import enum
import logging
import os
import sys
import threading
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import (
    Any,
    BinaryIO,
    Callable,
    DefaultDict,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

import pyls_jsonrpc.dispatchers
import pyls_jsonrpc.endpoint
import pyls_jsonrpc.streams

from . import n, util
from .diagnostics import Diagnostic
from .flutter import check_type, checked
from .n import FileId, SerializableType
from .page import Page
from .parser import Project, ProjectBackend
from .types import BuildIdentifierSet

_F = TypeVar("_F", bound=Callable[..., Any])
Uri = str
PARENT_PROCESS_WATCH_INTERVAL_SECONDS = 60
logger = logging.getLogger(__name__)


@checked
@dataclass
class Position:
    line: int
    character: int


@checked
@dataclass
class Range:
    start: Position
    end: Position


@checked
@dataclass
class Location:
    uri: Uri
    range: Range


@checked
@dataclass
class TextDocumentIdentifier:
    uri: Uri


@checked
@dataclass
class TextDocumentItem:
    uri: Uri
    languageId: str
    version: int
    text: str


@checked
@dataclass
class VersionedTextDocumentIdentifier(TextDocumentIdentifier):
    version: Union[int, None]


@checked
@dataclass
class TextDocumentContentChangeEvent:
    range: Optional[Range]
    rangeLength: Optional[int]
    text: str


@checked
@dataclass
class DiagnosticRelatedInformation:
    location: Location
    message: str


@checked
@dataclass
class LanguageServerDiagnostic:
    range: Range
    severity: Optional[int]
    code: Union[int, str, None]
    source: Optional[str]
    message: str
    relatedInformation: Optional[List[DiagnosticRelatedInformation]]


@checked
@dataclass
class Command:
    title: str
    command: str
    arguments: Optional[object]


@checked
@dataclass
class TextEdit:
    range: Range
    newText: str


@checked
@dataclass
class TextDocumentEdit:
    textDocument: VersionedTextDocumentIdentifier
    edits: List[TextEdit]


if sys.platform == "win32":
    import ctypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_INFROMATION = 0x1000

    def pid_exists(pid: int) -> bool:
        process = kernel32.OpenProcess(PROCESS_QUERY_INFROMATION, 0, pid)
        if process != 0:
            kernel32.CloseHandle(process)
            return True
        return False

else:

    def pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        else:
            return True


class Backend(ProjectBackend):
    def __init__(self, server: "LanguageServer") -> None:
        self.server = server
        self.pending_diagnostics: DefaultDict[FileId, List[Diagnostic]] = defaultdict(
            list
        )

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, fileid: FileId, diagnostics: List[Diagnostic]) -> None:
        self.pending_diagnostics[fileid] = diagnostics
        self.server.notify_diagnostics()

    def set_diagnostics(self, fileid: FileId, diagnostics: List[Diagnostic]) -> None:
        self.pending_diagnostics[fileid] = diagnostics
        self.server.notify_diagnostics()

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        pass

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        pass

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        try:
            del self.pending_diagnostics[page_id]
        except KeyError:
            pass

    def flush(self) -> None:
        pass


class Debouncer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.timers: Sequence[threading.Timer] = []

    def run(self, events: Sequence[Tuple[float, Callable[[], None]]]) -> None:
        self.stop()

        with self.lock:
            self.timers = [threading.Timer(ev[0], ev[1]) for ev in events]
            for timer in self.timers:
                timer.start()

    def stop(self) -> None:
        with self.lock:
            for timer in self.timers:
                timer.cancel()


class DiagnosticSeverity(enum.IntEnum):
    """The Language Server Protocol's DiagnosticSeverity namespace enumeration.
    See: https://microsoft.github.io/language-server-protocol/specification#diagnostic
    """

    error = 1
    warning = 2
    information = 3
    hint = 4

    @classmethod
    def from_diagnostic(cls, level: Diagnostic.Level) -> "DiagnosticSeverity":
        """Convert an internal Snooty Diagnostic's level to a DiagnosticSeverity value."""
        if level is Diagnostic.Level.info:
            return cls.information
        elif level is Diagnostic.Level.warning:
            return cls.warning
        elif level is Diagnostic.Level.error:
            return cls.error


@dataclass
class WorkspaceEntry:
    page_id: FileId
    document_uri: Uri
    diagnostics: List[Diagnostic]

    def create_lsp_diagnostics(self) -> List[object]:
        return [
            {
                "range": {
                    "start": {
                        "line": diagnostic.start[0],
                        "character": diagnostic.start[1],
                    },
                    "end": {"line": diagnostic.end[0], "character": diagnostic.end[1]},
                },
                "severity": DiagnosticSeverity.from_diagnostic(diagnostic.severity),
                "message": diagnostic.message,
                "code": type(diagnostic).__name__,
                "source": "snooty",
            }
            for diagnostic in self.diagnostics
        ]


class LanguageServer(pyls_jsonrpc.dispatchers.MethodDispatcher):
    def __init__(self, rx: BinaryIO, tx: BinaryIO) -> None:
        self.backend = Backend(self)
        self.workspace: Dict[str, WorkspaceEntry] = {}
        self.diagnostics: Dict[PurePath, List[Diagnostic]] = {}

        self._jsonrpc_stream_reader = pyls_jsonrpc.streams.JsonRpcStreamReader(rx)
        self._jsonrpc_stream_writer = pyls_jsonrpc.streams.JsonRpcStreamWriter(tx)
        self._endpoint = pyls_jsonrpc.endpoint.Endpoint(
            self, self._jsonrpc_stream_writer.write
        )
        self._shutdown = False
        self._debouncer = Debouncer()

        self.project: Optional[Project] = None
        self._project_lock = threading.Lock()

        self.pending_updates: util.QueueDict[FileId, Optional[str]] = util.QueueDict()

        def update_thread() -> None:
            while True:
                path, content = self.pending_updates.get()
                with self._project_lock:
                    if not self.project:
                        return

                    logger.info("Updating " + path.as_posix())
                    try:
                        self.project.update(path, content)
                    except Exception as err:
                        logger.exception(err)

        self.update_thread = threading.Thread(
            target=update_thread, name="update-thread", daemon=True
        )

    def start(self) -> None:
        self._jsonrpc_stream_reader.listen(self._endpoint.consume)
        logger.info("listening")

    def notify_diagnostics(self) -> None:
        """Handle the backend notifying us that diagnostics are available to be pulled."""
        if not self.project:
            logger.debug("Received diagnostics, but project not ready")
            return

        for fileid, diagnostics in self.backend.pending_diagnostics.items():
            self._set_diagnostics(fileid, diagnostics)

        self.backend.pending_diagnostics.clear()

    def update_file(self, page_path: FileId, change: Optional[str] = None) -> None:
        if page_path.suffix not in util.SOURCE_FILE_EXTENSIONS:
            return

        with self._project_lock:
            if not self.project:
                return

            self.project.cancel_postprocessor()

        self.pending_updates.put(page_path, change)

    def _set_diagnostics(self, fileid: FileId, diagnostics: List[Diagnostic]) -> None:
        self.diagnostics[fileid] = diagnostics
        uri = self.fileid_to_uri(fileid)
        workspace_item = self.workspace.get(uri, None)
        if workspace_item is None:
            workspace_item = WorkspaceEntry(fileid, uri, [])

        workspace_item.diagnostics = diagnostics
        self._endpoint.notify(
            "textDocument/publishDiagnostics",
            params={"uri": uri, "diagnostics": workspace_item.create_lsp_diagnostics()},
        )

    def uri_to_fileid(self, uri: Uri) -> FileId:
        if not self.project:
            raise TypeError("Cannot map uri to fileid before a project is open")

        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError("Only file:// URIs may be resolved", uri)

        path = Path(parsed.netloc).joinpath(Path(parsed.path)).resolve()
        return self.project.config.get_fileid(path)

    def fileid_to_uri(self, fileid: FileId) -> str:
        if not self.project:
            raise TypeError("Cannot map fileid to uri before a project is open")

        return "file://" + str(self.project.config.source_path.joinpath(fileid))

    def postprocess(self) -> None:
        with self._project_lock:
            if self.project is None:
                return
            project = self.project

        def inner() -> None:
            try:
                project.postprocess()
            except util.CancelledException:
                pass

        # The postprocess method is intended to be thread-safe
        threading.Thread(target=inner, daemon=True).start()

    def m_initialize(
        self,
        processId: Optional[int] = None,
        rootUri: Optional[Uri] = None,
        **kwargs: object,
    ) -> SerializableType:
        if rootUri:
            root_path = Path(rootUri.replace("file://", "", 1))
            self.project = Project(root_path, self.backend, {})
            self.notify_diagnostics()

            logger.info("Parsing")
            self.project.build(postprocess=False)
            self.update_thread.start()
            self.postprocess()

        if processId is not None:

            def watch_parent_process(pid: int) -> None:
                # exist when the given pid is not alive
                if not pid_exists(pid):
                    logger.info("parent process %s is not alive", pid)
                    self.m_exit()
                logger.debug("parent process %s is still alive", pid)
                threading.Timer(
                    PARENT_PROCESS_WATCH_INTERVAL_SECONDS,
                    watch_parent_process,
                    args=[pid],
                ).start()

            watching_thread = threading.Thread(
                target=watch_parent_process, args=(processId,), daemon=True
            )
            watching_thread.daemon = True
            watching_thread.start()

        return {"capabilities": {"textDocumentSync": 1}}

    def m_initialized(self, **kwargs: object) -> None:
        # Ignore this message to avoid logging a pointless warning
        pass

    def m_text_document__resolve(
        self, fileName: str, docPath: str, resolveType: str
    ) -> str:
        """Given an artifact's path relative to the project's source directory,
        return a corresponding source file path relative to the project's root."""

        if self.project is None:
            logger.warn("Project uninitialized")
            return fileName

        if resolveType == "doc":
            resolved_target_path = util.add_doc_target_ext(
                fileName, PurePath(docPath), self.project.config.source_path
            )
            return str(resolved_target_path)
        elif resolveType == "directive":
            """If the filename has a .rst extension, it might be converted from
            a YAML file. We want to get its original file path in that case."""

            # Strip the first slash from fileName so the / operator doesn't mess up :|
            stripped_file_name = fileName[1:]
            if fileName.endswith("rst"):
                file_path = self.project.config.source_path / stripped_file_name
                file_id = self.project.get_fileid(file_path)
                real_file_path = self.project.config.source_path / file_id
                return str(real_file_path)
            else:
                return str(self.project.config.source_path / stripped_file_name)
        else:
            logger.error("resolveType is not supported")
            return fileName

    def m_text_document__get_page_ast(self, fileName: str) -> SerializableType:
        """
        Given the filename, return the ast of the page that is created from parsing that file.
        If the file is a .rst file, we return an ast that emulates the ast of a .txt
        file containing a single include directive to said .rst file.
        """

        if self.project is None:
            logger.warn("Project uninitialized")
            return None

        filePath = Path(fileName)
        page_ast = self.project.get_page_ast(filePath)

        # If rst file, insert its ast into a pseudo ast object
        if filePath.suffix == ".rst":
            # Copy ast of previewed file into a modified version
            if isinstance(page_ast, n.Parent):
                children = page_ast.children
            else:
                children = []
            rst_ast = n.Directive(
                page_ast.start,
                children,
                "",
                "include",
                [n.Text((0,), self.project.config.get_fileid(filePath).as_posix())],
                {},
            )

            # Insert modified ast as a child of a pseudo empty page ast
            pseudo_ast = n.Root((0,), [], self.project.config.get_fileid(filePath), {})
            pseudo_ast.children.append(rst_ast)
            return pseudo_ast.serialize()

        return page_ast.serialize()

    def m_text_document__get_project_name(self) -> SerializableType:
        """Get the project's name from its ProjectConfig"""
        # This method may later be refactored to obtain other ProjectConfig data
        # (https://github.com/mongodb/snooty-parser/pull/44#discussion_r336749209)
        if not self.project:
            logger.warn("Project uninitialized")
            return None

        return self.project.get_project_name()

    def m_text_document__get_page_fileid(self, filePath: str) -> SerializableType:
        """Given a path to a file, return its fileid as a string"""
        if not self.project:
            logger.warn("Project uninitialized")
            return None

        fileid = self.project.config.get_fileid(PurePath(filePath))
        return fileid.without_known_suffix

    def m_text_document__did_open(self, textDocument: SerializableType) -> None:
        logger.info("did_open")
        if not self.project:
            return

        item = check_type(TextDocumentItem, textDocument)
        fileid = self.uri_to_fileid(item.uri)
        entry = WorkspaceEntry(fileid, item.uri, [])
        self.workspace[item.uri] = entry
        self.update_file(fileid, item.text)

    def m_text_document__did_change(
        self, textDocument: SerializableType, contentChanges: SerializableType
    ) -> None:
        logger.info("did_change")
        if not self.project:
            return

        identifier = check_type(VersionedTextDocumentIdentifier, textDocument)
        fileid = self.uri_to_fileid(identifier.uri)
        assert isinstance(contentChanges, list)
        change = next(
            check_type(TextDocumentContentChangeEvent, x) for x in contentChanges
        )

        self._debouncer.run(
            [
                (0.1, lambda: self.update_file(fileid, change.text)),
                (0.25, self.postprocess),
            ]
        )

    def m_text_document__did_close(self, textDocument: SerializableType) -> None:
        logger.info("did_close")
        if not self.project:
            return

        identifier = check_type(TextDocumentIdentifier, textDocument)
        fileid = self.uri_to_fileid(identifier.uri)
        del self.workspace[identifier.uri]
        self.update_file(fileid)

    def m_shutdown(self, **_kwargs: object) -> None:
        self._shutdown = True

    def m_exit(self, **_kwargs: object) -> None:
        self._endpoint.shutdown()
        self._debouncer.stop()
        if self.project:
            self.project.stop_monitoring()

    def __enter__(self) -> "LanguageServer":
        return self

    def __exit__(self, *args: object) -> None:
        self.m_shutdown()
        self.m_exit()


def start() -> None:
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    server = LanguageServer(stdin, stdout)
    logger.info("Started")
    server.start()

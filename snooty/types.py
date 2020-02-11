import enum
import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath
from typing import (
    Dict,
    DefaultDict,
    NamedTuple,
    Set,
    List,
    Iterator,
    Sequence,
    MutableSequence,
    Tuple,
    Optional,
    Union,
    Match,
)
from typing_extensions import Protocol
import urllib.parse
import toml
from .flutter import checked, check_type, LoadError
from . import n, intersphinx
from .n import SerializableType as ST

SerializableType = ST
PAT_VARIABLE = re.compile(r"{\+([\w-]+)\+}")
PAT_GIT_MARKER = re.compile(r"^<<<<<<< .*?^=======\n.*?^>>>>>>>", re.M | re.S)
PAT_FILE_EXTENSIONS = re.compile(r"\.((txt)|(rst)|(yaml))$")
BuildIdentifierSet = Dict[str, Optional[str]]
logger = logging.getLogger(__name__)

#: Indicates the target protocol of a target: either a file local to the
#: current project, or a URL (from an intersphinx inventory).
TargetType = enum.Enum("TargetType", ("fileid", "url"))


class EmbeddedRstParser(Protocol):
    def parse_block(self, text: str, lineno: int) -> MutableSequence[n.Node]:
        ...

    def parse_inline(self, text: str, lineno: int) -> MutableSequence[n.InlineNode]:
        ...


def normalize_target(target: str) -> str:
    """Normalize targets to allow easy matching against the target
       database: normalize whitespace and convert to lowercase."""
    return re.sub(r"\s+", " ", target).lower()


class SnootyError(Exception):
    pass


class FileId(PurePosixPath):
    """An unambiguous file path relative to the local project's root."""

    @property
    def without_known_suffix(self) -> str:
        """Returns the fileid without any of its known file extensions (txt, rst, yaml)"""
        fileid = self.with_name(PAT_FILE_EXTENSIONS.sub("", self.name))
        return fileid.as_posix()


@dataclass
class Diagnostic:
    __slots__ = ("message", "severity", "start", "end")

    class Level(enum.IntEnum):
        info = 0
        error = 1
        warning = 2

        @classmethod
        def from_docutils(cls, docutils_level: int) -> "Diagnostic.Level":
            level = docutils_level - 1
            level = min(level, cls.warning)
            level = max(level, cls.info)
            return cls(level)

    severity: Level
    message: str
    start: Tuple[int, int]
    end: Tuple[int, int]

    @property
    def severity_string(self) -> str:
        return self.severity.name.title()

    @classmethod
    def create(
        cls,
        severity: Level,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> "Diagnostic":
        if isinstance(start, int):
            start_line, start_column = start, 0
        else:
            start_line, start_column = start

        if end is None:
            end_line, end_column = start_line, 1000
        elif isinstance(end, int):
            end_line, end_column = end, 1000
        else:
            end_line, end_column = end

        return cls(
            severity, message, (start_line, start_column), (end_line, end_column)
        )

    @classmethod
    def info(
        cls,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> "Diagnostic":
        return cls.create(cls.Level.info, message, start, end)

    @classmethod
    def warning(
        cls,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> "Diagnostic":
        return cls.create(cls.Level.warning, message, start, end)

    @classmethod
    def error(
        cls,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> "Diagnostic":
        return cls.create(cls.Level.error, message, start, end)


@dataclass
class StaticAsset:
    fileid: FileId
    path: Path
    upload: bool
    _checksum: Optional[str]
    _data: Optional[bytes]

    def __hash__(self) -> int:
        return hash(self.fileid)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StaticAsset) and self.fileid == other.fileid

    def get_checksum(self) -> str:
        self.__load()
        assert self._checksum is not None
        return self._checksum

    def can_upload(self) -> bool:
        """Return True iff the file exists and it's of a file type which should be uploaded
           (e.g. an image)."""
        try:
            self.__load()
        except OSError:
            return False

        return self.upload

    @property
    def data(self) -> bytes:
        self.__load()
        assert self._data is not None
        return self._data

    @classmethod
    def load(cls, fileid: FileId, path: Path, upload: bool = False) -> "StaticAsset":
        return cls(fileid, path, upload, None, None)

    def __load(self) -> None:
        if self._data is None:
            self._data = self.path.read_bytes()
            self._checksum = hashlib.blake2b(self._data, digest_size=32).hexdigest()


@dataclass
class TargetDatabase:
    """A database of targets known to this project."""

    class Result(NamedTuple):
        type: TargetType
        result: str
        title: Sequence[n.InlineNode]

    intersphinx_inventories: Dict[str, intersphinx.Inventory] = field(
        default_factory=dict
    )
    local_definitions: DefaultDict[
        str, List[Tuple[FileId, Sequence[n.InlineNode]]]
    ] = field(default_factory=lambda: defaultdict(list))

    def __contains__(self, key: str) -> bool:
        key = normalize_target(key)
        if key in self.local_definitions:
            return True

        for inventory in self.intersphinx_inventories.values():
            if key in inventory:
                return True

        return False

    def __getitem__(self, key: str) -> Sequence["TargetDatabase.Result"]:
        key = normalize_target(key)
        results: List[TargetDatabase.Result] = []

        # Check to see if the target is defined locally
        try:
            results.extend(
                TargetDatabase.Result(
                    TargetType.fileid, fileid.without_known_suffix, title
                )
                for fileid, title in self.local_definitions[key]
            )
        except KeyError:
            pass

        # Get URL from intersphinx inventories
        for inventory in self.intersphinx_inventories.values():
            if key in inventory:
                base_url = inventory.base_url
                entry = inventory[key]
                url = urllib.parse.urljoin(base_url, entry.uri)
                title: List[n.InlineNode] = [n.Text((-1,), entry.display_name)]
                results.append(TargetDatabase.Result(TargetType.url, url, title))

        return results

    def define_local_target(
        self,
        domain: str,
        name: str,
        targets: Sequence[str],
        pageid: FileId,
        title: Sequence[n.InlineNode],
    ) -> None:
        for target in targets:
            target = normalize_target(target)
            key = f"{domain}:{name}:{target}"
            self.local_definitions[key].append((pageid, title))

    def reset(self, config: "ProjectConfig") -> None:
        """Reset this database to a "blank" state with intersphinx inventories defined by
           the given ProjectConfig instance."""
        self.intersphinx_inventories.clear()
        self.local_definitions.clear()

        logger.debug("Loading %s intersphinx inventories", len(config.intersphinx))
        for url in config.intersphinx:
            self.intersphinx_inventories[url] = intersphinx.fetch_inventory(url)

    @classmethod
    def load(cls, config: "ProjectConfig") -> "TargetDatabase":
        """Create a TargetDatabase with the intersphinx inventories specified by the given
           ProjectConfig."""
        db = cls()
        db.reset(config)
        return db


@dataclass
class Cache:
    """A versioned cache that associates a (FileId, int) pair with an arbitrary object and
       an integer version. Whenever the key is re-assigned, the version is incremented."""

    _cache: Dict[Tuple[FileId, int], object] = field(default_factory=dict)
    _keys_of_each_fileid: DefaultDict[FileId, Set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    _versions: DefaultDict[Tuple[FileId, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def __setitem__(self, key: Tuple[FileId, int], value: object) -> None:
        if key in self._cache:
            self._cache[key] = value
        else:
            self._cache[key] = value

        self._versions[key] += 1
        self._keys_of_each_fileid[key[0]].add(key[1])

    def __delitem__(self, fileid: FileId) -> None:
        keys = self._keys_of_each_fileid[fileid]
        del self._keys_of_each_fileid[fileid]
        for key in keys:
            del self._cache[(fileid, key)]

    def __getitem__(self, key: Tuple[FileId, int]) -> Optional[object]:
        return self._cache.get(key, None)

    def get_versions(self, fileid: FileId) -> Iterator[int]:
        for key, version in self._versions.items():
            if key[0] == fileid:
                yield version


class ProjectInterface(Protocol):
    expensive_operation_cache: Cache
    targets: TargetDatabase


@dataclass
class EmptyProjectInterface:
    """An empty ProjectInterface implementation for testing."""

    expensive_operation_cache: Cache
    targets: TargetDatabase

    def __init__(self) -> None:
        self.expensive_operation_cache = Cache()
        self.targets = TargetDatabase()


class PendingTask:
    """A thunk which will be executed in the main process after the full tree is
       constructed. This should primarily be used to execute tasks which may need
       to mutate state from the main process (e.g. caches or dependency graphs)."""

    def __init__(self, node: n.Node) -> None:
        self.node = node

    def __call__(
        self, diagnostics: List[Diagnostic], project: ProjectInterface
    ) -> None:
        """Perform an action in the main process once the tree has been built."""
        pass

    def error(self, message: str) -> Diagnostic:
        """Create an error diagnostic associated with this task's node."""
        return Diagnostic.error(message, self.node.start[0])


@dataclass
class Page:
    source_path: Path
    output_filename: str
    source: str
    ast: n.Parent[n.Node]
    static_assets: Set[StaticAsset] = field(default_factory=set)
    pending_tasks: List[PendingTask] = field(default_factory=list)
    category: Optional[str] = None
    query_fields: Dict[str, SerializableType] = field(default_factory=dict)

    @classmethod
    def create(
        self,
        source_path: Path,
        output_filename: Optional[str],
        source: str,
        ast: Optional[n.Parent[n.Node]] = None,
    ) -> "Page":
        if output_filename is None:
            output_filename = source_path.name

        if ast is None:
            ast = n.Root((0,), [], {})

        return Page(source_path, output_filename, source, ast)

    def fake_full_path(self) -> PurePath:
        """Return a fictitious path (hopefully) uniquely identifying this output artifact."""
        if self.category:
            # Giza wrote out yaml file artifacts under a directory. e.g. steps-foo.yaml becomes
            # steps/foo.rst
            return self.source_path.parent.joinpath(
                PurePath(self.category), self.output_filename
            )
        return self.source_path

    def finish(
        self, diagnostics: List[Diagnostic], project: Optional[ProjectInterface] = None
    ) -> None:
        """Finish all pending tasks for this page. This should be run in the main process."""
        for task in self.pending_tasks:
            task(
                diagnostics, project if project is not None else EmptyProjectInterface()
            )

        self.pending_tasks.clear()


@checked
@dataclass
class ProjectConfig:
    root: Path
    name: str
    default_domain: Optional[str] = field(default=None)
    title: str = field(default="untitled")
    source: str = field(default="source")
    constants: Dict[str, object] = field(default_factory=dict)
    intersphinx: List[str] = field(default_factory=list)
    substitutions: Dict[str, str] = field(default_factory=dict)
    # substitution_nodes contains a parsed representation of the substitutions member, and is populated on Project initialization.
    substitution_nodes: Dict[str, List[n.InlineNode]] = field(default_factory=dict)
    toc_landing_pages: List[str] = field(default_factory=list)
    page_groups: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def source_path(self) -> Path:
        return self.root.joinpath(self.source)

    @property
    def config_path(self) -> Path:
        return self.root.joinpath("snooty.toml")

    @classmethod
    def open(cls, root: Path) -> Tuple["ProjectConfig", List[Diagnostic]]:
        path = root
        diagnostics = []
        while path.parent != path:
            try:
                with path.joinpath("snooty.toml").open(encoding="utf-8") as f:
                    data = toml.load(f)
                    data["root"] = path
                    result, parsed_diagnostics = check_type(
                        ProjectConfig, data
                    ).render_constants()
                    return result, parsed_diagnostics
            except FileNotFoundError:
                pass
            except LoadError as err:
                diagnostics.append(Diagnostic.error(str(err), 0))

            path = path.parent

        return cls(root, name="unnamed"), diagnostics

    def render_constants(self) -> Tuple["ProjectConfig", List[Diagnostic]]:
        if not self.constants:
            return self, []
        constants: Dict[str, object] = {}
        all_diagnostics: List[Diagnostic] = []
        for k, v in self.constants.items():
            result, diagnostics = self.substitute(str(v))
            all_diagnostics.extend(diagnostics)
            constants[k] = result

        self.constants = constants
        return self, all_diagnostics

    def read(
        self, path: Path, text: Optional[str] = None
    ) -> Tuple[str, List[Diagnostic]]:
        if text is None:
            text = path.read_text(encoding="utf-8")

        text, diagnostics = self.substitute(text)
        match_found = PAT_GIT_MARKER.finditer(text)

        if match_found:
            for match in match_found:
                lineno = text.count("\n", 0, match.start())
                diagnostics.append(Diagnostic.error("git merge conflict found", lineno))

        return (text, diagnostics)

    def substitute(self, source: str) -> Tuple[str, List[Diagnostic]]:
        """Substitute all placeholders within a string."""
        diagnostics: List[Diagnostic] = []

        def handle_match(match: Match[str]) -> str:
            """Replace a given placeholder match with a value from the project
               configuration. Log a warning if it's not defined."""
            variable_name = match.group(1)
            try:
                return str(self.constants[variable_name])
            except KeyError:
                lineno = source.count("\n", 0, match.start())
                diagnostics.append(
                    Diagnostic.error(
                        f"{variable_name} not defined as a source constant", lineno
                    )
                )

            # Return a zero-width space to avoid breaking syntax
            return "\u200b"

        return PAT_VARIABLE.sub(handle_match, source), diagnostics

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from . import language_server
from .types import Diagnostic, FileId
from .flutter import checked, check_type

CWD_URL = "file://" + Path().resolve().as_posix()


@checked
@dataclass
class LSPPosition:
    line: int
    character: int


@checked
@dataclass
class LSPRange:
    start: LSPPosition
    end: LSPPosition


@checked
@dataclass
class LSPDiagnostic:
    message: str
    severity: int
    range: LSPRange


def test_debounce() -> None:
    bounces = [0]

    @language_server.debounce(0.1)
    def inc() -> None:
        bounces[0] += 1

    inc()
    inc()
    inc()

    time.sleep(0.2)
    inc()

    assert bounces[0] == 1


def test_pid_exists() -> None:
    assert language_server.pid_exists(0)
    # Test that an invalid PID returns False
    assert not language_server.pid_exists(537920)


def test_workspace_entry() -> None:
    entry = language_server.WorkspaceEntry(
        FileId(""), "", [Diagnostic.error("foo", 10), Diagnostic.warning("fo", 10, 12)]
    )
    parsed = [
        check_type(LSPDiagnostic, diag) for diag in entry.create_lsp_diagnostics()
    ]
    assert parsed[0] == LSPDiagnostic(
        "foo", 1, LSPRange(LSPPosition(10, 0), LSPPosition(10, 1000))
    )
    assert parsed[1] == LSPDiagnostic(
        "fo", 2, LSPRange(LSPPosition(10, 0), LSPPosition(12, 1000))
    )


def test_language_server() -> None:
    with language_server.LanguageServer(sys.stdin.buffer, sys.stdout.buffer) as server:
        server.m_initialize(None, CWD_URL + "/test_data/test_project")
        assert server.uri_to_fileid(
            CWD_URL + "/test_data/test_project/source/blah/bar.rst"
        ) == FileId("blah/bar.rst")


def test_text_doc_resolve() -> None:
    """Tests to see if m_text_document__resolve() returns the proper path combined with """
    with language_server.LanguageServer(sys.stdin.buffer, sys.stdout.buffer) as server:
        server.m_initialize(None, CWD_URL + "/test_data/test_project")

        assert server.project is not None

        # Set up resolve arguments for testing directive file
        source_path = server.project.config.source_path
        docpath_str = str(source_path.joinpath("foo.rst"))
        test_file = "/images/compass-create-database.png"
        resolve_type = "directive"

        # Set up assertion
        resolve_path = Path(
            server.m_text_document__resolve(test_file, docpath_str, resolve_type)
        )
        expected_path = source_path.joinpath(test_file[1:])

        assert resolve_path == expected_path

        # Resolve arguments for testing doc role target file
        test_file = "index"  # Testing relative path for example
        resolve_type = "doc"

        # Set up assertion
        resolve_path = Path(
            server.m_text_document__resolve(test_file, docpath_str, resolve_type)
        )
        expected_path = source_path.joinpath(test_file).with_suffix(".txt")

        assert resolve_path == expected_path

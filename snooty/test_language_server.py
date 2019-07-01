import sys
import time
from dataclasses import dataclass
from pathlib import Path
from . import language_server
from .types import Diagnostic, FileId
from .flutter import checked, check_type


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
        assert server.uri_to_path("file://foo.rst") == Path("foo.rst")


def test_text_doc_resolve() -> None:
    """Tests to see if m_text_document__resolve() returns the proper path combined with """
    with language_server.LanguageServer(sys.stdin.buffer, sys.stdout.buffer) as server:
        server.m_initialize(None, "file://test_data/test_project")

        test_file = "/images/compass-create-database.png"

        assert server.project is not None

        assert (
            server.m_text_document__resolve(test_file)
            == str(server.project.config.source_path) + test_file
        )

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from . import language_server, rstparser
from .util_test import check_ast_testing_string
from .types import Diagnostic, FileId, SerializableType, ProjectConfig
from .parser import parse_rst, JSONVisitor
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
    """Tests to see if m_text_document__resolve() returns the proper path combined with 
    appropriate extension"""
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


def test_text_doc_get_page_ast() -> None:
    """Tests to see if m_text_document__get_ast() returns the proper
    page ast for .txt file"""
    language_server_ast: SerializableType = None
    parser_ast: SerializableType = None

    test_file_text = """
            .. _guides:

            ======
            Guides
            ======

            .. figure:: /images/compass-create-database.png
            :alt: Sample images

            .. include:: /includes/test_rst.rst

            .. include:: /includes/steps/migrate-compose-pr.rst
            """

    # Set up language server
    with language_server.LanguageServer(sys.stdin.buffer, sys.stdout.buffer) as server:
        server.m_initialize(None, CWD_URL + "/test_data/test_project_ls")

        assert server.project is not None

        source_path = server.project.config.source_path
        test_file = "index.txt"
        test_file_path = source_path.joinpath(test_file)

        language_server_ast = server.m_text_document__get_page_ast(
            str(test_file_path), test_file_text
        )

    # Set up parser
    root_path = Path("test_data")
    project_root = root_path.joinpath("test_project")
    path = project_root.joinpath(Path("source/index.txt")).resolve()
    project_config = ProjectConfig(project_root, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Parse text
    page, diagnostics = parse_rst(parser, path, test_file_text)
    page.finish(diagnostics)

    # Parser ast should have less information than ast from language server
    assert language_server_ast != parser_ast

    # Check to see that ast has all includes
    check_ast_testing_string(
        language_server_ast,
        """<root alt="Sample images">
        <target ids="['guides']"></target>
        <directive name="figure" checksum="10e351828f156afcafc7744c30d7b2564c6efba1ca7c55cac59560c67581f947">
        <text>/images/compass-create-database.png</text></directive>
        <directive name="include"><text>/includes/test_rst.rst</text>
        <directive name="include"><text>/includes/include_child.rst</text>
        <paragraph><text>This is an include in an include</text></paragraph>
        </directive></directive>
        <directive name="include"><text>/includes/steps/migrate-compose-pr.rst</text>
        <directive name="step"><section><heading id="mongodb-atlas-account">
        <text>MongoDB Atlas account</text></heading>
        <paragraph><text>If you don't have an Atlas account, </text>
        <role name="doc" label="{'type': 'text', 'value': 'create one', 'position': {'start': {'line': 1}}}" target="/cloud/atlas"></role>
        <text> now.</text></paragraph></section></directive>
        <directive name="step"><section>
        <heading id="compose-mongodb-deployment"><text>Compose MongoDB deployment</text></heading>
        </section></directive></directive></root>""",
    )

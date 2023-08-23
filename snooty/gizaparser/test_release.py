from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..diagnostics import Diagnostic
from ..n import FileId
from ..page import Page
from ..parser import EmbeddedRstParser
from ..types import ProjectConfig
from ..util_test import check_ast_testing_string
from .release import GizaReleaseSpecificationCategory


def test_release_specification() -> None:
    root_path = Path("test_data/test_gizaparser")
    project_config = ProjectConfig(root_path, "")
    project_config.constants["version"] = "3.4"
    category = GizaReleaseSpecificationCategory(project_config)

    fileid = FileId("includes/release-specifications.yaml")
    parent_fileid = FileId("includes/release-base.yaml")

    def add_main_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(fileid)
        category.add(fileid, text, extracts)
        assert len(parse_diagnostics) == 0
        assert len(extracts) == 2
        return parse_diagnostics

    def add_parent_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(parent_fileid)
        category.add(parent_fileid, text, extracts)
        assert len(parse_diagnostics) == 0
        assert len(extracts) == 2
        return parse_diagnostics

    all_diagnostics: Dict[FileId, List[Diagnostic]] = {}
    all_diagnostics[fileid] = add_main_file()
    all_diagnostics[parent_fileid] = add_parent_file()

    assert len(category) == 2
    _, giza_node = next(category.reify_all_files(all_diagnostics))

    def create_page(filename: Optional[str]) -> Tuple[Page, EmbeddedRstParser]:
        page = Page.create(fileid, filename, "")
        return (page, EmbeddedRstParser(project_config, page, all_diagnostics[fileid]))

    pages = category.to_pages(fileid, create_page, giza_node.data)
    assert [page.fake_full_fileid().as_posix() for page in pages] == [
        "includes/release/untar-release-osx-x86_64.rst",
        "includes/release/install-ent-windows-default.rst",
    ]

    assert all((not diagnostics for diagnostics in all_diagnostics.values()))

    check_ast_testing_string(
        pages[0].ast,
        """<root fileid="includes/release-specifications.yaml"><directive name="release_specification">
        <code lang="sh" copyable="True">
        tar -zxvf mongodb-macos-x86_64-3.4.tgz\n</code>
        </directive></root>""",
    )

    check_ast_testing_string(
        pages[1].ast,
        """<root fileid="includes/release-specifications.yaml"><directive name="release_specification">
            <code lang="bat" copyable="True">
            msiexec.exe /l*v mdbinstall.log  /qb /i mongodb-win32-x86_64-enterprise-windows-64-3.4-signed.msi\n
            </code>
            </directive></root>""",
    )

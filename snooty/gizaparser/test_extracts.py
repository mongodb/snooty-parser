from pathlib import Path, PurePath
from typing import Dict, Tuple, List, Optional
from .extracts import GizaExtractsCategory
from ..types import Diagnostic, Page, ProjectConfig
from ..parser import EmbeddedRstParser
from ..util_test import ast_to_testing_string


def test_extract() -> None:
    project_config = ProjectConfig(Path("test_data"), "")
    category = GizaExtractsCategory(project_config)
    path = Path("test_data/extracts-test.yaml")
    parent_path = Path("test_data/extracts-test-parent.yaml")

    def add_main_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(path)
        category.add(path, text, extracts)
        assert len(parse_diagnostics) == 1
        assert parse_diagnostics[0].severity == Diagnostic.Level.error
        assert parse_diagnostics[0].start == (21, 0)
        assert len(extracts) == 5
        return parse_diagnostics

    def add_parent_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(parent_path)
        category.add(parent_path, text, extracts)
        assert len(parse_diagnostics) == 0
        assert len(extracts) == 1
        return parse_diagnostics

    all_diagnostics: Dict[PurePath, List[Diagnostic]] = {}
    all_diagnostics[path] = add_main_file()
    all_diagnostics[parent_path] = add_parent_file()

    assert len(category) == 2
    file_id, giza_node = next(category.reify_all_files(all_diagnostics))

    def create_page(filename: Optional[str]) -> Tuple[Page, EmbeddedRstParser]:
        page = Page.create(path, filename, "")
        return (page, EmbeddedRstParser(project_config, page, all_diagnostics[path]))

    pages = category.to_pages(path, create_page, giza_node.data)
    assert [str(page.fake_full_path()) for page in pages] == [
        "test_data/extracts/installation-directory-rhel.rst",
        "test_data/extracts/broken-inherit.rst",
        "test_data/extracts/another-file.rst",
        "test_data/extracts/missing-substitution.rst",
    ]

    assert ast_to_testing_string(pages[0].ast) == "".join(
        (
            '<directive name="extract"><paragraph><text>By default, MongoDB stores its data files in ',
            "</text><literal><text>/var/lib/mongo</text></literal><text> and its\nlog files in </text>",
            "<literal><text>/var/log/mongodb</text></literal><text>.</text></paragraph></directive>",
        )
    )

    assert ast_to_testing_string(pages[3].ast) == "".join(
        (
            '<directive name="extract"><paragraph><text>Substitute</text></paragraph></directive>'
        )
    )

    # XXX: We need to track source file information for each property.
    # Line number 1 here should correspond to parent_path, not path.
    assert set(d.start[0] for d in all_diagnostics[path]) == set((21, 13, 1))

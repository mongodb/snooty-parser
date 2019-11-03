from pathlib import Path, PurePath
from typing import Dict, Tuple, List
from .options import GizaOptionsCategory
from ..types import Diagnostic, Page, EmbeddedRstParser, ProjectConfig
from ..parser import make_embedded_rst_parser


def test_options() -> None:
    project_config, project_diagnostics = ProjectConfig.open(Path("test_data"))
    assert project_diagnostics == []

    category = GizaOptionsCategory(project_config)
    path = Path("test_data/options-shared.yaml")
    child_path = Path("test_data/options-test.yaml")

    def add_root_file() -> List[Diagnostic]:
        options, text, parse_diagnostics = category.parse(path)
        assert len(options) == 1
        category.add(path, text, options)
        assert len(parse_diagnostics) == 0
        return parse_diagnostics

    def add_child_file() -> List[Diagnostic]:
        options, text, parse_diagnostics = category.parse(child_path)
        assert len(options) == 2
        category.add(child_path, text, options)
        assert len(parse_diagnostics) == 0
        return parse_diagnostics

    all_diagnostics: Dict[PurePath, List[Diagnostic]] = {}
    all_diagnostics[child_path] = add_child_file()
    all_diagnostics[path] = add_root_file()

    assert len(category) == 2
    file_id, giza_node = next(category.reify_all_files(all_diagnostics))

    def create_page() -> Tuple[Page, EmbeddedRstParser]:
        page = Page(path, "", {})
        return (
            page,
            make_embedded_rst_parser(project_config, page, all_diagnostics[path]),
        )

    pages = category.to_pages(create_page, giza_node.data)
    assert len(pages) == 2

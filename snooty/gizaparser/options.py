from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple, List, Union
from ..flutter import checked
from ..types import Diagnostic, EmbeddedRstParser, SerializableType, Page
from .nodes import GizaCategory, OptionsInheritable
from .parse import parse


@checked
@dataclass
class Option(OptionsInheritable):
    command: Optional[str]
    aliases: Optional[str]
    args: Optional[str]
    default: Union[str, int, None]
    description: Optional[str]
    directive: Optional[str]
    optional: Optional[bool]
    post: Optional[str]
    pre: Optional[str]
    type: Optional[str]

    def render(
        self, page: Page, parse_rst: EmbeddedRstParser
    ) -> List[SerializableType]:
        all_nodes: List[SerializableType] = []
        return all_nodes


def option_to_page(
    page: Page, option: Option, rst_parser: EmbeddedRstParser
) -> SerializableType:
    rendered = option.render(page, rst_parser)
    return {
        "type": "directive",
        "name": "option",
        "position": {"start": {"line": option.line}},
        "children": rendered,
    }


class GizaOptionsCategory(GizaCategory[Option]):
    def parse(
        self, path: Path, text: Optional[str] = None
    ) -> Tuple[Sequence[Option], str, List[Diagnostic]]:
        return parse(Option, path, self.project_config, text)

    def to_pages(
        self,
        page_factory: Callable[[], Tuple[Page, EmbeddedRstParser]],
        options: Sequence[Option],
    ) -> List[Page]:
        pages: List[Page] = []
        for option in options:
            assert option.ref is not None
            if option.ref.startswith("_"):
                continue

            page, rst_parser = page_factory()
            page.category = "option"
            page.output_filename = f"{option.program}-{option.name}"
            page.ast = option_to_page(page, option, rst_parser)
            pages.append(page)

        return pages

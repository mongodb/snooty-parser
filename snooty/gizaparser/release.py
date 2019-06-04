from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, List, Tuple, Sequence
from ..flutter import checked
from ..types import Diagnostic, EmbeddedRstParser, SerializableType, Page
from .parse import parse
from .nodes import Inheritable, GizaCategory


@checked
@dataclass
class ReleaseSpecification(Inheritable):
    copyable: Optional[bool]
    language: Optional[str]
    code: Optional[str]

    def render(self, page: Page, parse_rst: EmbeddedRstParser) -> SerializableType:
        children: List[SerializableType] = []
        if self.code:
            children.append(
                {
                    "type": "code",
                    "lang": self.language,
                    "copyable": True if self.copyable is None else self.copyable,
                    "position": {"start": {"line": self.line}},
                    "value": self.code,
                }
            )
        return children


def release_specification_to_page(
    page: Page, node: ReleaseSpecification, rst_parser: EmbeddedRstParser
) -> SerializableType:
    rendered = node.render(page, rst_parser)
    return {
        "type": "directive",
        "name": "release_specification",
        "position": {"start": {"line": node.line}},
        "children": rendered,
    }


class GizaReleaseSpecificationCategory(GizaCategory[ReleaseSpecification]):
    def parse(
        self, path: Path, text: Optional[str] = None
    ) -> Tuple[Sequence[ReleaseSpecification], str, List[Diagnostic]]:
        nodes, text, diagnostics = parse(
            ReleaseSpecification, path, self.project_config, text
        )

        def report_missing_ref(node: ReleaseSpecification) -> bool:
            diagnostics.append(
                Diagnostic.error(
                    "Missing ref; all release specifications must define a ref",
                    node.line,
                )
            )
            return False

        # All nodes must have an explicitly-defined ref ID
        release_specifications = [
            node for node in nodes if node.ref or report_missing_ref(node)
        ]
        return release_specifications, text, diagnostics

    def to_pages(
        self,
        page_factory: Callable[[], Tuple[Page, EmbeddedRstParser]],
        nodes: Sequence[ReleaseSpecification],
    ) -> List[Page]:
        pages: List[Page] = []
        for node in nodes:
            assert node.ref is not None
            if node.ref.startswith("_"):
                continue

            page, rst_parser = page_factory()
            page.category = "release"
            page.output_filename = node.ref
            page.ast = release_specification_to_page(page, node, rst_parser)
            pages.append(page)

        return pages

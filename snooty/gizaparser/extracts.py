from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple, Sequence, Optional
from ..flutter import checked
from .nodes import Inheritable, GizaCategory, HeadingMixin
from .parse import parse
from ..types import Diagnostic, EmbeddedRstParser, Page
from .. import n


@checked
@dataclass
class Extract(Inheritable, HeadingMixin):
    content: Optional[str]
    only: Optional[str]

    def render(self, page: Page, rst_parser: EmbeddedRstParser) -> List[n.Node]:
        if self.only is not None:
            raise NotImplementedError('extracts: "only" not implemented')

        children: List[n.Node] = []
        children.extend(self.render_heading(rst_parser))
        if self.content:
            children.extend(rst_parser.parse_block(self.content, self.line))

        return children


def extract_to_page(
    page: Page, extract: Extract, rst_parser: EmbeddedRstParser
) -> n.Directive:
    rendered = extract.render(page, rst_parser)
    directive = n.Directive((extract.line,), [], "", "extract", [], {})
    directive.children = rendered
    return directive


class GizaExtractsCategory(GizaCategory[Extract]):
    def parse(
        self, path: Path, text: Optional[str] = None
    ) -> Tuple[Sequence[Extract], str, List[Diagnostic]]:
        extracts, text, diagnostics = parse(Extract, path, self.project_config, text)

        def report_missing_ref(extract: Extract) -> bool:
            diagnostics.append(
                Diagnostic.error(
                    "Missing ref; all extracts must define a ref", extract.line
                )
            )
            return False

        # All extracts must have an explicitly-defined ref ID
        extracts = [
            extract
            for extract in extracts
            if extract.ref or report_missing_ref(extract)
        ]
        return extracts, text, diagnostics

    def to_pages(
        self,
        source_path: Path,
        page_factory: Callable[[str], Tuple[Page, EmbeddedRstParser]],
        extracts: Sequence[Extract],
    ) -> List[Page]:
        pages: List[Page] = []
        for extract in extracts:
            assert extract.ref is not None
            if extract.ref.startswith("_"):
                continue

            page, rst_parser = page_factory(f"{extract.ref}.rst")
            page.category = "extracts"
            page.ast = extract_to_page(page, extract, rst_parser)
            pages.append(page)

        return pages

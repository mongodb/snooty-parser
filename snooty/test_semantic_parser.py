from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, cast
from .gizaparser.published_branches import PublishedBranches
from .types import FileId, Page, Diagnostic, SerializableType
from .parser import Project

ROOT_PATH = Path("test_data")


@dataclass
class Backend:
    metadata: Dict[str, SerializableType] = field(default_factory=dict)
    pages: Dict[FileId, Page] = field(default_factory=dict)
    updates: List[FileId] = field(default_factory=list)

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        pass

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        self.pages[page_id] = page
        self.updates.append(page_id)

    def on_update_metadata(
        self, prefix: List[str], field: Dict[str, SerializableType]
    ) -> None:
        self.metadata.update(field)

    def on_delete(self, page_id: FileId) -> None:
        pass

    def on_published_branches(
        self, prefix: List[str], published_branches: PublishedBranches
    ) -> None:
        pass


def test() -> None:
    backend = Backend()
    with Project(Path("test_data/test_semantic_parser"), backend) as project:
        project.build()

        # Ensure that the correct pages and assets exist for slug-title mapping
        slugToTitle: Dict[str, str] = cast(
            Dict[str, str], backend.metadata["slugToTitle"]
        )

        assert len(slugToTitle) == 4
        assert slugToTitle["index"] == "Connection Limits and Cluster Tier"
        assert slugToTitle["page1"] == "Print this heading"
        assert slugToTitle["page2"] == "Heading is not at the top for some reason"
        assert slugToTitle["page3"] == ""

        # Ensure that the correct pages and assets exist for toctree
        toctree: List[Any] = cast(List[Any], backend.metadata["toctree"])

        assert len(toctree) == 5
        assert any(node["title"] == "Print this heading" for node in toctree)
        assert any(
            node["title"] == "Connection Limits and Cluster Tier"
            and len(node["children"]) == 2
            for node in toctree
        )

        # Ensure that the correct pages and assets exist for breadcrumbs
        pages: Dict[str, Any] = cast(Dict[str, Any], backend.metadata["pages"])

        assert len(pages) == 3
        assert len(pages["page1"]) == 4
        assert ["index"] in pages["page1"]
        assert ["page3"] in pages["page1"]
        assert ["page2", "page3"] in pages["page1"]
        assert ["index", "page2", "page3"] in pages["page1"]

        assert len(pages["page2"]) == 1
        assert ["index"] in pages["page2"]

        assert len(pages["page3"]) == 2
        assert ["index", "page2"] in pages["page3"]
        assert ["page2"] in pages["page3"]

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, cast, Any
from .gizaparser.published_branches import PublishedBranches
from .types import FileId, Page, Diagnostic, SerializableType
from .parser import Project
import pytest

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


@pytest.fixture
def backend() -> Backend:
    backend = Backend()
    with Project(Path("test_data/test_semantic_parser"), backend) as project:
        project.build()

    return backend


def test_slug_title_mapping(backend: Backend) -> None:
    slug_to_title: Dict[str, str] = cast(
        Dict[str, str], backend.metadata["slugToTitle"]
    )

    assert len(slug_to_title) == 4
    assert slug_to_title["index"] == "Connection Limits and Cluster Tier"
    assert slug_to_title["page1"] == "Print this heading"
    assert slug_to_title["page2"] == "Heading is not at the top for some reason"
    assert slug_to_title["page3"] == ""


def test_toctree(backend: Backend) -> None:
    print(backend.metadata["toctree"])
    assert backend.metadata["toctree"] == {
        "children": [
            {"slug": "page1", "title": "Print this heading"},
            {
                "slug": "page2",
                "title": "Heading is not at the top for some reason",
                "children": [
                    {
                        "title": "MongoDB Connector for Business Intelligence",
                        "url": "https://docs.mongodb.com/bi-connector/current/",
                    },
                    {
                        "slug": "page3",
                        "title": "",
                        "children": [{"slug": "page1", "title": "Print this heading"}],
                    },
                ],
            },
        ],
        "title": "test_data",
        "slug": "/",
    }

def test_breadcrumbs(backend: Backend) -> None:
    # Ensure that the correct pages and assets exist for breadcrumbs
    pages: Dict[str, Any] = cast(Dict[str, Any], backend.metadata["pages"])

    assert len(pages) == 3
    assert len(pages["page1"]) == 2
    assert ["/"] in pages["page1"]
    assert ["/", "page2", "page3"] in pages["page1"]

    assert len(pages["page2"]) == 1
    assert ["/"] in pages["page2"]

    assert len(pages["page3"]) == 1
    assert ["/", "page2"] in pages["page3"]


def test_toctree_order(backend: Backend)
    # Ensure that the correct pages and assets exist for toctree order
    order: List[str] = cast(List[str], backend.metadata["toctreeOrder"])
    assert order == ["/", "page1", "page2", "page3", "page1"]


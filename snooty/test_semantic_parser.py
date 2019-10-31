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

        # Ensure that the correct pages and assets exist
<<<<<<< HEAD
        print(backend.metadata["toctree"])
        toctree: List[Any] = cast(List[Any], backend.metadata["toctree"])
        assert len(toctree) == 4
        assert any(node["title"] == "Print this heading" for node in toctree)
        assert any(
            node["title"] == "Connection Limits and Cluster Tier"
            and len(node["children"]) == 2
            for node in toctree
        )
=======
        toctreeNodes: List[Any] = cast(List[Any], backend.metadata["toctreeNodes"])

        assert len(toctreeNodes) == 14
        assert {"slug": "/tutorial/create-global-cluster"} in toctreeNodes
        assert {
            "title": "Build Aggregation Pipelines",
            "slug": "/data-explorer/cloud-agg-pipeline",
        } in toctreeNodes
>>>>>>> 3b82b2c6e7c18c833593883b7cb14384106a3915

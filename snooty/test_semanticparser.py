import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict
from .parser import Project
from . import rstparser, semanticparser
from .util import ast_dive
from .util_test import check_ast_testing_string
from .types import Diagnostic, ProjectConfig, FileId, Page, Diagnostic, SerializableType, List
from .parser import parse_rst, JSONVisitor

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

def test() -> None:
    backend = Backend()
    with Project(Path("test_data/test_semantic_parser"), backend) as project:
        project.build()
        # Ensure that the correct pages and assets exist
        assert len(backend.metadata) == 4
        assert backend.metadata['test_data/test_semantic_parser/source/index.txt'] == 'Some Title'
        assert backend.metadata['test_data/test_semantic_parser/source/page1.txt'] == 'Another Title'
        assert backend.metadata['test_data/test_semantic_parser/source/page2.txt'] == 'MongoDB Java Driver'
        assert backend.metadata['test_data/test_semantic_parser/source/page3.txt'] == 'MongoDB Server'

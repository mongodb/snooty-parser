import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast, Any, Dict, List
from .types import FileId, Page, Diagnostic
from .parser import Project
from .util import ast_dive

@dataclass
class Backend:
    pages: Dict[FileId, Page] = field(default_factory=dict)
    updates: List[FileId] = field(default_factory=list)

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        pass

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        self.pages[page_id] = page
        self.updates.append(page_id)

    def on_delete(self, page_id: FileId) -> None:
        pass


def test() -> None:
    backend = Backend()
    n_threads = len(threading.enumerate())
    with Project(Path("test_data/merge_conflict"), backend) as project:
        project.build()
        print(project)
        # Ensure that filesystem monitoring threads have been started
        assert len(threading.enumerate()) > n_threads

        # Ensure that the correct pages and assets exist
        index_id = FileId("index.txt")
        print(backend.pages.keys())
        assert list(backend.pages.keys()) == [index_id]
        code_length = 0
        checksums = []
        index = backend.pages[index_id]


    # Ensure that any filesystem monitoring threads have been shut down
    #assert len(threading.enumerate()) == n_threads

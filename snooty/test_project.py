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
    with Project(Path('test_data/test_project'), backend) as project:
        project.build()

        # Ensure that filesystem monitoring threads have been started
        assert len(threading.enumerate()) > n_threads

        # Ensure that the correct pages and assets exist
        index_id = FileId('index.txt')
        assert list(backend.pages.keys()) == [index_id]
        code_length = 0
        checksums = []
        index = backend.pages[index_id]
        assert len(index.static_assets) == 2
        assert not index.pending_tasks
        for node in ast_dive(index.ast):
            if node['type'] == 'code':
                code_length += len(cast(str, node['value']))
            elif node['type'] == 'directive' and node['name'] == 'figure':
                checksums.append(cast(Any, node['options'])['checksum'])
        assert code_length == 345
        assert checksums == ['10e351828f156afcafc7744c30d7b2564c6efba1ca7c55cac59560c67581f947']
        assert backend.updates == [index_id]

        # Confirm that modifying an asset reparses the dependent files
        literalinclude_id = FileId('driver-examples/DocumentationExamples.cs')
        with project._lock:
            assert list(project._project._expensive_operation_cache.
                        get_versions(literalinclude_id)) == [1, 1]
        with project.config.source_path.joinpath(literalinclude_id).open(mode='r+b') as f:
            text = f.read()
            f.seek(0)
            f.truncate(0)
            f.write(text)
            f.flush()
        time.sleep(0.1)
        with project._lock:
            assert list(project._project._expensive_operation_cache.
                        get_versions(literalinclude_id)) == [2, 2]
        assert backend.updates == [index_id, index_id]

        figure_id = FileId('images/compass-create-database.png')
        with project._lock:
            assert list(project._project._expensive_operation_cache.
                        get_versions(figure_id)) == [1]
        with project.config.source_path.joinpath(figure_id).open(mode='r+b') as f:
            text = f.read()
            f.seek(0)
            f.truncate(0)
            f.write(text)
            f.flush()
        time.sleep(0.1)
        with project._lock:
            assert list(project._project._expensive_operation_cache.
                        get_versions(figure_id)) == [2]

        # Ensure that the page has been reparsed 3 times
        assert backend.updates == [index_id, index_id, index_id]

    # Ensure that any filesystem monitoring threads have been shut down
    assert len(threading.enumerate()) == n_threads

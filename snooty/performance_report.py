import sys
import logging
from pathlib import Path
from typing import Dict, List
from .parser import Project
from .types import Diagnostic, Page, FileId, SerializableType, BuildIdentifierSet
from .util import PerformanceLogger

logging.basicConfig(level=logging.INFO)


class Backend:
    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        pass

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        pass

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        pass

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        pass


def main() -> None:
    backend = Backend()
    root_path = Path(sys.argv[1])
    project = Project(root_path, backend, {})

    n_runs = 3
    for i in range(n_runs):
        print(f"run {i+1}/{n_runs}")
        project.build(1)

    for name, time in PerformanceLogger.singleton().times().items():
        print(f"{name}:{time:10.4}")


if __name__ == "__main__":
    main()

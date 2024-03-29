import logging
import sys
from pathlib import Path

from .parser import Project
from .util import PerformanceLogger
from .util_test import BackendTestResults

logging.basicConfig(level=logging.INFO)


def main() -> None:
    root_path = Path(sys.argv[1])

    n_runs = 3
    for i in range(n_runs):
        backend = BackendTestResults()
        project = Project(root_path, backend, {})

        print(f"run {i+1}/{n_runs}")
        project.build(1)
        with PerformanceLogger.singleton().start("serialization"):
            for page in backend.pages.values():
                page.ast.serialize()

    PerformanceLogger.singleton().print()


if __name__ == "__main__":
    main()

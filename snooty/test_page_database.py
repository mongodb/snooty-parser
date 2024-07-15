from pathlib import Path

from .n import FileId
from .page_database import PageDatabase
from .parser import Project
from .test_project import Backend


def test_persistence() -> None:
    backend = Backend()
    project = Project(Path("test_data/test_project_embedding_includes/"), backend, {})
    project.build()

    with project._lock:
        persisted = project._project.pages.persist()
        loaded = PageDatabase.from_persisted(persisted)
        assert loaded == project._project.pages

        loaded._parsed[FileId("index.txt")][0].ast.children[0].span = (2,)
        assert loaded != project._project.pages

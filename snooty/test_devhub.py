from pathlib import Path
from typing import Dict
from .types import BuildIdentifierSet, FileId, SerializableType
from .parser import Project
from .test_project import Backend
import pytest


@pytest.fixture
def backend() -> Backend:
    backend = Backend()
    build_identifiers: BuildIdentifierSet = {}
    with Project(Path("test_data/test_devhub"), backend, build_identifiers) as project:
        project.build()

    return backend


def test_queryable_fields(backend: Backend) -> None:
    page_id = FileId("index.txt")
    page = backend.pages[page_id]
    query_fields: Dict[str, SerializableType] = page.query_fields
    assert query_fields is not None
    assert query_fields["author"] == "Eliot Horowitz"
    assert query_fields["tags"] == ["foo", "bar", "baz"]
    assert query_fields["languages"] == ["nodejs", "java"]
    assert query_fields["products"] == ["Realm", "MongoDB"]

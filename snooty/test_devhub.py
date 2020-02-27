from pathlib import Path
from typing import cast, Any, Dict, List
from .types import BuildIdentifierSet, FileId, SerializableType
from .parser import Project
from .test_project import Backend
from .util_test import check_ast_testing_string
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
    assert query_fields["pubdate"] == "January 31, 2019"
    assert query_fields["updated-date"] == "February 2, 2019"
    assert query_fields["atf-image"] == "/img/heros/how-to-write-an-article.png"
    assert query_fields["type"] == "article, quickstart, how-to, video, live"
    assert query_fields["level"] == "beginner, intermediate, advanced"

    related = cast(Any, query_fields["related"])
    check_ast_testing_string(
        related[0], "<literal><text>list of related articles</text></literal>"
    )
    check_ast_testing_string(
        related[1], """<role name="doc" target="/path/to/article"></role>"""
    )
    check_ast_testing_string(
        related[2], """<literal><text>:doc:`/path/to/other/article`</text></literal>"""
    )

    meta_description = cast(Any, query_fields["meta-description"])
    check_ast_testing_string(
        meta_description[0],
        "<paragraph><text>meta description (160 characters or fewer)</text></paragraph>",
    )

    title = cast(Any, query_fields["title"])
    assert len(title) == 1
    check_ast_testing_string(title[0], "<text>h1 Article Title</text>")


def test_page_groups(backend: Backend) -> None:
    """Test that page groups are correctly filtered and cleaned."""
    page_groups: Dict[str, List[str]] = cast(Any, backend.metadata["pageGroups"])
    assert page_groups == {"Group 1": ["index", "index"]}

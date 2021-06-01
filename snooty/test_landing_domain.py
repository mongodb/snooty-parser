from pathlib import Path

import pytest

from . import n
from .parser import Project
from .test_project import Backend
from .types import BuildIdentifierSet, FileId
from .util_test import check_ast_testing_string


@pytest.fixture
def backend() -> Backend:
    backend = Backend()
    build_identifiers: BuildIdentifierSet = {}
    with Project(
        Path("test_data/test_landing_domain"), backend, build_identifiers
    ) as project:
        project.build()

    return backend


# Test all directives exclusive to the landing domain
def test_landing_directives(backend: Backend) -> None:
    page_id = FileId("index.txt")
    page = backend.pages[page_id]
    assert len(page.static_assets) == 0

    ast = page.ast
    section = ast.children[0]
    assert isinstance(section, n.Section)

    cta = section.children[1]
    check_ast_testing_string(
        cta,
        """<directive domain="landing" name="cta"><paragraph><reference refuri="https://docs.mongodb.com/manual/introduction/"><text>Read the Introduction to MongoDB</text></reference></paragraph></directive>""",
    )

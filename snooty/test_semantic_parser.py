from pathlib import Path
from typing import Dict, List, cast, Any
from .types import BuildIdentifierSet, FileId, SerializableType
from .parser import Project
from .test_project import Backend
import pytest


ROOT_PATH = Path("test_data")


@pytest.fixture
def backend() -> Backend:
    backend = Backend()
    build_identifiers: BuildIdentifierSet = {"commit_hash": "123456"}
    with Project(
        Path("test_data/test_semantic_parser"), backend, build_identifiers
    ) as project:
        project.build()

    return backend


def test_slug_title_mapping(backend: Backend) -> None:
    # Ensure that the correct pages and assets exist
    slugToTitle: Dict[str, List[Dict[str, SerializableType]]] = cast(
        Dict[str, List[Dict[str, SerializableType]]], backend.metadata["slugToTitle"]
    )

    # page3 is not included in slug-title mapping because it lacks a heading.
    assert len(slugToTitle) == 4
    assert slugToTitle["index"][0]["value"] == "Connection Limits and Cluster Tier"
    assert slugToTitle["page1"][0]["value"] == "Print this heading"
    assert (
        slugToTitle["page2"][0]["value"] == "Heading is not at the top for some reason"
    )
    assert slugToTitle["page4"][0]["value"] == "Skip includes"


def test_expand_includes(backend: Backend) -> None:
    page4_id = FileId("page4.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page4_id].ast)
    children = cast(Dict[str, Any], ast["children"][0])
    assert children["name"] == "include"
    assert len(children["children"]) > 1
    assert children["children"] == [
        {
            "type": "target",
            "position": {"start": {"line": 1}},
            "ids": ["connection-limits"],
            "children": [],
        },
        {
            "type": "section",
            "position": {"start": {"line": 5}},
            "children": [
                {
                    "type": "heading",
                    "position": {"start": {"line": 5}},
                    "id": "skip-includes",
                    "children": [
                        {
                            "type": "text",
                            "position": {"start": {"line": 5}},
                            "value": "Skip includes",
                        }
                    ],
                },
                {
                    "type": "directive",
                    "position": {"start": {"line": 7}},
                    "domain": "",
                    "name": "default-domain",
                    "argument": [
                        {
                            "type": "text",
                            "position": {"start": {"line": 7}},
                            "value": "mongodb",
                        }
                    ],
                    "children": [],
                },
                {
                    "type": "directive",
                    "position": {"start": {"line": 9}},
                    "domain": "",
                    "name": "meta",
                    "argument": [],
                    "options": {"keywords": "connect"},
                    "children": [],
                },
            ],
        },
    ]


def test_validate_ref_targets(backend: Backend) -> None:
    page_id = FileId("refrole.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)
    paragraph = cast(Dict[str, Any], ast["children"][0])
    ref_role = paragraph["children"][0]
    assert ref_role["type"] == "ref_role"
    assert "url" in ref_role
    assert (
        ref_role["url"]
        == "https://docs.mongodb.com/manual/reference/configuration-options/#net.port"
    )

    diagnostics = backend.diagnostics[page_id]
    assert len(diagnostics) == 2
    assert all(["Target" in diagnostic.message for diagnostic in diagnostics])


def test_toctree(backend: Backend) -> None:
    assert backend.metadata["toctree"] == {
        "children": [
            {
                "children": [],
                "options": {"drawer": True},
                "slug": "page1",
                "title": [
                    {
                        "position": {"start": {"line": 4}},
                        "type": "text",
                        "value": "Print this heading",
                    }
                ],
            },
            {
                "options": {"drawer": False},
                "slug": "page2",
                "title": [
                    {
                        "position": {"start": {"line": 19}},
                        "type": "text",
                        "value": "Heading is not at the top for some reason",
                    }
                ],
                "children": [
                    {
                        "children": [],
                        "title": "MongoDB Connector for Business Intelligence",
                        "url": "https://docs.mongodb.com/bi-connector/current/",
                    },
                    {
                        "children": [],
                        "options": {"drawer": False},
                        "slug": "page3",
                        "title": None,
                    },
                ],
            },
        ],
        "title": "test_data",
        "slug": "/",
    }


def test_breadcrumbs(backend: Backend) -> None:
    # Ensure that the correct pages and assets exist for breadcrumbs
    pages: Dict[str, Any] = cast(Dict[str, Any], backend.metadata["parentPaths"])

    assert len(pages) == 3
    assert len(pages["page1"]) == 0

    assert len(pages["page2"]) == 0

    assert len(pages["page3"]) == 1
    assert pages["page3"] == ["page2"]


def test_toctree_order(backend: Backend) -> None:
    # Ensure that the correct pages and assets exist for toctree order
    order: List[str] = cast(List[str], backend.metadata["toctreeOrder"])
    assert order == ["/", "page1", "page2", "page3"]

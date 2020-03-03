from pathlib import Path
from typing import Dict, List, cast, Any
from .types import BuildIdentifierSet, FileId, SerializableType
from .parser import Project
from .test_project import Backend
from .util_test import ast_to_testing_string, check_ast_testing_string
import pytest


ROOT_PATH = Path("test_data")


@pytest.fixture(scope="module")
def backend() -> Backend:
    backend = Backend()
    build_identifiers: BuildIdentifierSet = {"commit_hash": "123456"}
    with Project(
        Path("test_data/test_postprocessor"), backend, build_identifiers
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
            "domain": "std",
            "name": "label",
            "target": "connection-limits",
            "children": [
                {
                    "type": "target_ref_title",
                    "position": {"start": {"line": 5}},
                    "children": [
                        {
                            "type": "text",
                            "position": {"start": {"line": 5}},
                            "value": "Skip includes",
                        }
                    ],
                }
            ],
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

    # Assert that targets found in intersphinx inventories are correctly resolved
    paragraph = cast(Dict[str, Any], ast["children"][0])
    ref_role = paragraph["children"][0]
    # print(ast_to_testing_string(ref_role))
    check_ast_testing_string(
        ref_role,
        """<ref_role
        domain="mongodb"
        name="setting"
        target="net.port"
        url="https://docs.mongodb.com/manual/reference/configuration-options/#net.port">
        <literal><text>net.port</text></literal>
        </ref_role>""",
    )

    # Assert that local targets are correctly resolved
    paragraph = cast(Dict[str, Any], ast["children"][3])
    ref_role = paragraph["children"][1]
    # print(ast_to_testing_string(ref_role))
    check_ast_testing_string(
        ref_role,
        """<ref_role
        domain="mongodb"
        name="method"
        target="amethod"
        fileid="index">
        <literal><text>amethod()</text></literal>
        </ref_role>""",
    )

    # Assert that labels are correctly resolved
    paragraph = cast(Dict[str, Any], ast["children"][1])
    ref_role = paragraph["children"][-2]
    print(ast_to_testing_string(ref_role))
    check_ast_testing_string(
        ref_role,
        """<ref_role
        domain="std"
        name="label"
        target="global-writes-zones"
        fileid="index"><emphasis><text>Global</text></emphasis><text> Writes Zones</text></ref_role>""",
    )

    # Assert that local targets with a prefix correctly resolved
    paragraph = cast(Dict[str, Any], ast["children"][4])
    ref_role = paragraph["children"][1]
    print(ast_to_testing_string(ref_role))
    check_ast_testing_string(
        ref_role,
        """<ref_role
        domain="mongodb"
        name="binary"
        target="bin.mongod"
        url="https://docs.mongodb.com/manual/reference/program/mongod/#bin.mongod">
        <literal><text>bin.mongod</text></literal>
        </ref_role>""",
    )

    # Check that undeclared targets raise an error
    diagnostics = backend.diagnostics[page_id]
    assert len(diagnostics) == 1
    assert (
        "Target" in diagnostics[0].message
        and "global-writes-collections" in diagnostics[0].message
    )


def test_role_explicit_title(backend: Backend) -> None:
    page_id = FileId("index.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)

    # Assert that ref_roles with an explicit title work
    paragraph = cast(Any, ast)["children"][1]["children"][4]["children"][1]["children"][
        2
    ]
    ref_role = paragraph["children"][1]
    print(ast_to_testing_string(ref_role))
    check_ast_testing_string(
        ref_role,
        """<ref_role
        domain="std"
        name="label"
        target="global-writes-zones"
        fileid="index">
        <text>explicit title</text>
        </ref_role>""",
    )


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
        "title": "untitled",
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


def test_target_titles(backend: Backend) -> None:
    page_id = FileId("index.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)

    # Assert that titles are correctly located
    section = cast(Dict[str, Any], ast)["children"][1]["children"][4]
    target1 = section["children"][-2]
    target2 = section["children"][-1]
    check_ast_testing_string(
        target1,
        """<target domain="std" name="label" target="a-sibling-node"><target_ref_title><text>Testing Sibling Nodes</text></target_ref_title></target>""",
    )
    check_ast_testing_string(
        target2,
        """<target domain="std" name="label" target="another-target-for-a-sibling-node"><target_ref_title><text>Testing Sibling Nodes</text></target_ref_title></target>""",
    )


def test_substitutions(backend: Backend) -> None:
    # Test substitutions as defined in snooty.toml
    page_id = FileId("page3.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)

    paragraph = cast(Dict[str, Any], ast["children"][2])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="service"><text>Atlas</text></substitution_reference>""",
    )

    substitution_reference = paragraph["children"][2]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="global-write-clusters"><text>Global </text><emphasis><text>Clusters</text></emphasis></substitution_reference>""",
    )

    # Verify that same substitution can be used multiple times on the same page
    paragraph = cast(Dict[str, Any], ast["children"][4])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="service"><text>Atlas</text></substitution_reference>""",
    )

    # Test substitution of empty string
    paragraph = cast(Dict[str, Any], ast["children"][3])
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="blank"></substitution_reference>""",
    )

    # Test substitutions defined in-page
    paragraph = cast(Dict[str, Any], ast["children"][6])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="sub"><text>Diff</text></substitution_reference>""",
    )

    page_id = FileId("page4.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)

    substution_definition = cast(Dict[str, Any], ast["children"][2])
    check_ast_testing_string(
        substution_definition,
        """<substitution_definition name="sub"><text>Substitution</text></substitution_definition>""",
    )

    paragraph = cast(Dict[str, Any], ast["children"][1])
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="sub"><text>Substitution</text></substitution_reference>""",
    )

    paragraph = cast(Dict[str, Any], ast["children"][3])
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="sub"><text>Substitution</text></substitution_reference>""",
    )

    # Test substitution used in an include
    page_id = FileId("page5.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)
    paragraph = cast(Dict[str, Any], ast["children"][1])
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="included-sub"><text>ack</text></substitution_reference>""",
    )

    paragraph = cast(Dict[str, Any], ast["children"][3])
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="included-sub"><text>included substitution</text></substitution_reference>""",
    )

    include = cast(Dict[str, Any], ast["children"][2])
    paragraph = include["children"][1]
    substitution_reference = paragraph["children"][1]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="use-in-include"><text>Yes</text></substitution_reference>""",
    )

    # Test circular substitutionos
    page_id = FileId("circular.txt")

    diagnostics = backend.diagnostics[page_id]
    assert len(diagnostics) == 4

    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)
    paragraph = cast(Dict[str, Any], ast["children"][2])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="operation"><substitution_reference name="add"></substitution_reference></substitution_reference>""",
    )

    paragraph = cast(Dict[str, Any], ast["children"][7])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="baz"><substitution_reference name="foo"></substitution_reference></substitution_reference>""",
    )

    paragraph = cast(Dict[str, Any], ast["children"][3])
    check_ast_testing_string(
        paragraph, "<paragraph><text>Testing content here.</text></paragraph>"
    )

    # Test nested substitutions
    page_id = FileId("nested.txt")
    ast = cast(Dict[str, List[SerializableType]], backend.pages[page_id].ast)
    paragraph = cast(Dict[str, Any], ast["children"][2])
    substitution_reference = paragraph["children"][0]
    check_ast_testing_string(
        substitution_reference,
        """<substitution_reference name="weather"><substitution_reference name="sun"><text>sun</text></substitution_reference></substitution_reference>""",
    )

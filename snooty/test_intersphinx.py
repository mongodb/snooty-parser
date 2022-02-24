import os
import shutil
from pathlib import Path

import requests
from pytest import raises

from . import n
from .diagnostics import FetchError
from .intersphinx import Inventory, TargetDefinition, fetch_inventory
from .parser import Project
from .target_database import TargetDatabase
from .test_project import Backend
from .types import FileId
from .util_test import make_test

TESTING_CACHE_DIR = Path(f".intersphinx_cache-{os.getpid()}")
INVENTORY_URL = "https://docs.mongodb.com/manual/objects.inv"
EXPECTED_INVENTORY_FILENAME = r"https%3A%2F%2Fdocs.mongodb.com%2Fmanual%2Fobjects.inv"
INVENTORY_PATH = TESTING_CACHE_DIR.joinpath(EXPECTED_INVENTORY_FILENAME)

# Skip footnote labels during validation. Yes, these are all labels created
# by footnotes.
IGNORE_TARGETS = {
    "std:label:hashes",
    "std:label:update-correctness",
    "std:label:timestamps",
    "std:label:genindex",
    "std:label:sql-aggregation-equivalents",
    "std:label:modindex",
    "std:label:queries",
    "std:label:search",
    "std:label:authrequired",
    "std:label:objid",
}


def test_fetch() -> None:
    try:
        try:
            shutil.rmtree(TESTING_CACHE_DIR)
        except FileNotFoundError:
            pass
        inventory = fetch_inventory(INVENTORY_URL, TESTING_CACHE_DIR)
        assert inventory.base_url == "https://docs.mongodb.com/manual/"
        assert len(inventory) > 1000
        assert INVENTORY_PATH.is_file()
        stat = INVENTORY_PATH.stat()

        try:
            original_requests_get = requests.get

            def get_fail(*args: object, **kwargs: object) -> object:
                assert False, "Made a get request but shouldn't have"

            requests.get = get_fail  # type: ignore
            # Make sure that an immediate followup request does not change the mtime
            fetch_inventory(INVENTORY_URL, TESTING_CACHE_DIR)
        finally:
            requests.get = original_requests_get

        assert INVENTORY_PATH.is_file()
        stat2 = INVENTORY_PATH.stat()
        assert stat.st_mtime_ns == stat2.st_mtime_ns
    finally:
        shutil.rmtree(TESTING_CACHE_DIR, ignore_errors=True)

    # Now try without caching
    inventory = fetch_inventory(INVENTORY_URL, None)
    assert inventory.base_url == "https://docs.mongodb.com/manual/"
    assert len(inventory) > 1000


def test_intersphinx_generation() -> None:
    with open("test_data/test_intersphinx/manual.inv", "rb") as f:
        inventory_bytes = f.read()

    inventory = Inventory.parse(INVENTORY_URL, inventory_bytes)
    inventory_bytes = inventory.dumps("", "")
    inventory2 = Inventory.parse(INVENTORY_URL, inventory_bytes)

    assert inventory == inventory2

    # Ensure that we can't pass a string with newlines to dumps
    with raises(ValueError):
        inventory.dumps("foo\nbar", "")

    with raises(ValueError):
        inventory.dumps("", "foo\nbar")


def test_dump_target_database() -> None:
    backend = Backend()
    with Project(Path("test_data/test_intersphinx"), backend, {}) as project:
        project.build()
        with project._lock:
            generated_inventory = project._project.targets.generate_inventory(
                INVENTORY_URL
            )

    with open("test_data/test_intersphinx/ecosystem.inv", "rb") as f:
        reference_inventory = Inventory.parse(INVENTORY_URL, f.read())

    assert (len(reference_inventory.targets) - len(IGNORE_TARGETS)) == len(
        generated_inventory.targets
    )

    for target_name, generated_definition in generated_inventory.targets.items():
        reference_definition = reference_inventory.targets[target_name]
        # Skip odd definitions
        if not reference_definition.uri:
            continue

        # We don't follow Sphinx's element ID convention, so patch our element ID's
        # for the following comparison
        if "#" in generated_definition.uri:
            new_uri = (
                generated_definition.uri.split("#", 1)[0]
                + "#"
                + reference_definition.uri.rsplit("#", 1)[1]
            )
            new_uri_base = (
                generated_definition.uri_base.split("#", 1)[0]
                + "#"
                + reference_definition.uri_base.rsplit("#", 1)[1]
            )
            generated_definition = generated_definition._replace(
                uri=new_uri, uri_base=new_uri_base
            )

        assert reference_definition == generated_definition


def test_target_strange_fields() -> None:
    db = TargetDatabase()

    # Ensure that a weird target with a colon does not crash inventory generation
    db.define_local_target("std", "label", ["foo:bar"], FileId("foo"), [], "bar")
    inventory = db.generate_inventory("")

    # Now corrupt the domain:role name pair to ensure we don't crash
    good_role_name = "std:label:foo:bar"
    weird_role_name = "std:lab:el:foo:bar"
    inventory.targets[weird_role_name] = inventory.targets[good_role_name]._replace(
        role=("std", "lab:el")
    )
    del inventory.targets[good_role_name]
    inventory_bytes = inventory.dumps("", "")
    Inventory.parse("", inventory_bytes)


def test_targets() -> None:
    db = TargetDatabase()

    db.define_local_target(
        "std",
        "option",
        ["--maxVarcharLength", "mongosqld.--maxVarcharLength"],
        FileId("reference/mongosqld.txt"),
        [n.Text(span=(7,), value="mongosqld --maxVarcharLength")],
        "std-option-mongosqld.--maxVarcharLength",
    )

    db.define_local_target(
        "std",
        "label",
        ["a-label-on-index"],
        FileId("index.txt"),
        [n.Text(span=(7,), value="A Label on Index")],
        "std-label-a-label-on-index",
    )

    db.define_local_target(
        "std",
        "label",
        ["a-label-on-index-2"],
        FileId("reference/index.txt"),
        [n.Text(span=(7,), value="A Label on Index 2")],
        "std-label-a-label-on-index-2",
    )

    inventory = db.generate_inventory("")
    inventory = Inventory.parse("", inventory.dumps("", ""))
    assert inventory.targets == {
        "std:option:mongosqld.--maxVarcharLength": TargetDefinition(
            name="mongosqld.--maxVarcharLength",
            role=("std", "option"),
            priority=-1,
            uri_base="reference/mongosqld/#std-option-mongosqld.--maxVarcharLength",
            uri="reference/mongosqld/#std-option-mongosqld.--maxVarcharLength",
            display_name="mongosqld --maxVarcharLength",
        ),
        "std:label:a-label-on-index": TargetDefinition(
            name="a-label-on-index",
            role=("std", "label"),
            priority=-1,
            uri_base="#std-label-a-label-on-index",
            uri="#std-label-a-label-on-index",
            display_name="A Label on Index",
        ),
        "std:label:a-label-on-index-2": TargetDefinition(
            name="a-label-on-index-2",
            role=("std", "label"),
            priority=-1,
            uri_base="reference/index/#std-label-a-label-on-index-2",
            uri="reference/index/#std-label-a-label-on-index-2",
            display_name="A Label on Index 2",
        ),
    }


def test_fetch_failure() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test_fetch_failure"
intersphinx = ["booglygoogly not a real URL"]
""",
            Path("source/index.txt"): "",
        }
    ) as result:
        assert [type(diag) for diag in result.diagnostics[FileId("snooty.toml")]] == [
            FetchError
        ]

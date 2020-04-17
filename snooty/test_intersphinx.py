import shutil
from pathlib import Path
from pytest import raises
from .intersphinx import fetch_inventory, Inventory
from .parser import Project
from .test_project import Backend

TESTING_CACHE_DIR = Path(".intersphinx_cache")
INVENTORY_URL = "https://docs.mongodb.com/manual/objects.inv"
EXPECTED_INVENTORY_FILENAME = "docsmongodbcommanualobjectsinv"
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

        # Make sure that an immediate followup request does not change the mtime
        fetch_inventory(INVENTORY_URL, TESTING_CACHE_DIR)
        assert INVENTORY_PATH.is_file()
        stat2 = INVENTORY_PATH.stat()

        assert stat.st_mtime_ns == stat2.st_mtime_ns
    finally:
        shutil.rmtree(TESTING_CACHE_DIR, ignore_errors=True)


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

        assert reference_definition == generated_definition

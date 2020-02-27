import shutil
from pathlib import Path
from .intersphinx import fetch_inventory

TESTING_CACHE_DIR = Path(".intersphinx_cache")
INVENTORY_URL = "https://docs.mongodb.com/manual/objects.inv"
EXPECTED_INVENTORY_FILENAME = "docsmongodbcommanualobjectsinv"
INVENTORY_PATH = TESTING_CACHE_DIR.joinpath(EXPECTED_INVENTORY_FILENAME)


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

        # XXX: Workaround the new CDN ignoring If-Modified-Since. Hopefully we can
        # re-enable this assertion soon.
        # assert stat.st_mtime_ns == stat2.st_mtime_ns
    finally:
        shutil.rmtree(TESTING_CACHE_DIR, ignore_errors=True)

"""Intersphinx inventories allow different Sphinx projects to refer to targets
   defined in other projects, and export their targets to other projects.

   This module is responsible for loading and parsing these inventories."""

import re
import logging
import datetime
import urllib.parse
import zlib
from dataclasses import dataclass, field
from email.utils import formatdate
from time import mktime
from pathlib import Path
from typing import Dict, Tuple, NamedTuple, Optional
import requests

__all__ = ("TargetDefinition", "Inventory")
DEFAULT_CACHE_DIR = Path.home().joinpath(".cache", "snooty")
INVENTORY_PATTERN = re.compile(r"(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)")
logger = logging.Logger(__name__)


class TargetDefinition(NamedTuple):
    """A definition of a reStructuredText link target."""

    name: str
    role: Tuple[str, str]
    priority: int
    uri: str
    display_name: str


@dataclass
class Inventory:
    """An inventory of a project's link target definitions."""

    base_url: str
    targets: Dict[str, TargetDefinition] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.targets)

    def __contains__(self, target: str) -> bool:
        return target in self.targets

    def __getitem__(self, target: str) -> TargetDefinition:
        return self.targets[target]

    @classmethod
    def parse(cls, base_url: str, text: bytes) -> "Inventory":
        """Parse an intersphinx inventory from the given URL prefix and raw inventory contents."""
        # Intersphinx always has 4 lines of ASCII before the payload.
        start_index = 0
        for i in range(4):
            start_index = text.find(b"\n", start_index) + 1

        decompressed = str(zlib.decompress(text[start_index:]), "utf-8")
        inventory = cls(base_url)
        for line in decompressed.split("\n"):
            if not line.strip():
                continue

            match = INVENTORY_PATTERN.match(line.rstrip())
            if match is None:
                logger.debug(f"Invalid intersphinx line: {line}")
                continue

            name, domain_and_role, raw_priority, uri, dispname = match.groups()

            if uri.endswith("$"):
                uri = uri[:-1] + name

            # The spec says that only {dispname} can contain spaces. In practice, this is a lie.
            # Just silently skip invalid lines.
            try:
                priority = int(raw_priority)
            except ValueError:
                logger.debug(f"Invalid priority in intersphinx inventory: {line}")
                continue

            domain, role = domain_and_role.split(":", 2)

            # "If {dispname} is identical to {name}, it is stored as -"
            if dispname == "-":
                dispname = name

            target_definition = TargetDefinition(
                name, (domain, role), priority, uri, dispname
            )
            inventory.targets[f"{domain_and_role}:{name}".lower()] = target_definition

        return inventory


def fetch_inventory(url: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Inventory:
    """Fetch an intersphinx inventory, or use a locally cached copy if it is still valid."""
    logger.debug(f"Fetching inventory: {url}")

    base_url = url.rsplit("/", 1)[0]
    base_url.rstrip("/")
    base_url += "/"

    # Make our user's cache directory if it doesn't exist
    parsed_url = urllib.parse.urlparse(url)
    filename = "".join(
        char for char in parsed_url.netloc + parsed_url.path if char.isalnum()
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = cache_dir.joinpath(filename)

    # Only re-request if more than an hour old
    request_headers: Dict[str, str] = {}
    mtime: Optional[datetime.datetime] = None
    try:
        mtime = datetime.datetime.fromtimestamp(inventory_path.stat().st_mtime)
    except FileNotFoundError:
        pass

    if mtime is not None:
        if (datetime.datetime.now() - mtime) < datetime.timedelta(hours=1):
            request_headers["If-Modified-Since"] = formatdate(mktime(mtime.timetuple()))

    res = requests.get(url, headers=request_headers)
    res.raise_for_status()
    if res.status_code == 304:
        return Inventory.parse(base_url, inventory_path.read_bytes())

    with open(inventory_path, "wb") as f:
        f.write(res.content)

    return Inventory.parse(base_url, res.content)

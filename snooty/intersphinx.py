"""Intersphinx inventories allow different Sphinx projects to refer to targets
   defined in other projects, and export their targets to other projects.

   This module is responsible for loading and parsing these inventories."""

import logging
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple, NamedTuple
from .download_cache import download_url, DEFAULT_CACHE_DIR

__all__ = ("TargetDefinition", "Inventory")
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

            name, domain_and_role, raw_priority, uri, dispname = line.split(None, 4)

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
            inventory.targets[f"{domain_and_role}:{name}"] = target_definition

        return inventory


def fetch_inventory(url: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Inventory:
    """Fetch an intersphinx inventory, or use a locally cached copy if it is still valid."""
    logger.debug(f"Fetching inventory: {url}")

    base_url, cache_entry_path, content = download_url(url, cache_dir)
    return Inventory.parse(base_url, content)

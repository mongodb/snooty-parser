import copy
import enum
import logging
import threading
import urllib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, List, NamedTuple, Optional, Sequence, Tuple, Union

import requests.exceptions
from typing_extensions import Protocol

from . import intersphinx, n, specparser
from .cache import Cache
from .types import FileId, ProjectConfig, normalize_target

logger = logging.getLogger(__name__)

#: Indicates the target protocol of a target: either a file local to the
#: current project, or a URL (from an intersphinx inventory).
TargetType = enum.Enum("TargetType", ("fileid", "url"))


@dataclass
class TargetDatabase:
    """A database of targets known to this project."""

    class ExternalResult(NamedTuple):
        url: str
        canonical_target_name: str
        title: Sequence[n.InlineNode]

    class InternalResult(NamedTuple):
        result: Tuple[str, str]
        canonical_target_name: str
        title: Sequence[n.InlineNode]

    Result = Union[ExternalResult, InternalResult]

    class LocalDefinition(NamedTuple):
        canonical_name: str
        fileid: FileId
        title: Sequence[n.InlineNode]
        html5_id: str

    intersphinx_inventories: Dict[str, intersphinx.Inventory] = field(
        default_factory=dict
    )
    local_definitions: DefaultDict[str, List[LocalDefinition]] = field(
        default_factory=lambda: defaultdict(list)
    )

    lock: threading.Lock = field(default_factory=threading.Lock)

    def __getitem__(self, key: str) -> Sequence["TargetDatabase.Result"]:
        key = normalize_target(key)
        results: List[TargetDatabase.Result] = []

        spec = specparser.Spec.get()

        with self.lock:
            # Check to see if the target is defined locally
            try:
                results.extend(
                    TargetDatabase.InternalResult(
                        (fileid.without_known_suffix, html5_id),
                        canonical_target_name,
                        title,
                    )
                    for canonical_target_name, fileid, title, html5_id in self.local_definitions[
                        key
                    ]
                )
            except KeyError:
                pass

            # Get URL from intersphinx inventories
            for inventory in self.intersphinx_inventories.values():
                entry = inventory.get(key)

                # Sphinx, at least older versions, have a habit of lower-casing its intersphinx
                # inventory sections. Try that.
                if not entry:
                    entry = inventory.get(key.lower())

                # FIXME: temporary until DOP-2345 is complete
                if not entry and key.startswith("mongodb:php"):
                    entry = inventory.get(key.replace("\\\\", "\\"))

                if entry:
                    base_url = inventory.base_url
                    url = urllib.parse.urljoin(base_url, entry.uri)

                    display_name = entry.display_name
                    if display_name is None:
                        display_name = entry.name

                        display_name = spec.strip_prefix_from_name(
                            entry.domain_and_role, display_name
                        )

                    title: List[n.InlineNode] = [n.Text((-1,), display_name)]
                    results.append(
                        TargetDatabase.ExternalResult(url, entry.name, title)
                    )

        return results

    def define_local_target(
        self,
        domain: str,
        name: str,
        targets: Sequence[str],
        pageid: FileId,
        title: Sequence[n.InlineNode],
        html5_id: str,
    ) -> None:
        # If multiple target names are given, prefer placing the one with the most periods
        # into referring RefRole nodes. This is an odd heuristic, but should work for now.
        # e.g. if a RefRole links to "-v", we want it to get normalized to "mongod.-v" if that's
        # what gets resolved.
        canonical_target_name = max(targets, key=lambda x: x.count("."))

        with self.lock:
            for target in targets:
                target = normalize_target(target)
                key = f"{domain}:{name}:{target}"
                self.local_definitions[key].append(
                    TargetDatabase.LocalDefinition(
                        canonical_target_name, pageid, title, html5_id
                    )
                )

    def reset(self, config: "ProjectConfig") -> Sequence[Tuple[str, str]]:
        """Reset this database to a "blank" state with intersphinx inventories defined by
        the given ProjectConfig instance."""
        failed_requests = []
        logger.debug("Loading %s intersphinx inventories", len(config.intersphinx))
        fetched_inventories: Dict[str, intersphinx.Inventory] = {}

        for url in config.intersphinx:
            try:
                fetched_inventories[url] = intersphinx.fetch_inventory(url)
            except requests.exceptions.RequestException as err:
                failed_requests.append((url, str(err)))

        with self.lock:
            self.intersphinx_inventories = fetched_inventories
            self.local_definitions.clear()

        return failed_requests

    def generate_inventory(self, base_url: str) -> intersphinx.Inventory:
        targets: Dict[str, intersphinx.TargetDefinition] = {}
        with self.lock:
            for key, definitions in self.local_definitions.items():
                if not definitions:
                    continue

                definition = definitions[0]
                uri = definition.fileid.as_dirhtml()
                dispname: Optional[str] = "".join(
                    node.get_text() for node in definition.title
                )
                domain, role_name, name = key.split(":", 2)

                if not dispname:
                    dispname = None

                base_uri = uri
                if (domain, role_name) != ("std", "doc"):
                    base_uri += "#" + definition.html5_id
                    uri += "#" + definition.html5_id

                targets[key] = intersphinx.TargetDefinition(
                    definition.canonical_name,
                    (domain, role_name),
                    -1,
                    base_uri,
                    uri,
                    dispname,
                )
            return intersphinx.Inventory(base_url, targets)

    def copy_clean_slate(self) -> "TargetDatabase":
        """Create a deep copy of this database that only inherits the intersphinx targets.
        This is used for seeding the postprocessor."""
        with self.lock:
            return type(self)(copy.deepcopy(self.intersphinx_inventories))

    @classmethod
    def load(
        cls, config: "ProjectConfig"
    ) -> Tuple["TargetDatabase", Sequence[Tuple[str, str]]]:
        """Create a TargetDatabase with the intersphinx inventories specified by the given
        ProjectConfig."""
        db = cls()
        failed_urls = db.reset(config)
        return db, failed_urls


class ProjectInterface(Protocol):
    expensive_operation_cache: Cache[FileId]
    targets: TargetDatabase


@dataclass
class EmptyProjectInterface:
    """An empty ProjectInterface implementation for testing."""

    expensive_operation_cache: Cache[FileId]
    targets: TargetDatabase

    def __init__(self) -> None:
        self.expensive_operation_cache = Cache()
        self.targets = TargetDatabase()

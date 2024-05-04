import collections
import gzip
import hashlib
import logging
import pickle
import pickletools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import requests.exceptions

from . import __version__, diagnostics, gizaparser, specparser, util
from .diagnostics import Diagnostic
from .n import FileId
from .page import Page
from .types import ProjectConfig

logger = logging.getLogger(__name__)

# Specify protocol 5 since it's supported by Python 3.8+, our supported
# versions of Python.
PROTOCOL = 5


class CacheMiss(Exception):
    pass


@dataclass
class CacheStats:
    """Tracking data for cache hit rates."""

    hits: int = field(default=0)
    misses: int = field(default=0)
    errors: int = field(default=0)


@dataclass
class CacheData:
    specifier: Tuple[str, ...]
    pages: Dict[Tuple[str, str], bytes] = field(default_factory=dict)
    orphan_diagnostics: Dict[str, bytes] = field(default_factory=dict)

    yaml_nodes: Dict[str, Dict[FileId, Tuple[str, bytes]]] = field(
        default_factory=lambda: collections.defaultdict(dict)
    )
    yaml_pages: Dict[str, Sequence[Page]] = field(default_factory=dict)

    stats: CacheStats = field(default_factory=CacheStats)

    def set_page(self, obj: Page, diagnostics: List[Diagnostic]) -> None:
        self.pages[(obj.ast.fileid.as_posix(), obj.blake2b)] = pickle.dumps(
            (obj, diagnostics), protocol=PROTOCOL
        )

    def ingest_yaml(self, yaml_domain: gizaparser.domain.GizaYamlDomain) -> None:
        self.yaml_nodes.clear()
        for category_name, category in yaml_domain.yaml_mapping.items():
            if category.reified_nodes is None:
                continue

            for node in category.reified_nodes.values():
                source_hash = hashlib.blake2b(bytes(node.text, "utf-8")).hexdigest()
                self.yaml_nodes[category_name][node.path] = (
                    source_hash,
                    pickle.dumps(node),
                )

    def get_yaml_entries(self, category: str) -> Mapping[FileId, Tuple[str, bytes]]:
        return self.yaml_nodes[category]

    def set_orphan_diagnostics(
        self, fileid: FileId, orphan_diagnostics: List[Diagnostic]
    ) -> None:
        self.orphan_diagnostics[fileid.as_posix()] = pickle.dumps(
            orphan_diagnostics, protocol=PROTOCOL
        )

    def get(
        self, config: ProjectConfig, path: FileId
    ) -> Tuple[Page, Sequence[diagnostics.Diagnostic]]:
        """Get a specific page from the cached data with the specified blake2b hash. Raises KeyError
        if the page is not found or the checksum does not match."""

        text, _ = config.read(path)
        file_hash = hashlib.blake2b(bytes(text, "utf-8")).hexdigest()

        try:
            page, diagnostics = pickle.loads(self.pages[(path.as_posix(), file_hash)])
        except KeyError as err:
            self.stats.misses += 1
            raise CacheMiss() from err
        except Exception as err:
            logger.info("Error loading page from cache: %s", err)
            self.stats.errors += 1
            raise CacheMiss()

        assert isinstance(page, Page)
        assert all(isinstance(x, Diagnostic) for x in diagnostics)

        # Check page dependencies
        try:
            if not page.dependencies.check_cache(
                lambda fileid: hashlib.blake2b(
                    config.get_full_path(fileid).read_bytes()
                ).hexdigest()
            ):
                self.stats.misses += 1
                raise CacheMiss()
        except OSError:
            self.stats.misses += 1
            raise CacheMiss()

        self.stats.hits += 1
        return page, diagnostics

    def __len__(self) -> int:
        return len(self.pages)

    def __getstate__(self) -> Dict[str, object]:
        # Delete the statistics field from the pickle state
        state = self.__dict__.copy()
        del state["stats"]
        return state

    def __setstate__(self, state: Dict[str, object]) -> None:
        # When loading statistics from pickled data, fill in zero'd data
        self.__dict__.update(state)
        self.stats = CacheStats()


class ParseCache:
    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config = project_config
        self.specifier = self.generate_specifier()

    def read_from_bytes(self, data_bytes: bytes) -> Optional[CacheData]:
        try:
            data = pickle.loads(gzip.decompress(data_bytes))
            assert isinstance(data, CacheData)
            if not isinstance(data.specifier, tuple) or not all(
                isinstance(x, str) for x in data.specifier
            ):
                raise TypeError("Invalid cache format")
        except Exception as err:
            logger.info("Error loading cache file: %s", err)
            return None

        if data.specifier != self.specifier:
            logger.info(
                "Cache file specifier incompatible: %s != %s",
                data.specifier,
                self.specifier,
            )
            return None

        return data

    def read(
        self, path: Optional[Path] = None, url_prefix: Optional[str] = None
    ) -> CacheData:
        path = self.path if path is None else path
        url_prefix = (
            url_prefix if url_prefix else specparser.Spec.get().build.cache_url_prefix
        )
        data: Optional[CacheData] = None
        try:
            data = self.read_from_bytes(path.read_bytes())
        except FileNotFoundError:
            if url_prefix:
                url = url_prefix + self.filename
                try:
                    data = self.read_from_bytes(util.HTTPCache.singleton().get(url))
                except requests.exceptions.RequestException as err:
                    logger.debug(err)

        if not data:
            logger.info("No cache usable")
            data = CacheData(specifier=self.specifier)

        return data

    @property
    def path(self) -> Path:
        return self.project_config.root / self.filename

    @property
    def filename(self) -> str:
        return f".snooty-{self.project_config.name}-{'_'.join(self.specifier)}.cache.gz"

    def persist(
        self, data: CacheData, path: Optional[Path] = None, optimize: bool = True
    ) -> None:
        path = self.path if path is None else path

        if optimize:
            for key, page_data in data.pages.items():
                data.pages[key] = pickletools.optimize(page_data)

        # Specify protocol 5 since it's supported by Python 3.8+, our supported
        # versions of Python.
        pickled = pickle.dumps(data, protocol=PROTOCOL)
        if optimize:
            pickled = pickletools.optimize(pickled)

        util.atomic_write(path, gzip.compress(pickled, mtime=0), path.parent)

    def generate_specifier(self) -> Tuple[str, ...]:
        return (
            __version__,
            util.structural_hash(self.project_config).hex(),
            util.structural_hash(specparser.Spec.get()).hex(),
        )

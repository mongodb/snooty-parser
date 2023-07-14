import hashlib
import logging
import pickle
import pickletools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__, diagnostics, specparser, util
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
class CacheData:
    specifier: Tuple[str, ...]
    pages: Dict[Tuple[str, str], bytes] = field(default_factory=dict)
    orphan_diagnostics: Dict[str, bytes] = field(default_factory=dict)

    def set_page(self, obj: Page, diagnostics: List[Diagnostic]) -> None:
        self.pages[(obj.ast.fileid.as_posix(), obj.blake2b)] = pickle.dumps(
            (obj, diagnostics), protocol=PROTOCOL
        )

    def set_orphan_diagnostics(
        self, fileid: FileId, orphan_diagnostics: List[Diagnostic]
    ) -> None:
        self.orphan_diagnostics[fileid.as_posix()] = pickle.dumps(
            orphan_diagnostics, protocol=PROTOCOL
        )

    def get(
        self, config: ProjectConfig, path: Path
    ) -> Tuple[Page, Sequence[diagnostics.Diagnostic]]:
        """Get a specific page from the cached data with the specified blake2b hash. Raises KeyError
        if the page is not found or the checksum does not match."""

        file_hash = hashlib.blake2b(path.read_bytes()).hexdigest()

        try:
            page, diagnostics = pickle.loads(
                self.pages[(config.get_fileid(path).as_posix(), file_hash)]
            )
        except KeyError as err:
            raise CacheMiss() from err
        except Exception as err:
            logger.info("Error loading page from cache: %s", err)
            raise CacheMiss()

        assert isinstance(page, Page)
        assert all(isinstance(x, Diagnostic) for x in diagnostics)

        # Check page dependencies
        for dep_fileid, dep_blake2b in page.dependencies.items():
            dep_path = config.get_full_path(dep_fileid)
            try:
                actual_blake2b = hashlib.blake2b(dep_path.read_bytes()).hexdigest()
            except OSError:
                raise CacheMiss()

            if dep_blake2b != actual_blake2b:
                raise CacheMiss()

        return page, diagnostics

    def __len__(self) -> int:
        return len(self.pages)


class ParseCache:
    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config = project_config

    def read(self, path: Optional[Path] = None) -> CacheData:
        path = self.path if path is None else path

        self_specifier = self.generate_specifier()

        try:
            with path.open("rb") as f:
                data = pickle.load(f)
        except Exception as err:
            logger.debug("Error loading cache file: %s", err)
            return CacheData(self_specifier)

        if data.specifier != self_specifier:
            logger.info(
                "Cache file specifier incompatible: %s != %s",
                data.specifier,
                self_specifier,
            )
            return CacheData(self_specifier)

        assert isinstance(data, CacheData)
        return data

    @property
    def path(self) -> Path:
        return self.project_config.root / ".parsercache"

    def persist(
        self, data: CacheData, path: Optional[Path] = None, optimize: bool = False
    ) -> None:
        path = self.path if path is None else path
        # Specify protocol 5 since it's supported by Python 3.8+, our supported
        # versions of Python.
        pickled = pickle.dumps(data, protocol=PROTOCOL)
        if optimize:
            pickled = pickletools.optimize(pickled)

        util.atomic_write(path, pickled, path.parent)

    def generate_specifier(self) -> Tuple[str, ...]:
        return (
            __version__,
            util.structural_hash(self.project_config).hex(),
            util.structural_hash(specparser.Spec.get()).hex(),
        )

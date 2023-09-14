import collections
import hashlib
import logging
import pickle
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .. import n
from ..diagnostics import Diagnostic
from ..page import Page
from ..types import EmbeddedRstParser, ProjectConfig
from . import extracts, nodes, release, steps

if TYPE_CHECKING:
    from ..parse_cache import CacheData

logger = logging.getLogger(__name__)


def get_giza_category(path: n.FileId) -> str:
    """Infer the Giza category of a YAML file."""
    return path.name.split("-", 1)[0]


def validate_cache(
    cached_entries: Mapping[n.FileId, Tuple[str, bytes]],
    our_entries: Mapping[n.FileId, Tuple[str, str, List[Diagnostic]]],
) -> bool:
    """Check if a given set of cached giza data is eligable to be used for the YAML files on disk."""
    if cached_entries.keys() != our_entries.keys():
        return False

    for fileid, cached_entry in cached_entries.items():
        our_entry = our_entries[fileid]
        if cached_entry[0] != our_entry[0]:
            return False

    return True


class GizaYamlDomain:
    """A registry to centrally manage Giza node categories."""

    def __init__(
        self,
        config: ProjectConfig,
        rst_parser_factory: Callable[
            [ProjectConfig, Page, List[Diagnostic]], EmbeddedRstParser
        ],
    ) -> None:
        self.config = config
        self.rst_parser_factory = rst_parser_factory
        self.yaml_mapping: Mapping[str, nodes.GizaCategory[Any]] = {
            "steps": steps.GizaStepsCategory(self.config),
            "extracts": extracts.GizaExtractsCategory(self.config),
            "release": release.GizaReleaseSpecificationCategory(self.config),
        }

    def load_and_generate(
        self,
        all_diagnostics: Dict[n.FileId, List[Diagnostic]],
        cache: "Optional[CacheData]" = None,
    ) -> Iterable[Tuple[Page, Sequence[Diagnostic]]]:
        """Load all giza data, either from cache or from YAML files as appropriate."""
        categorized = self.categorize()

        # Initialize our YAML file registry for each giza category
        for prefix, giza_category in self.yaml_mapping.items():
            logger.info("Parsing %s YAML", prefix)

            our_entries: Dict[n.FileId, Tuple[str, str, List[Diagnostic]]] = {}
            for path in categorized[prefix]:
                text, reading_diagnostics = self.config.read(path)
                text_blake2b = hashlib.blake2b(bytes(text, "utf-8")).hexdigest()
                our_entries[path] = (text_blake2b, text, reading_diagnostics)

            # If we have a usable cache, load all of our YAML data from that
            if cache is not None:
                cached_entries = cache.get_yaml_entries(prefix)
                if validate_cache(cached_entries, our_entries):
                    logger.info(
                        "Cache: loaded %d nodes for %s", len(cached_entries), prefix
                    )
                    for fileid, cached_entry in cached_entries.items():
                        giza_file = pickle.loads(cached_entry[1])
                        assert isinstance(giza_file, nodes.GizaFile)
                        giza_category.add(
                            fileid,
                            our_entries[fileid][0],
                            giza_file.data,
                            giza_file.diagnostics,
                        )

                        if giza_file.pages is not None:
                            for page in giza_file.pages:
                                yield page, giza_file.diagnostics
                    continue

            # Otherwise, generate data anew
            for fileid, entry in our_entries.items():
                artifacts, text, diagnostics = giza_category.parse(fileid, entry[1])
                giza_category.add(fileid, text, artifacts, entry[2] + diagnostics)

            yield from self.generate_pages(prefix, all_diagnostics)

    def categorize(self) -> Dict[str, List[n.FileId]]:
        """Scan the source directory for YAML files we should ingest, and categorize them."""
        # Categorize our YAML files
        logger.debug("Categorizing YAML files")
        categorized: Dict[str, List[n.FileId]] = collections.defaultdict(list)
        for path in self.config.get_files_by_extension((".yaml",)):
            prefix = get_giza_category(path)
            if prefix in self.yaml_mapping:
                categorized[prefix].append(path)

        return categorized

    def generate_pages(
        self, category_name: str, all_diagnostics: Dict[n.FileId, List[Diagnostic]]
    ) -> Iterable[Tuple[Page, Sequence[Diagnostic]]]:
        """Generate a Page for each node in each of our managed categories."""
        # Now that all of our YAML files are loaded, generate a page for each one
        giza_category = self.yaml_mapping[category_name]
        logger.debug("Processing %s YAML: %d nodes", category_name, len(giza_category))
        for file_id, giza_node in giza_category.reify_all_files(all_diagnostics):

            def create_page(filename: str) -> Tuple[Page, EmbeddedRstParser]:
                page = Page.create(
                    giza_node.path,
                    filename,
                    giza_node.text,
                    n.Root((-1,), [], giza_node.path, {}),
                )
                return (
                    page,
                    self.rst_parser_factory(
                        self.config, page, giza_node.parse_diagnostics
                    ),
                )

            for page in giza_category.to_pages(giza_node.path, create_page, giza_node):
                assert giza_node.pages is not None
                yield (page, giza_node.diagnostics)

    def update(
        self,
        path: n.FileId,
        optional_text: Optional[str] = None,
    ) -> Iterable[Tuple[Page, Sequence[Diagnostic]]]:
        """Update an individual Giza file."""
        file_id = path.name
        prefix = get_giza_category(path)
        giza_category = self.yaml_mapping[prefix]
        needs_rebuild = set((file_id,)).union(
            *(
                category.dg.predecessors(file_id)
                for category in self.yaml_mapping.values()
            )
        )
        logger.debug("needs_rebuild: %s", ",".join(needs_rebuild))
        for file_id in needs_rebuild:
            file_diagnostics: List[Diagnostic] = []
            try:
                giza_node = giza_category.reify_file_id(file_id)
            except KeyError:
                logging.warn("No file found in registry: %s", file_id)
                continue

            steps, text, parse_diagnostics = giza_category.parse(path, optional_text)
            file_diagnostics.extend(parse_diagnostics)

            def create_page(filename: str) -> Tuple[Page, EmbeddedRstParser]:
                page = Page.create(
                    giza_node.path,
                    filename,
                    text,
                    n.Root((-1,), [], self.config.get_fileid(n.FileId(filename)), {}),
                )
                return (
                    page,
                    self.rst_parser_factory(self.config, page, file_diagnostics),
                )

            giza_category.add(path, text, steps, file_diagnostics)
            pages = giza_category.to_pages(giza_node.path, create_page, giza_node)
            path = giza_node.path
            yield from ((page, giza_node.diagnostics) for page in pages)

    def is_known_yaml(self, fileid: n.FileId) -> bool:
        """Check if a given fileid belongs to a known giza category."""
        return (
            fileid.suffix == ".yaml" and get_giza_category(fileid) in self.yaml_mapping
        )

    def delete(self, name: str) -> None:
        for giza_category in self.yaml_mapping.values():
            try:
                del giza_category[name]
            except KeyError:
                pass

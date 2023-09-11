import collections
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .. import n
from ..diagnostics import Diagnostic
from ..page import Page
from ..types import EmbeddedRstParser, ProjectConfig
from . import extracts, nodes, release, steps

logger = logging.getLogger(__name__)


def get_giza_category(path: n.FileId) -> str:
    """Infer the Giza category of a YAML file."""
    return path.name.split("-", 1)[0]


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
        self.yaml_mapping: Dict[str, nodes.GizaCategory[Any]] = {
            "steps": steps.GizaStepsCategory(self.config),
            "extracts": extracts.GizaExtractsCategory(self.config),
            "release": release.GizaReleaseSpecificationCategory(self.config),
        }

    def categorize(
        self, all_yaml_diagnostics: Dict[n.FileId, List[Diagnostic]]
    ) -> None:
        """Scan the source directory for YAML files we should ingest, and categorize them."""
        # Categorize our YAML files
        logger.debug("Categorizing YAML files")
        categorized: Dict[str, List[n.FileId]] = collections.defaultdict(list)
        for path in self.config.get_files_by_extension((".yaml",)):
            prefix = get_giza_category(path)
            if prefix in self.yaml_mapping:
                categorized[prefix].append(path)

        # Initialize our YAML file registry
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug("Parsing %s YAML", prefix)
            for fileid in categorized[prefix]:
                artifacts, text, diagnostics = giza_category.parse(fileid)
                if diagnostics:
                    all_yaml_diagnostics[fileid] = diagnostics
                giza_category.add(fileid, text, artifacts)

    def generate_pages(
        self, all_yaml_diagnostics: Dict[n.FileId, List[Diagnostic]]
    ) -> Iterable[Tuple[Page, Sequence[Diagnostic]]]:
        """Generate a Page for each node in each of our managed categories."""
        # Now that all of our YAML files are loaded, generate a page for each one
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug("Processing %s YAML: %d nodes", prefix, len(giza_category))
            for file_id, giza_node in giza_category.reify_all_files(
                all_yaml_diagnostics
            ):

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
                            self.config,
                            page,
                            all_yaml_diagnostics.setdefault(giza_node.path, []),
                        ),
                    )

                for page in giza_category.to_pages(
                    giza_node.path, create_page, giza_node.data
                ):
                    yield (page, all_yaml_diagnostics.get(page.fileid, []))

    def update(
        self,
        path: n.FileId,
        all_yaml_diagnostics: Dict[n.FileId, List[Diagnostic]],
        optional_text: Optional[str] = None,
    ) -> Iterable[Page]:
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
                giza_node = giza_category.reify_file_id(file_id, all_yaml_diagnostics)
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

            giza_category.add(path, text, steps)
            pages = giza_category.to_pages(giza_node.path, create_page, giza_node.data)
            path = giza_node.path
            all_yaml_diagnostics.setdefault(path, []).extend(file_diagnostics)
            yield from pages

    def is_known_yaml(self, fileid: n.FileId) -> bool:
        return (
            fileid.suffix == ".yaml" and get_giza_category(fileid) in self.yaml_mapping
        )

    def delete(self, name: str) -> None:
        for giza_category in self.yaml_mapping.values():
            try:
                del giza_category[name]
            except KeyError:
                pass

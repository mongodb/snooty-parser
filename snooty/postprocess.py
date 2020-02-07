import os.path
import logging
from collections import defaultdict
from typing import Any, Callable, cast, Dict, List, Optional, Tuple, Iterable
from .eventparser import EventParser
from .types import (
    Diagnostic,
    FileId,
    Page,
    ProjectConfig,
    SerializableType,
    TargetDatabase,
)
from .util import get_child_of_type, SOURCE_FILE_EXTENSIONS

logger = logging.getLogger(__name__)


# XXX: The following two functions should probably be combined at some point
def get_title_injection_candidate(
    node: Dict[str, SerializableType]
) -> Optional[Dict[str, SerializableType]]:
    """Dive into a tree of nodes, and return the deepest non-inline node if and only if the tree is linear."""
    while True:
        children = node.get("children")
        if children is not None:
            assert isinstance(children, list)
            if len(children) > 1:
                return None
            elif len(children) == 1:
                node = children[0]
            else:
                return node
        else:
            return None


def get_deepest(
    node: Dict[str, SerializableType]
) -> Optional[Dict[str, SerializableType]]:
    """Dive into a tree of nodes, and return the deepest node if and only if the tree is linear."""
    while True:
        children = node.get("children")
        if children is not None:
            assert isinstance(children, list)
            if len(children) > 1:
                return None
            elif len(children) == 1:
                node = children[0]
            else:
                return node
        else:
            return node


def deep_copy_position(source: SerializableType, dest: SerializableType) -> None:
    """Copy the source position data from one node to another, for the case
       where the dest node's positional data is irrelevant or comes from another file."""
    assert isinstance(source, dict)
    assert isinstance(dest, dict)
    source_position = source["position"]
    dest["position"] = source_position
    for child in dest.get("children", ()):
        deep_copy_position(source, child)


class Postprocessor:
    """Handles all postprocessing operations on parsed AST files.

    The only method that should be called on an instance of Postprocessor is run(). This method
    handles calling all other methods and ensures that parse operations are run in the correct order."""

    def __init__(self, project_config: ProjectConfig, targets: TargetDatabase) -> None:
        self.project_config = project_config
        self.slug_title_mapping: Dict[str, List[SerializableType]] = {}
        self.toctree: Dict[str, SerializableType] = {}
        self.pages: Dict[FileId, Page] = {}
        self.pending_targets: List[SerializableType] = []
        self.targets = targets
        self.toc_landing_pages = [
            clean_slug(slug) for slug in project_config.toc_landing_pages
        ]

    def run(
        self, pages: Dict[FileId, Page]
    ) -> Tuple[Dict[str, SerializableType], Dict[FileId, List[Diagnostic]]]:
        """Run all postprocessing operations and return a dictionary containing the metadata document to be saved."""
        if not pages:
            return {}, {}

        self.pages = pages
        self.build_slug_fileid_mapping()
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)

        document: Dict[str, SerializableType] = {}

        document.update({"title": self.project_config.title})

        self.run_event_parser(
            [(EventParser.OBJECT_START_EVENT, self.populate_include_nodes)]
        )

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.build_slug_title_mapping),
                (EventParser.OBJECT_START_EVENT, self.add_titles_to_label_targets),
            ]
        )

        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_target)])

        # Update metadata document with key-value pairs defined in event parser
        document.update({"slugToTitle": self.slug_title_mapping})

        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_refs)])

        # Run postprocessing operations related to toctree and append to metadata document
        document.update(
            {
                "toctree": self.build_toctree(),
                "toctreeOrder": self.toctree_order(),
                "parentPaths": self.breadcrumbs(),
            }
        )

        return document, self.diagnostics

    def run_event_parser(
        self, listeners: Iterable[Tuple[str, Callable[[Any], None]]]
    ) -> None:
        event_parser = EventParser()
        for event, listener in listeners:
            event_parser.add_event_listener(event, listener)

        event_parser.consume(
            (k, v) for k, v in self.pages.items() if k.suffix == ".txt"
        )

    def handle_refs(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """When a node of type ref_role is encountered, ensure that it references a valid target.

        If so, append the full URL to the AST node. If not, throw an error.
        """
        obj = kwargs.get("obj")
        assert obj is not None

        if obj.get("type") == "ref_role":
            domain = obj.get("domain")
            name = obj.get("name")
            target = obj.get("target")
            key = f"{domain}:{name}:{target}"

            try:
                # Add title and link target to AST
                field_name, target, title_nodes = self.targets[key]
                injection_candidate = get_title_injection_candidate(obj)
                if not obj.get("children") or injection_candidate is not None:
                    for node in title_nodes:
                        deep_copy_position(obj, node)
                    obj[field_name] = target

                    if injection_candidate is not None:
                        obj = injection_candidate
                    obj["children"] = title_nodes
            except KeyError:
                position = cast(Any, obj.get("position"))
                start = position["start"]
                line = start["line"]
                self.diagnostics[filename].append(
                    Diagnostic.error(f'Target not found: "{name}:{target}"', line)
                )

    def add_titles_to_label_targets(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        obj = kwargs["obj"]
        assert obj is not None
        node_type = obj.get("type")

        if node_type not in {"target", "section"}:
            self.pending_targets = []

        if (
            node_type == "target"
            and obj.get("domain") == "std"
            and obj.get("name") == "label"
        ):
            self.pending_targets.append(obj)
        elif node_type == "section":
            for target in self.pending_targets:
                heading = get_child_of_type(obj, "heading")
                if heading is not None:
                    target["children"].append(  # type: ignore
                        {
                            "type": "target_ref_title",
                            "position": heading["position"],  # type: ignore
                            "children": heading["children"],  # type: ignore
                        }
                    )
            self.pending_targets = []

    def handle_target(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        obj = kwargs["obj"]
        assert obj is not None

        if obj.get("type") != "target":
            return

        domain = obj["domain"]
        assert isinstance(domain, str)
        name = obj["name"]
        assert isinstance(name, str)
        target = obj["target"]
        assert isinstance(target, str)
        title_node = get_child_of_type(obj, "target_ref_title")
        if title_node is None:
            title: List[SerializableType] = []
        else:
            title = title_node["children"]  # type: ignore

        self.targets.define_local_target(domain, name, target, filename, title)

    def populate_include_nodes(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """Iterate over all pages to find include directives. When found, replace their
        `children` property with the contents of the include file.
        Because the include contents are added to the tree on which the event parser is
        running, they will automatically be parsed and have their includes expanded, too."""

        def get_include_argument(node: Dict[str, Any]) -> str:
            """Get filename of include"""
            argument_list = node["argument"]
            assert len(argument_list) > 0
            argument: str = argument_list[0]["value"]
            return argument

        obj = kwargs.get("obj")
        assert obj is not None

        if obj.get("name") == "include":
            argument = get_include_argument(obj)
            include_slug = clean_slug(argument)
            include_fileid = self.slug_fileid_mapping.get(include_slug)
            # Some `include` FileIds in the mapping include file extensions (.yaml) and others do not
            # This will likely be resolved by DOCSP-7159 https://jira.mongodb.org/browse/DOCSP-7159
            if include_fileid is None:
                include_slug = argument.strip("/")
                include_fileid = self.slug_fileid_mapping.get(include_slug)

                # End if we can't find a file
                if include_fileid is None:
                    return

            include_page = self.pages.get(include_fileid)
            assert include_page is not None
            include_ast = cast(Dict[str, SerializableType], include_page.ast)
            obj["children"] = include_ast["children"]

    def build_slug_title_mapping(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """Construct a slug-title mapping of all pages in property"""
        obj = kwargs.get("obj")
        slug = filename.without_known_suffix

        assert obj is not None

        # Save the first heading we encounter to the slug title mapping
        if slug not in self.slug_title_mapping and obj.get("type") == "heading":
            children = cast(Optional[List[SerializableType]], obj.get("children"))
            assert children is not None
            self.slug_title_mapping[slug] = children

    def build_slug_fileid_mapping(self) -> None:
        """Construct a {slug: fileid} mapping so that we can retrieve the full file name
        given a slug. We cannot use the with_suffix method since the type of the slug
        in find_toctree_nodes(...) is string rather than FileId."""
        fileid_dict: Dict[str, FileId] = {}
        for fileid in self.pages:
            slug = fileid.without_known_suffix
            fileid_dict[slug] = fileid
        self.slug_fileid_mapping = fileid_dict

    def build_toctree(self) -> Dict[str, SerializableType]:
        """Build property toctree"""

        # The toctree must begin at either `contents.txt` or `index.txt`.
        # Generally, repositories will have one or the other; but, if a repo has both,
        # the starting point will be `contents.txt`.
        candidates = (FileId("contents.txt"), FileId("index.txt"))
        starting_fileid = next(
            (candidate for candidate in candidates if candidate in self.pages), None
        )
        if starting_fileid is None:
            return {}

        # Build the toctree
        root: Dict[str, SerializableType] = {
            "title": self.project_config.title,
            "slug": "/",
            "children": [],
        }
        ast: Dict[str, SerializableType] = cast(
            Dict[str, SerializableType], self.pages[starting_fileid].ast
        )

        self.find_toctree_nodes(starting_fileid, ast, root)

        self.toctree = root
        return root

    def find_toctree_nodes(
        self, fileid: FileId, ast: Dict[str, Any], node: Dict[str, Any]
    ) -> None:
        """Iterate over AST to find toctree directives and construct their nodes for the unified toctree"""

        # Base case: stop iterating over AST
        if not children_exist(ast):
            return

        is_toctree_node: bool = ast["type"] == "directive" and ast["name"] == "toctree"
        if is_toctree_node and "entries" in ast.keys():
            # Recursively build the tree for each toctree node in this entries list
            assert isinstance(ast["entries"], List)
            for entry in ast["entries"]:
                toctree_node: Dict[str, SerializableType] = {}
                if "url" in entry:
                    toctree_node = {
                        "title": entry.get("title", None),
                        "url": entry.get("url", None),
                        "children": [],
                    }
                elif "slug" in entry:
                    # Recursively build the tree for internal links
                    slug_cleaned = clean_slug(entry["slug"])

                    # Ensure that the user-specified slug is an existing page. We want to add this error
                    # handling to the initial parse layer, but this works for now.
                    # https://jira.mongodb.org/browse/DOCSP-7941
                    slug_fileid: FileId = self.slug_fileid_mapping[slug_cleaned]
                    slug: str = slug_fileid.without_known_suffix

                    toctree_node = {
                        "title": entry.get("title")
                        or self.slug_title_mapping.get(slug, None),
                        "slug": slug,
                        "children": [],
                        "options": {"drawer": slug not in self.toc_landing_pages},
                    }

                    new_ast: Dict[str, Any] = cast(
                        Dict[str, Any], self.pages[slug_fileid].ast
                    )
                    self.find_toctree_nodes(slug_fileid, new_ast, toctree_node)
                node["children"].append(toctree_node)

        # Locate the correct directive object containing the toctree within this AST
        for child_ast in ast["children"]:
            self.find_toctree_nodes(fileid, child_ast, node)

    def breadcrumbs(self) -> Dict[str, List[str]]:
        """Generate breadcrumbs for each page represented in the toctree"""
        page_dict: Dict[str, List[str]] = {}
        all_paths: List[Any] = []

        # Find all node to leaf paths for each node in the toctree
        if children_exist(self.toctree):
            assert isinstance(self.toctree["children"], List)
            for node in self.toctree["children"]:
                paths: List[str] = []
                get_paths(node, [], paths)
                all_paths.extend(paths)

        # Populate page_dict with a list of parent paths for each slug
        for path in all_paths:
            for i in range(len(path)):
                slug = clean_slug(path[i])
                page_dict[slug] = path[:i]
        return page_dict

    def toctree_order(self) -> List[str]:
        """Return a pre-order traversal of the toctree to be used for internal page navigation"""
        order: List[str] = []

        pre_order(self.toctree, order)
        return order


def pre_order(node: Dict[str, Any], order: List[str]) -> None:
    if not node:
        return
    if "slug" in node:
        order.append(node["slug"])
    if children_exist(node):
        for child in node["children"]:
            pre_order(child, order)


def get_paths(node: Dict[str, Any], path: List[str], all_paths: List[Any]) -> None:
    """Helper function used to retrieve the breadcrumbs for a particular slug"""
    if not node:
        return
    if node.get("children") is None or len(node["children"]) == 0:
        # Skip urls
        if "slug" in node:
            path.append(clean_slug(node["slug"]))
            all_paths.append(path)
    else:
        # Recursively build the path
        for child in node["children"]:
            subpath = path[:]
            subpath.append(clean_slug(node["slug"]))
            get_paths(child, subpath, all_paths)


def clean_slug(slug: str) -> str:
    """Strip file extension and leading/trailing slashes (/) from string"""
    slug = slug.strip("/")

    # TODO: remove file extensions in initial parse layer
    # https://jira.mongodb.org/browse/DOCSP-7595
    root, ext = os.path.splitext(slug)
    if ext in SOURCE_FILE_EXTENSIONS:
        return root

    return slug


def children_exist(ast: Dict[str, Any]) -> bool:
    if "children" in ast.keys():
        return True
    return False


class DevhubPostprocessor(Postprocessor):
    """Postprocess operation to be run if a project's default_domain is equal to 'devhub'"""

    # TODO: Identify directives that should be exposed in the rstspec.toml to avoid hardcoding
    # These directives are represented as list nodes; they will return a list of strings
    LIST_FIELDS = {"devhub:products", "devhub:tags", ":languages"}
    # These directives have their content represented as children; they will return a list of nodes
    BLOCK_FIELDS = {"devhub:introduction"}

    def run(
        self, pages: Dict[FileId, Page]
    ) -> Tuple[Dict[str, SerializableType], Dict[FileId, List[Diagnostic]]]:
        if not pages:
            return {}, {}

        self.pages = pages
        self.build_slug_fileid_mapping()
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)

        document: Dict[str, SerializableType] = {"title": self.project_config.title}

        self.run_event_parser(
            [(EventParser.OBJECT_START_EVENT, self.populate_include_nodes)]
        )

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.build_slug_title_mapping),
                (EventParser.OBJECT_START_EVENT, self.add_titles_to_label_targets),
            ]
        )

        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_target)])

        # Update metadata document with key-value pairs defined in event parser
        document.update({"slugToTitle": self.slug_title_mapping})

        def clean_and_validate_page_group_slug(slug: str) -> Optional[str]:
            """Clean a slug and validate that it is a known page. If it is not, return None."""
            cleaned = clean_slug(slug)
            if cleaned not in self.slug_title_mapping:
                # XXX: Because reporting errors in config.toml properly is dodgy right now, just
                # log to stderr.
                logger.error(f"Cannot find slug '{cleaned}'")
                return None

            return cleaned

        # Normalize all page group slugs
        page_groups = {
            title: [
                slug
                for slug in (clean_and_validate_page_group_slug(slug) for slug in slugs)
                if slug
            ]
            for title, slugs in self.project_config.page_groups.items()
        }

        if page_groups:
            document.update({"pageGroups": page_groups})

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.handle_refs),
                (EventParser.OBJECT_START_EVENT, self.flatten_devhub_article),
                (EventParser.PAGE_START_EVENT, self.reset_query_fields),
                (EventParser.PAGE_END_EVENT, self.append_query_fields),
            ]
        )

        return document, self.diagnostics

    def reset_query_fields(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """To be called at the start of each page: reset the query field dictionary"""
        self.query_fields: Dict[str, Any] = {}

    def append_query_fields(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """To be called at the end of each page: append the query field dictionary to the
        top level of the page's class instance.
        """
        page = kwargs.get("page")
        assert isinstance(page, Page)
        page.query_fields = self.query_fields

    def flatten_devhub_article(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]],
    ) -> None:
        """Extract fields from a page's AST and expose them as a queryable nested document in the page document."""
        obj = kwargs.get("obj")
        assert obj is not None

        if obj.get("type") != "directive":
            return

        domain = obj.get("domain")
        assert isinstance(domain, str)
        name = obj.get("name")
        assert isinstance(name, str)
        key = f"{domain}:{name}"

        if key == "devhub:author":
            options = cast(Dict[str, str], obj["options"])
            self.query_fields["author"] = options["name"]
        elif key in self.BLOCK_FIELDS:
            self.query_fields[name] = obj["children"]
        elif key in self.LIST_FIELDS:
            self.query_fields[name] = []
            children = cast(Any, obj["children"])
            list_items = children[0]["children"]
            assert isinstance(list_items, List)
            for item in list_items:
                text_candidate = get_deepest(item)
                assert text_candidate is not None
                self.query_fields[name].append(text_candidate["value"])

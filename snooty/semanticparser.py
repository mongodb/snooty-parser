from typing import Any, Callable, cast, Dict, List, Optional, Set
from .types import FileId, Page, ProjectConfig, SerializableType
import re

PAT_FILE_EXTENSIONS = re.compile(r"\.((txt)|(rst)|(yaml))$")

PAGE_START_EVENT = "page_start"
OBJECT_START_EVENT = "object_start"
ARRAY_START_EVENT = "array_start"
PAIR_EVENT = "pair"
ELEMENT_EVENT = "element"


class SemanticParser:
    """SemanticParser handles all operations on parsed AST files.

    The only method that should be called on an instance of SemanticParser is run(). This method
    handles calling all other methods and ensures that parse operations are run in the correct order."""

    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config = project_config
        self.slug_title_mapping: Dict[str, List[SerializableType]] = {}
        self.toctree: Dict[str, SerializableType] = {}
        self.pages: Dict[FileId, Page] = {}
        self.toc_landing_pages = [
            clean_slug(slug) for slug in project_config.toc_landing_pages
        ]

    def run(
        self, pages: Dict[FileId, Page], fn_names: List[str]
    ) -> Dict[str, SerializableType]:
        """Run all semantic parse operations and return a dictionary containing the metadata document to be saved."""
        if not pages:
            return {}

        self.pages = pages
        self.build_slug_fileid_mapping()
        document: Dict[str, SerializableType] = {}

        # Update metadata document with key-value pairs defined in event parser
        document.update(self.run_event_parser())

        # Run semantic parse operations related to toctree and append to metadata document
        document.update(
            {
                "toctree": self.build_toctree(),
                "toctreeOrder": self.toctree_order(),
                "parentPaths": self.breadcrumbs(),
            }
        )

        return document

    def run_event_parser(self) -> Dict[str, SerializableType]:
        event_parser = EventParser()
        event_parser.add_event_listener(OBJECT_START_EVENT, self.populate_include_nodes)
        event_parser.add_event_listener(
            OBJECT_START_EVENT, self.build_slug_title_mapping
        )
        event_parser.consume(self.pages)

        # Return dict containing fields updated in event-based parse
        return {"slugToTitle": self.slug_title_mapping}

    def populate_include_nodes(
        self,
        filename: FileId,
        *args: SerializableType,
        **kwargs: Optional[Dict[str, SerializableType]]
    ) -> None:
        """Iterate over all pages to find include directives. When found, replace their
        `children` property with the contents of the include file.
        Because the include contents are added to the tree on which the event parser is
        running, they will automatically be parsed and have their includes expanded, too."""

        def get_include_argument(node: Dict[str, Any]) -> str:
            argument_list = node["argument"]
            assert len(argument_list) > 0
            argument: str = argument_list[0]["value"]
            return argument

        obj = kwargs.get("obj")
        assert obj is not None

        # Only parse pages for include nodes
        if filename.suffix != ".txt":
            return

        if obj.get("name") == "include":
            argument = get_include_argument(obj)
            include_slug = clean_slug(argument)
            include_fileid = self.slug_fileid_mapping.get(include_slug)
            # Some includes in the mapping include file extensions (.yaml) and others do not
            # Perhaps try to find the logic in this, but for now handle both cases
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
        **kwargs: Optional[Dict[str, SerializableType]]
    ) -> None:
        """Construct a slug-title mapping of all pages in property"""
        obj = kwargs.get("obj")
        slug = filename.without_known_suffix

        assert obj is not None

        # Only parse pages for their headings
        if filename.suffix != ".txt":
            return

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
            "title": self.project_config.name,
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
    slug_cleaned = slug.strip("/")

    # TODO: remove file extensions in initial parse layer
    # https://jira.mongodb.org/browse/DOCSP-7595
    return PAT_FILE_EXTENSIONS.sub("", slug_cleaned)


def children_exist(ast: Dict[str, Any]) -> bool:
    if "children" in ast.keys():
        return True
    return False


class EventListeners:
    """Manage the listener functions associated with an event-based parse operation"""

    def __init__(self) -> None:
        self._universal_listeners: Set[Callable[..., Any]] = set()
        self._event_listeners: Dict[str, Set[Callable[..., Any]]] = {}

    def add_universal_listener(self, listener: Callable[..., Any]) -> None:
        """Add a listener to be called on any event"""
        self._universal_listeners.add(listener)

    def add_event_listener(self, event: str, listener: Callable[..., Any]) -> None:
        """Add a listener to be called when a particular type of event occurs"""
        event = event.upper()
        listeners: Set[Callable[..., Any]] = self._event_listeners.get(event, set())
        listeners.add(listener)
        self._event_listeners[event] = listeners

    def get_event_listeners(self, event: str) -> Set[Callable[..., Any]]:
        """Return all listeners of a particular type"""
        event = event.upper()
        return self._event_listeners.get(event, set())

    def fire(
        self,
        event: str,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Iterate through all universal listeners and all listeners of the specified type and call them"""
        for listener in self.get_event_listeners(event):
            listener(filename, *args, **kwargs)

        for listener in self._universal_listeners:
            listener(filename, *args, **kwargs)


class EventParser(EventListeners):
    """Initialize an event-based parse on a python dictionary"""

    def __init__(self) -> None:
        super(EventParser, self).__init__()

    def consume(self, d: Dict[FileId, Page]) -> None:
        """Initializes a parse on the provided key-value map of pages"""
        for filename, page in d.items():
            self._on_page_enter_event(filename)
            self._iterate(cast(Dict[str, SerializableType], page.ast), filename)

    def _iterate(self, d: SerializableType, filename: FileId) -> None:
        if isinstance(d, dict):
            self._on_object_enter_event(d, filename)
            for k, v in d.items():
                self._on_pair_event(k, v, filename)
                self._iterate(v, filename)
        elif isinstance(d, list):
            self._on_array_enter_event(d, filename)
            for child in d:
                self._iterate(child, filename)
        else:
            self._on_element_event(d, filename)

    def _on_page_enter_event(
        self, filename: FileId, *args: SerializableType, **kwargs: SerializableType
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(PAGE_START_EVENT, filename, *args, **kwargs)

    def _on_object_enter_event(
        self,
        obj: Dict[str, SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an object is first encountered in tree"""
        self.fire(OBJECT_START_EVENT, filename, obj=obj, *args, **kwargs)

    def _on_array_enter_event(
        self,
        arr: List[SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(ARRAY_START_EVENT, filename, arr=arr, *args, **kwargs)

    def _on_pair_event(
        self,
        key: SerializableType,
        value: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when a key-value pair is encountered in tree"""
        self.fire(PAIR_EVENT, filename, key=key, value=value, *args, **kwargs)

    def _on_element_event(
        self,
        element: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an array element is encountered in tree"""
        self.fire(ELEMENT_EVENT, filename, element=element, *args, **kwargs)

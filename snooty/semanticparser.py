from typing import Any, Callable, cast, Dict, List, Set
from .types import FileId, Page, ProjectConfig, SerializableType
import re

PAT_FILE_EXTENSIONS = re.compile(r"\.((txt)|(rst)|(yaml))$")


class SemanticParser:
    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config = project_config
        self.slug_title: Dict[str, Any] = {}
        self.toctree: Dict[str, Any] = {}
        self.parent_paths: Dict[str, Any] = {}

    def run(
        self, pages: Dict[FileId, Page], fn_names: List[str]
    ) -> Dict[str, SerializableType]:
        if not pages:
            return {}

        document: Dict[str, SerializableType] = {}

        # Update metadata document with key-value pairs defined in event parser
        document.update(self.run_event_parser(pages))

        # Specify which transformations should be included in semantic postprocessing
        functions: List[
            Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]
        ] = self.functions(fn_names)

        for fn in functions:
            field: Dict[str, SerializableType] = fn(pages)
            document.update(field)
        return document

    def run_event_parser(
        self, pages: Dict[FileId, Page]
    ) -> Dict[str, SerializableType]:
        event_parser = EventParser()

        # Add event listeners here before calling consume()

        event_parser.consume(pages)

        # Return dict containing fields updated in event-based parse
        return {}

    # Returns a list of transformations to include in self.run()
    def functions(
        self, fn_names: List[str]
    ) -> List[Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]]:
        fn_mapping = {
            "toctree": self.build_toctree,
            "slug-title": self.build_slug_title,
            "breadcrumbs": self.breadcrumbs,
            "toctree order": self.toctree_order,
        }

        return [fn_mapping[name] for name in fn_names]

    def build_slug_title(
        self, pages: Dict[FileId, Page]
    ) -> Dict[str, SerializableType]:
        # Function which returns a dictionary of slug-title mappings
        slug_title_dict: Dict[str, SerializableType] = {}
        for file_id, page in pages.items():
            # remove the file extension from the slug
            slug = file_id.without_known_suffix

            # Skip slug-title mapping if the file is an `includes`
            if "includes" in slug or "images" in slug:
                continue

            # Parse for title
            title = ""
            ast: Dict[str, Any] = cast(Dict[str, Any], page.ast)
            title_is_set = False

            if ast is None:
                return {}

            for child in ast["children"]:
                if title_is_set:
                    break
                if child["type"] == "section":
                    for section_child in child["children"]:
                        if title_is_set:
                            break
                        if section_child["type"] == "heading":
                            for heading_child in section_child["children"]:
                                if title_is_set:
                                    break
                                if heading_child["type"] == "text":
                                    title = heading_child["value"]
                                    title_is_set = True
            slug_title_dict[slug] = title

        self.slug_title = {"slugToTitle": slug_title_dict}

        return self.slug_title

    def build_toctree(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        fileid_dict = {}
        toctree: Dict[str, Any] = {"toctree": {}}

        # The toctree must begin at either `contents.txt` or `index.txt`.
        # Generally, repositories will have one or the other; but, if a repo has both,
        # the starting point will be `contents.txt`.
        candidates = (FileId("contents.txt"), FileId("index.txt"))
        starting_fileid = next(
            (candidate for candidate in candidates if candidate in pages), None
        )
        if starting_fileid is None:
            return {}

        # Construct a {slug: fileid} mapping so that we can retrieve the full file name
        # given a slug. We cannot use the with_suffix method since the type of the slug
        # in find_toctree_nodes(...) is string rather than FileId.
        for fileid in pages:
            slug = fileid.without_known_suffix
            fileid_dict[slug] = fileid

        if not self.slug_title:
            self.build_slug_title(pages)

        # Build the toctree
        root: Dict["str", Any] = {}
        ast: Dict[str, Any] = cast(Dict[str, Any], pages[starting_fileid].ast)

        find_toctree_nodes(
            starting_fileid,
            ast,
            pages,
            root,
            fileid_dict,
            self.slug_title["slugToTitle"],
        )

        toctree["toctree"] = root
        toctree["toctree"]["title"] = self.project_config.name
        toctree["toctree"]["slug"] = "/"

        self.toctree = toctree

        return self.toctree

    def breadcrumbs(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        page_dict: Dict[str, Any] = {}
        if not self.toctree:
            self.build_toctree(pages)

        all_paths: List[Any] = []

        # Find all node to leaf paths for each node in the toctree
        if children_exist(self.toctree["toctree"]):
            for node in self.toctree["toctree"]["children"]:
                paths: List[str] = []
                get_paths(node, [], paths)
                all_paths.extend(paths)

        # Populate page_dict with a list of all possible paths for each slug
        for path in all_paths:
            reversed_path = path[::-1]
            for i in range(len(reversed_path)):
                slug = remove_leading_slash(path[i])

                if slug not in page_dict:
                    page_dict[slug] = [path[:i]]
                else:
                    if path[:i] not in page_dict[slug]:
                        page_dict[slug].append(path[:i])

        # Flatten the list of paths if possible
        for slug, paths in page_dict.items():
            if len(paths) == 1:
                page_dict[slug] = paths[0]

        self.parent_paths = {"parentPaths": page_dict}

        return self.parent_paths

    # toctree_order returns a pre-order traversal of the toctree
    def toctree_order(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        order: List[str] = []

        if not self.toctree:
            self.build_toctree(pages)

        pre_order(self.toctree["toctree"], order)
        return {"toctreeOrder": order}


def pre_order(root: Dict[str, Any], order: List[str]) -> None:
    if not root:
        return
    if "slug" in root:
        order.append(root["slug"])
    if children_exist(root):
        for child in root["children"]:
            pre_order(child, order)


# Helper function used to retrieve the breadcrumbs for a particular slug
def get_paths(root: Dict[str, Any], path: List[str], all_paths: List[Any]) -> None:
    if not root:
        return
    if (
        not children_exist(root)
        or (children_exist(root) and len(root["children"])) == 0
    ):
        # Skip urls
        if "slug" in root:
            path.append(remove_leading_slash(root["slug"]))
            all_paths.append(path)
    else:
        # Recursively build the path
        for child in root["children"]:
            subpath = path[:]
            subpath.append(remove_leading_slash(root["slug"]))
            get_paths(child, subpath, all_paths)


# find_toctree_nodes is a helper function for SemanticParser.toctree that recursively builds the toctree
def find_toctree_nodes(
    fileid: FileId,
    ast: Dict[str, Any],
    pages: Dict[FileId, Page],
    node: Dict[Any, Any],
    fileid_dict: Dict[str, FileId],
    slug_title: Dict[str, Any],
) -> None:

    # Base case: create node in toctree
    if not children_exist(ast):
        if node:
            node["slug"] = fileid.without_known_suffix
            node["title"] = slug_title.get(node["slug"], "")
        return

    if ast["type"] == "directive":
        if ast["name"] == "toctree" and "entries" in ast.keys():
            if not children_exist(node):
                node["children"] = ast["entries"]
            else:
                node["children"].extend(ast["entries"])

            # Recursively build the tree for each toctree node in this entries list
            for toctree_node in ast["entries"]:
                if not children_exist(toctree_node):
                    # If the node has no children, save `children` as an empty list
                    toctree_node["children"] = []
                if "slug" in toctree_node:
                    # Only recursively build the tree for internal links
                    slug = remove_leading_slash(toctree_node["slug"])

                    if slug[-1] == "/":
                        slug = slug[:-1]

                    # TODO: https://jira.mongodb.org/browse/DOCSP-7595
                    slug = PAT_FILE_EXTENSIONS.sub("", slug)

                    new_fileid = fileid_dict[slug]
                    new_ast: Dict[str, Any] = cast(
                        Dict[str, Any], pages[new_fileid].ast
                    )
                    find_toctree_nodes(
                        new_fileid,
                        new_ast,
                        pages,
                        toctree_node,
                        fileid_dict,
                        slug_title,
                    )

    # Locate the correct directive object containing the toctree within this AST
    for child_ast in ast["children"]:
        find_toctree_nodes(fileid, child_ast, pages, node, fileid_dict, slug_title)


def children_exist(ast: Dict[str, Any]) -> bool:
    if "children" in ast.keys():
        return True
    return False


def remove_leading_slash(path: str) -> str:
    if path[0] == "/":
        return path[1:]
    return path


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

    PAGE_START_EVENT = "page_start"
    OBJECT_START_EVENT = "object_start"
    ARRAY_START_EVENT = "array_start"
    PAIR_EVENT = "pair"
    ELEMENT_EVENT = "element"

    def __init__(self) -> None:
        super(EventParser, self).__init__()

    def consume(self, d: Dict[FileId, Page]) -> None:
        """Initializes a parse on the provided key-value map of pages"""
        for key, value in d.items():
            self._iterate(cast(Dict[str, SerializableType], value.ast), key)

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

    def _on_object_enter_event(
        self,
        obj: Dict[str, SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an object is first encountered in tree"""
        self.fire(self.OBJECT_START_EVENT, filename, obj=obj, *args, **kwargs)

    def _on_array_enter_event(
        self,
        arr: List[SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.ARRAY_START_EVENT, filename, arr=arr, *args, **kwargs)

    def _on_pair_event(
        self,
        key: SerializableType,
        value: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when a key-value pair is encountered in tree"""
        self.fire(self.PAIR_EVENT, filename, key=key, value=value, *args, **kwargs)

    def _on_element_event(
        self,
        element: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        """Called when an array element is encountered in tree"""
        self.fire(self.ELEMENT_EVENT, filename, element=element, *args, **kwargs)

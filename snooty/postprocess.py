import collections
import logging
import os.path
import sys
import typing
import urllib.parse
from collections import defaultdict
from copy import deepcopy
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    MutableSequence,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from . import n, specparser, util
from .diagnostics import (
    AmbiguousTarget,
    Diagnostic,
    DuplicateDirective,
    ExpectedPathArg,
    ExpectedTabs,
    InvalidChild,
    InvalidContextError,
    InvalidIAEntry,
    InvalidInclude,
    InvalidTocTree,
    MissingOption,
    MissingTab,
    MissingTocTreeEntry,
    SubstitutionRefError,
    TargetNotFound,
    UnnamedPage,
)
from .eventparser import EventParser, FileIdStack
from .page import Page
from .target_database import TargetDatabase
from .types import FileId, ProjectConfig, SerializableType
from .util import SOURCE_FILE_EXTENSIONS

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


# XXX: The following two functions should probably be combined at some point
def get_title_injection_candidate(node: n.Node) -> Optional[n.Parent[n.Node]]:
    """Dive into a tree of nodes, and return the deepest non-inline node if and only if the tree is linear."""
    while True:
        if isinstance(node, n.Parent):
            if len(node.children) > 1:
                return None
            elif len(node.children) == 1:
                node = node.children[0]
            else:
                return node
        else:
            return None


def get_deepest(node: n.Node) -> Optional[n.Node]:
    """Dive into a tree of nodes, and return the deepest node if and only if the tree is linear."""
    while True:
        if isinstance(node, n.Parent):
            if len(node.children) > 1:
                return None
            elif len(node.children) == 1:
                node = node.children[0]
            else:
                return node
        else:
            return node


def deep_copy_position(source: n.Node, dest: n.Node) -> None:
    """Copy the source position data from one node to another, for the case
    where the dest node's positional data is irrelevant or comes from another file."""
    source_position = source.span
    dest.span = source_position
    if isinstance(dest, n.Parent):
        for child in dest.children:
            deep_copy_position(source, child)


def extract_inline(
    nodes: Union[MutableSequence[n.Node], MutableSequence[n.InlineNode]]
) -> Optional[MutableSequence[n.InlineNode]]:
    """Reach into a node and see if it's trivally transformable into an inline context
    without losing anything aside from a wrapping Paragraph."""
    if all(isinstance(node, n.InlineNode) for node in nodes):
        return cast(MutableSequence[n.InlineNode], nodes)

    node = nodes[0]
    if (
        len(nodes) == 1
        and isinstance(node, n.Paragraph)
        and len(node.children) == 1
        and isinstance(node.children[0], n.InlineNode)
    ):
        return [node.children[0]]

    return None


class Context:
    """Store and refer to an instance of a type by that type. This allows referring to
    arbitrary data stores in a type-safe way."""

    __slots__ = ("_ctx", "diagnostics", "pages")

    def __init__(self, pages: Dict[FileId, Page]) -> None:
        self._ctx: Dict[type, object] = {}
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)
        self.pages = pages

    def add(self, val: object) -> None:
        """Add a given instance to this context. If an instance of the same type has
        previously been added, it will be overwritten."""
        self._ctx[type(val)] = val

    def __getitem__(self, ty: Type[_T]) -> _T:
        """Retrieve an instance of the given type. Raises KeyError if an instance
        of this type has not previously been added."""
        val = self._ctx[ty]
        assert isinstance(val, ty)
        return val


class Handler:
    """Base class for postprocessing event handlers."""

    def __init__(self, context: Context) -> None:
        self.context = context

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        pass

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        pass

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        pass

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        pass


class ProgramOptionHandler(Handler):
    """Handle the program & option rstobjects, using the last program target
    to populate option targets."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.pending_program: Optional[n.Target] = None

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.pending_program = None

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Target):
            return

        identifier = f"{node.domain}:{node.name}"
        if identifier == "std:program":
            self.pending_program = node
        elif identifier == "std:option":
            if not self.pending_program:
                line = node.start[0]
                self.context.diagnostics[fileid_stack.current].append(
                    MissingOption(line)
                )
                return
            program_target = next(
                self.pending_program.get_child_of_type(n.TargetIdentifier)
            )
            program_name_node = program_target.children[0]
            assert isinstance(program_name_node, n.Text)
            program_name = program_name_node.value
            new_identifiers: List[n.Node] = []
            for child in node.get_child_of_type(n.TargetIdentifier):
                child_ids = child.ids
                child_ids.extend(
                    [f"{program_name}.{child_id}" for child_id in child_ids]
                )

                text_node = child.children[0]
                assert isinstance(text_node, n.Text)
                value = text_node.value
                text_node.value = f"{program_name} {value}"

            node.children.extend(new_identifiers)


class IncludeHandler(Handler):
    """Iterate over all pages to find include directives. When found, replace their
    `children` property with the contents of the include file.
    Because the include contents are added to the tree on which the event parser is
    running, they will automatically be parsed and have their includes expanded, too."""

    def __init__(
        self,
        context: Context,
    ) -> None:
        super().__init__(context)
        self.pages = context.pages
        self.slug_fileid_mapping: Dict[str, FileId] = {
            key.without_known_suffix: key for key in self.pages
        }

    @staticmethod
    def is_bound(node: n.Node, search_text: Optional[str]) -> bool:
        """Helper function to determine if the given node contains specified start-after or end-before text.

        Note: For now, we are only splicing included files based on Comments and TargetIdentifier nodes.
        Comments have Text nodes as children; Labels have TargetIdentifiers as children."""
        if isinstance(node, n.Comment):
            if node.children and isinstance(node.children[0], n.Text):
                comment_text = node.children[0].get_text()
                return search_text == comment_text
        elif isinstance(node, n.Target):
            # TODO: get_child_of_type
            if node.domain == "std" and node.name == "label":
                if node.children and isinstance(node.children[0], n.TargetIdentifier):
                    target_identifier = node.children[0]
                    if target_identifier.ids:
                        return search_text in target_identifier.ids
        return False

    def bound_included_AST(
        self,
        nodes: MutableSequence[n.Node],
        start_after_text: Optional[str],
        end_before_text: Optional[str],
    ) -> Tuple[MutableSequence[n.Node], bool, bool]:
        """Given an AST in the form of nodes, return a subgraph of that AST by removing nodes 'outside' of
        the bound formed by the nodes containing the start_after_text or end_before_text. In in-order traversal,
        a node is considered 'outside' the subgraph if it precedes and is not any ancestor of the start-after node,
        or if it succeeds and is not any ancestor of the end-before node."""

        start_index, end_index = 0, len(nodes)
        any_start, any_end = False, False

        # For any given node: if the start_after node is within this node's subtree, do not include any
        # preceding siblings of this node in the resulting AST; if the end_before node is within this
        # node's subtree, then do not include any succeeding siblings of this node.
        for i, node in enumerate(nodes):
            has_start, has_end = False, False
            # Determine if this node itself (not a child node) contains a bound
            is_start = IncludeHandler.is_bound(node, start_after_text)
            is_end = IncludeHandler.is_bound(node, end_before_text)
            # Recursively search the child nodes for bounds
            if isinstance(node, n.Parent):
                children, has_start, has_end = self.bound_included_AST(
                    node.children, start_after_text, end_before_text
                )
                node.children = children
            if is_start or has_start:
                any_start = True
                start_index = i
            if is_end or has_end:
                any_end = True
                end_index = i
        if start_index > end_index:
            raise Exception("start-after text should precede end-before text")
        # Remove sibling nodes preceding and succeeding the nodes containing the bounds in their subtrees
        return nodes[start_index : end_index + 1], any_start, any_end

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name not in {
            "include",
            "sharedinclude",
        }:
            return

        def get_include_argument(node: n.Directive) -> str:
            """Get filename of include"""
            argument_list = node.argument
            assert len(argument_list) > 0
            return argument_list[0].value

        argument = get_include_argument(node)
        include_slug = clean_slug(argument)
        include_fileid = self.slug_fileid_mapping.get(include_slug)
        # Some `include` FileIds in the mapping include file extensions (.yaml) and others do not
        # This will likely be resolved by DOCSP-7159 https://jira.mongodb.org/browse/DOCSP-7159
        if include_fileid is None:
            include_slug = argument.strip("/")
            include_fileid = self.slug_fileid_mapping.get(include_slug)

            # XXX: End if we can't find a file. Diagnostic SHOULD have already been raised,
            # but it isn't necessarily possible to say for sure. Validation should be moved
            # here.
            if include_fileid is None:
                return

        include_page = self.pages.get(include_fileid)
        assert include_page is not None
        ast = include_page.ast
        assert isinstance(ast, n.Parent)
        deep_copy_children: MutableSequence[n.Node] = [util.fast_deep_copy(ast)]

        # TODO: Move subgraphing implementation into parse layer, where we can
        # ideally take subgraph of the raw RST
        start_after_text = node.options.get("start-after")
        end_before_text = node.options.get("end-before")

        if start_after_text or end_before_text:
            line = node.span[0]
            any_start, any_end = False, False
            try:
                # Returns a subgraph of the AST based on text bounds
                deep_copy_children, any_start, any_end = self.bound_included_AST(
                    deep_copy_children, start_after_text, end_before_text
                )
            except Exception as e:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidInclude(str(e), line)
                )
            # Confirm that we found all specified text (with helpful diagnostic )message if not)
            msg = "Please be sure your text is a comment or label. Search is case-sensitive."
            if start_after_text and not any_start:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidInclude(
                        f"Could not find specified start-after text: '{start_after_text}'. {msg}",
                        line,
                    )
                )
            if end_before_text and not any_end:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidInclude(
                        f"Could not find specified end-before text: '{end_before_text}'. {msg}",
                        line,
                    )
                )

        # This is a bit sketchy, but retain replacement directives for replacement processing later
        node.children = [
            child
            for child in node.children
            if isinstance(child, n.Directive) and child.name == "replacement"
        ]
        node.children.extend(deep_copy_children)


class NamedReferenceHandlerPass1(Handler):
    """Identify non-anonymous hyperlinks (i.e. those defined with a single underscore) and save them according to {name: url}.
    Attach the associated URL to any uses of this named reference.
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.named_references: Dict[str, str] = {}

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.NamedReference):
            return

        self.named_references[node.refname] = node.refuri


class NamedReferenceHandlerPass2(Handler):
    """Identify non-anonymous hyperlinks (i.e. those defined with a single underscore) and save them according to {name: url}.
    Attach the associated URL to any uses of this named reference.
    """

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Reference):
            return

        if node.refuri:
            # Node is already populated with url; nothing to do
            return

        refuri = self.context[NamedReferenceHandlerPass1].named_references.get(
            node.refname
        )
        if refuri is None:
            line = node.span[0]
            self.context.diagnostics[fileid_stack.current].append(
                TargetNotFound("extlink", node.refname, line)
            )
            return

        node.refuri = refuri


class ContentsHandler(Handler):
    """Identify all headings on a given page. If a contents directive appears on the page, save list of headings as a page-level option."""

    class HeadingData(NamedTuple):
        depth: int
        id: str
        title: Sequence[n.InlineNode]

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.contents_depth = sys.maxsize
        self.current_depth = 0
        self.has_contents_directive = False
        self.headings: List[ContentsHandler.HeadingData] = []

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.contents_depth = sys.maxsize
        self.current_depth = 0
        self.has_contents_directive = False
        self.headings = []

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.has_contents_directive:
            return

        if isinstance(page.ast, n.Root):
            heading_list = [
                {
                    "depth": h.depth,
                    "id": h.id,
                    "title": [node.serialize() for node in h.title],
                }
                for h in self.headings
                if h.depth - 1 <= self.contents_depth
            ]
            if heading_list:
                page.ast.options["headings"] = heading_list

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.Section):
            self.current_depth += 1
            return

        if isinstance(node, n.Directive) and node.name == "contents":
            if self.has_contents_directive:
                self.context.diagnostics[fileid_stack.current].append(
                    DuplicateDirective(node.name, node.start[0])
                )
                return

            self.has_contents_directive = True
            self.contents_depth = int(node.options.get("depth", sys.maxsize))
            return

        if self.current_depth - 1 > self.contents_depth:
            return

        # Omit title headings (depth = 1) from heading list
        if isinstance(node, n.Heading) and self.current_depth > 1:
            self.headings.append(
                ContentsHandler.HeadingData(self.current_depth, node.id, node.children)
            )

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.Section):
            self.current_depth -= 1


class TabsSelectorHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.selectors: Dict[str, List[Dict[str, MutableSequence[n.Text]]]] = {}

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive):
            return

        if node.name == "tabs-pillstrip" or node.name == "tabs-selector":
            if len(node.argument) == 0:
                return

            tabset_name: str = node.argument[0].get_text()
            # Handle naming discrepancy between .. tabs-pillstrip:: languages and .. tabs-drivers::
            if tabset_name == "languages":
                tabset_name = "drivers"

            # Avoid overwriting previously seen tabsets if another tabs-pillstrip directive is encountered
            if tabset_name in self.selectors:
                self.context.diagnostics[fileid_stack.current].append(
                    DuplicateDirective(node.name, node.start[0])
                )
                return

            self.selectors[tabset_name] = []
            return

        if len(self.selectors) == 0 or node.name != "tabs":
            return

        tabset_name = node.options.get("tabset", "")
        if tabset_name in self.selectors:
            tabs = {
                tab.options["tabid"]: tab.argument
                for tab in node.get_child_of_type(n.Directive)
                if tab.name == "tab" and "tabid" in tab.options
            }
            self.selectors[tabset_name].append(tabs)

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.selectors = {}

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if len(self.selectors) == 0:
            return

        for tabset_name, tabsets in self.selectors.items():
            if len(tabsets) == 0:
                # Warn if tabs-selector is used without corresponding tabset
                self.context.diagnostics[fileid_stack.current].append(ExpectedTabs(0))
                return
            if not all(len(t) == len(tabsets[0]) for t in tabsets):
                # If all tabsets are not the same length, identify tabs that do not appear in every tabset
                tabset_sets = [set(t.keys()) for t in tabsets]
                union = set.union(*tabset_sets)
                intersection = set.intersection(*tabset_sets)
                error_tabs = union - intersection
                self.context.diagnostics[fileid_stack.current].append(
                    MissingTab(error_tabs, 0)
                )

            if isinstance(page.ast, n.Root):
                if not page.ast.options.get("selectors"):
                    page.ast.options["selectors"] = {}

                assert isinstance(page.ast.options["selectors"], Dict)
                page.ast.options["selectors"][tabset_name] = {
                    tabid: [node.serialize() for node in title]
                    for tabid, title in tabsets[0].items()
                }


class TargetHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.target_counter: typing.Counter[str] = collections.Counter()
        self.targets = context[TargetDatabase]

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Target):
            return

        # Frankly, this is silly. We just pick the longest identifier. This is arbitrary,
        # and we can consider this behavior implementation-defined to be changed later if needed.
        # It just needs to be something consistent.
        identifiers = list(node.get_child_of_type(n.TargetIdentifier))
        candidates = [
            max(identifier.ids, key=len) for identifier in identifiers if identifier.ids
        ]

        if not candidates:
            return

        chosen_id = max(candidates, key=len)
        chosen_html_id = f"{node.domain}-{node.name}-{util.make_html5_id(chosen_id)}"

        # Disambiguate duplicate IDs, should they occur.
        counter = self.target_counter[chosen_html_id]
        if counter > 0:
            chosen_html_id += f"-{counter}"
        self.target_counter[chosen_html_id] += 1
        node.html_id = chosen_html_id

        for target_node in identifiers:
            if not target_node.children:
                title: List[n.InlineNode] = []
            else:
                title = list(target_node.children)

            target_ids = target_node.ids
            self.targets.define_local_target(
                node.domain,
                node.name,
                target_ids,
                fileid_stack.root,
                title,
                chosen_html_id,
            )

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.target_counter.clear()


class HeadingHandler(Handler):
    """Construct a slug-title mapping of all pages in property, and rewrite
    heading IDs so as to be unique."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.heading_counter: typing.Counter[str] = collections.Counter()
        self.targets = context[TargetDatabase]
        self.slug_title_mapping: Dict[str, Sequence[n.InlineNode]] = {}

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.heading_counter.clear()

    def get_title(self, slug: str) -> Optional[Sequence[n.InlineNode]]:
        return self.slug_title_mapping.get(slug)

    def __contains__(self, slug: str) -> bool:
        return slug in self.slug_title_mapping

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Heading):
            return

        counter = self.heading_counter[node.id]
        self.heading_counter[node.id] += 1
        if counter > 0:
            node.id += f"-{counter}"

        slug = fileid_stack.root.without_known_suffix

        # Save the first heading we encounter to the slug title mapping
        if slug not in self.slug_title_mapping:
            self.targets.define_local_target(
                "std",
                "doc",
                (slug,),
                fileid_stack.root,
                node.children,
                util.make_html5_id(node.id),
            )
            self.slug_title_mapping[slug] = node.children
            self.targets.define_local_target(
                "std",
                "doc",
                (fileid_stack.root.without_known_suffix,),
                fileid_stack.root,
                node.children,
                util.make_html5_id(node.id),
            )


class BannerHandler(Handler):
    """Traverse a series of pages matching specified targets in Snooty.toml
    and append Banner directive nodes"""

    def __init__(self, context: Context) -> None:
        self.banners = context[ProjectConfig].banner_nodes
        self.root = context[ProjectConfig].root

    def __find_target_insertion_node(self, node: n.Parent[n.Node]) -> Optional[n.Node]:
        """Search via BFS for the first 'section' from a root node, arbitrarily terminating early if
        no 'section' is found within the first 50 nodes."""
        queue: List[n.Node] = list(node.children)
        curr_iteration = 0
        max_iteration = 50

        insertion_node = None

        while queue and curr_iteration < max_iteration:
            candidate = queue.pop(0)
            if candidate.type == "section":
                insertion_node = candidate
                break
            if isinstance(candidate, n.Parent):
                queue.extend(candidate.children)

            curr_iteration += 1
        return insertion_node

    def __determine_banner_index(self, node: n.Parent[n.Node]) -> int:
        """Determine if there's a heading within the first level of the target insertion node's children.
        If so, return the index position after the first detected heading. Otherwise, return 0."""
        return (
            next(
                (
                    idx
                    for idx, child in enumerate(node.children)
                    if isinstance(child, n.Heading)
                ),
                0,
            )
            + 1
        )

    def __page_target_match(
        self, targets: List[str], page: Page, fileid: FileId
    ) -> bool:
        """Check if page matches target specified, but assert to ensure this does not run on includes"""
        assert fileid.suffix == ".txt"

        page_path_relative_to_source = page.source_path.relative_to(
            self.root / "source"
        )

        for target in targets:
            if page_path_relative_to_source.match(target):
                return True
        return False

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        """Attach a banner as specified throughout project for target pages"""
        for banner in self.banners:
            if not self.__page_target_match(banner.targets, page, fileid_stack.current):
                continue

            banner_parent = self.__find_target_insertion_node(page.ast)
            if isinstance(banner_parent, n.Parent):
                target_insertion = self.__determine_banner_index(banner_parent)
                assert banner_parent is not None
                banner_parent.children.insert(
                    target_insertion, util.fast_deep_copy(banner.node)
                )


class IAHandler(Handler):
    """Identify IA directive on a page and save a list of its entries as a page-level option."""

    class IAData(NamedTuple):
        title: Sequence[n.InlineNode]
        url: Optional[str]
        slug: Optional[str]
        project_name: Optional[str]
        primary: Optional[bool]

        def serialize(self) -> n.SerializedNode:
            result: n.SerializedNode = {
                "title": [node.serialize() for node in self.title],
            }

            if self.project_name:
                result["project_name"] = self.project_name
            if self.slug:
                result["slug"] = self.slug
            if self.url:
                result["url"] = self.url
            if self.primary is not None:
                result["primary"] = self.primary

            return result

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.ia: List[IAHandler.IAData] = []

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if (
            not isinstance(node, n.Directive)
            or not node.name == "ia"
            or not node.domain == ""
        ):
            return

        if self.ia:
            self.context.diagnostics[fileid_stack.current].append(
                DuplicateDirective(node.name, node.start[0])
            )
            return

        for entry in node.get_child_of_type(n.Directive):
            if entry.name != "entry":
                line = node.span[0]
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidChild(entry.name, "ia", "entry", line)
                )
                continue

            if not entry.options.get("url"):
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidIAEntry(
                        "IA entry directives must include the :url: option",
                        node.span[0],
                    )
                )
                continue

            parsed = urllib.parse.urlparse(entry.options.get("url"))
            if parsed.scheme:
                url = entry.options.get("url")
                slug = None
            else:
                url = None
                slug = entry.options.get("url")

            if slug and not self.context[HeadingHandler].get_title(clean_slug(slug)):
                self.context.diagnostics[fileid_stack.current].append(
                    MissingTocTreeEntry(slug, node.span[0])
                )
                continue

            title: Sequence[n.InlineNode] = []
            if len(entry.argument) > 0:
                title = entry.argument
            elif slug:
                title = self.context[HeadingHandler].get_title(clean_slug(slug)) or []

            project_name = entry.options.get("project-name")
            if project_name and not url:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidIAEntry(
                        "IA entry directives with :project-name: option must include :url: option",
                        node.span[0],
                    )
                )
                continue

            if url and not title:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidIAEntry(
                        "IA entries to external URLs must include titles",
                        node.span[0],
                    )
                )
                continue

            self.ia.append(
                IAHandler.IAData(
                    title,
                    url,
                    slug,
                    project_name,
                    bool(entry.options.get("primary", False)) if project_name else None,
                )
            )

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.ia = []

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.ia:
            return

        if isinstance(page.ast, n.Root):
            page.ast.options["ia"] = [entry.serialize() for entry in self.ia]


class SubstitutionHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.project_config = context[ProjectConfig]
        self.substitution_definitions: Dict[str, MutableSequence[n.InlineNode]] = {}
        self.include_replacement_definitions: List[
            Dict[str, MutableSequence[n.Node]]
        ] = []
        self.unreplaced_nodes: List[
            Tuple[
                Union[n.SubstitutionReference, n.BlockSubstitutionReference],
                FileId,
                int,
            ]
        ] = []
        self.seen_definitions: Optional[Set[str]] = None

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        """When a substitution is defined, add it to the page's index.

        When a substitution is referenced, populate its children if possible.
        If not, save this node to be populated at the end of the page.
        """

        if isinstance(node, n.Directive):
            if node.name not in {"include", "sharedinclude"}:
                return

            definitions: Dict[str, MutableSequence[n.Node]] = {}
            self.include_replacement_definitions.append(definitions)
            for replacement_directive in node.get_child_of_type(n.Directive):
                if replacement_directive.name != "replacement":
                    continue

                arg = "".join(
                    x.get_text() for x in replacement_directive.argument
                ).strip()
                definitions[arg] = replacement_directive.children

        elif isinstance(node, n.SubstitutionDefinition):
            self.substitution_definitions[node.name] = node.children
            self.seen_definitions = set()

        elif isinstance(node, n.SubstitutionReference):
            inline_substitution = self.search_inline(node, fileid_stack)
            if inline_substitution is not None:
                node.children = inline_substitution
            else:
                # Save node in order to populate it at the end of the page
                self.unreplaced_nodes.append((node, fileid_stack.current, node.span[0]))

            if self.seen_definitions is not None:
                self.seen_definitions.add(node.name)

        elif isinstance(node, n.BlockSubstitutionReference):
            block_substitution = self.search_block(node, fileid_stack)
            if block_substitution is not None:
                node.children = block_substitution
            else:
                # Save node in order to populate it at the end of the page
                self.unreplaced_nodes.append((node, fileid_stack.current, node.span[0]))

            if self.seen_definitions is not None:
                self.seen_definitions.add(node.name)

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.SubstitutionDefinition):
            self.seen_definitions = None
        elif isinstance(node, n.Directive) and node.name in {
            "include",
            "sharedinclude",
        }:
            self.include_replacement_definitions.pop()

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        """Attempt to populate any yet-unresolved substitutions (substitutions defined after usage) .

        Clear definitions and unreplaced nodes for the next page.
        """
        for node, fileid, line in self.unreplaced_nodes:
            substitution = self.substitution_definitions.get(node.name)
            if substitution is not None:
                node.children = substitution
            else:
                self.context.diagnostics[fileid].append(
                    SubstitutionRefError(
                        f'Substitution reference could not be replaced: "|{node.name}|"',
                        line,
                    )
                )

        self.substitution_definitions = {}
        self.include_replacement_definitions = []
        self.unreplaced_nodes = []

    def search_inline(
        self, node: n.SubstitutionReference, fileid_stack: FileIdStack
    ) -> Optional[MutableSequence[n.InlineNode]]:
        result = self._search(node, fileid_stack)
        if result is None:
            return None

        # Ensure that we're only attempting to insert a single inline element. Otherwise,
        # it's not clear what the writer would want.
        substitution = extract_inline(result)
        if not substitution or len(substitution) != len(result):
            self.context.diagnostics[fileid_stack.current].append(
                InvalidContextError(
                    node.name,
                    node.span[0],
                )
            )
            return None

        return substitution

    def search_block(
        self, node: n.BlockSubstitutionReference, fileid_stack: FileIdStack
    ) -> Optional[MutableSequence[n.Node]]:
        result = self._search(node, fileid_stack)
        if result is None:
            return None

        # If we're injecting inline nodes, wrap them in a paragraph
        return [n.Paragraph(node.span, [el]) if isinstance(el, n.InlineNode) else el for el in result]  # type: ignore

    def _search(
        self,
        node: Union[n.BlockSubstitutionReference, n.SubstitutionReference],
        fileid_stack: FileIdStack,
    ) -> Optional[Union[MutableSequence[n.Node], MutableSequence[n.InlineNode]]]:
        name = node.name

        # Detect substitution loop
        if self.seen_definitions is not None and name in self.seen_definitions:
            # Catch circular substitution
            try:
                del self.substitution_definitions[name]
            except KeyError:
                pass
            self.context.diagnostics[fileid_stack.current].append(
                SubstitutionRefError(
                    f'Circular substitution definition referenced: "{name}"',
                    node.span[0],
                )
            )
            return None

        # Resolution order: include parameters, definitions from page, definitions from snooty.toml
        # First, check if there are any parameters provided by our immediate parent
        try:
            return util.fast_deep_copy(self.include_replacement_definitions[-1][name])
        except (IndexError, KeyError):
            pass

        # Now try to get a substitution from page.
        substitution = self.substitution_definitions.get(
            name
        ) or self.project_config.substitution_nodes.get(name)

        return util.fast_deep_copy(substitution)


class AddTitlesToLabelTargetsHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.pending_targets: List[n.Node] = []

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, (n.Target, n.Section, n.TargetIdentifier)):
            self.pending_targets = []

        if isinstance(node, n.Target) and node.domain == "std" and node.name == "label":
            self.pending_targets.extend(node.children)
        elif isinstance(node, n.Section):
            for target in self.pending_targets:
                heading = next(node.get_child_of_type(n.Heading), None)
                if heading is not None:
                    assert isinstance(target, n.Parent)
                    target.children = heading.children
            self.pending_targets = []


class RefsHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.project_config = context[ProjectConfig]
        self.targets = context[TargetDatabase]

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        """When a node of type ref_role is encountered, ensure that it references a valid target.

        If so, append the full URL to the AST node. If not, throw an error.
        """
        if not isinstance(node, n.RefRole):
            return
        key = f"{node.domain}:{node.name}"

        if key == "std:doc":
            if not node.children:
                # If title is not explicitly given, search slug-title mapping for the page's title
                self._attach_doc_title(fileid_stack, node)
            return

        key += f":{node.target}"

        # Add title and link target to AST
        target_candidates = self.targets[key]
        if not target_candidates:
            # insert title and raise diagnostic
            line = node.span[0]
            target_dict = specparser.SPEC.rstobject
            target_key = f"{node.domain}:{node.name}"
            title = node.target
            # abstract title from node's target to insert into new text node
            if target_key in target_dict and target_dict[target_key].prefix:
                title = title.replace(f"{target_dict[target_key].prefix}.", "")
            text_node = n.Text((line,), title)
            injection_candidate = get_title_injection_candidate(node)

            if injection_candidate is not None:
                injection_candidate.children = [text_node]

            self.context.diagnostics[fileid_stack.current].append(
                TargetNotFound(node.name, node.target, line)
            )
            return

        if len(target_candidates) > 1:
            # Try to prune down the options
            target_candidates = self.attempt_disambugation(
                fileid_stack.root, target_candidates
            )

        if len(target_candidates) > 1:
            line = node.span[0]
            candidate_descriptions = []
            for candidate in target_candidates:
                if isinstance(candidate, TargetDatabase.InternalResult):
                    candidate_descriptions.append(candidate.result[0])
                else:
                    candidate_descriptions.append(candidate.url)

            self.context.diagnostics[fileid_stack.current].append(
                AmbiguousTarget(node.name, node.target, candidate_descriptions, line)
            )

        # Choose the most recently-defined target candidate if it is ambiguous
        result = target_candidates[-1]
        node.target = result.canonical_target_name
        if isinstance(result, TargetDatabase.InternalResult):
            node.fileid = result.result
        else:
            node.url = result.url
        injection_candidate = get_title_injection_candidate(node)
        # If there is no explicit title given, use the target's title
        if injection_candidate is not None:
            cloned_title_nodes: MutableSequence[n.Node] = list(
                deepcopy(node) for node in result.title
            )
            for title_node in cloned_title_nodes:
                deep_copy_position(node, title_node)

            # Label abbreviation is underspecified. Good luck!
            if "~" in node.flag and cloned_title_nodes:
                node_to_abbreviate = cloned_title_nodes[0]
                if isinstance(node_to_abbreviate, n.Text):
                    index = node_to_abbreviate.value.rfind(".")
                    new_value = node_to_abbreviate.value[index + 1 :].strip()

                    if new_value:
                        node_to_abbreviate.value = new_value

            injection_candidate.children = cloned_title_nodes

    def attempt_disambugation(
        self, fileid: FileId, candidates: Sequence[TargetDatabase.Result]
    ) -> Sequence[TargetDatabase.Result]:
        """Given multiple possible targets we can link to, attempt to narrow down the
        list to one probably-intended target under a set of narrow circumstances."""

        # If there is a single local candidate, choose that.
        local_candidates: List[TargetDatabase.InternalResult] = [
            candidate
            for candidate in candidates
            if isinstance(candidate, TargetDatabase.InternalResult)
        ]
        if len(local_candidates) == 1:
            return [local_candidates[0]]

        # If there is a target defined in the current context, use that.
        current_fileid_candidates = [
            candidate
            for candidate in local_candidates
            if candidate.result[0] == fileid.without_known_suffix
        ]
        if len(current_fileid_candidates) == 1:
            return [current_fileid_candidates[0]]

        return candidates

    def _attach_doc_title(self, fileid_stack: FileIdStack, node: n.RefRole) -> None:
        target_fileid = None if node.fileid is None else node.fileid[0]
        if not target_fileid:
            line = node.span[0]
            self.context.diagnostics[fileid_stack.current].append(
                ExpectedPathArg(node.name, line)
            )
            return

        relative, _ = util.reroot_path(
            FileId(target_fileid), fileid_stack.root, self.project_config.source_path
        )
        slug = clean_slug(relative.as_posix())
        title = self.context[HeadingHandler].get_title(slug)

        if not title:
            line = node.span[0]
            self.context.diagnostics[fileid_stack.current].append(
                UnnamedPage(target_fileid, line)
            )
            return

        node.children = [deepcopy(node) for node in title]


class Postprocessor:
    """Handles all postprocessing operations on parsed AST files.

    The only method that should be called on an instance of Postprocessor is run(). This method
    handles calling all other methods and ensures that parse operations are run in the correct order."""

    PASSES: Sequence[Sequence[Type[Handler]]] = [
        [IncludeHandler],
        [SubstitutionHandler],
        [
            HeadingHandler,
            AddTitlesToLabelTargetsHandler,
            ProgramOptionHandler,
            TabsSelectorHandler,
            ContentsHandler,
            BannerHandler,
        ],
        [TargetHandler, IAHandler, NamedReferenceHandlerPass1],
        [RefsHandler, NamedReferenceHandlerPass2],
    ]

    def __init__(self, project_config: ProjectConfig, targets: TargetDatabase) -> None:
        self.project_config = project_config
        self.toctree: Dict[str, SerializableType] = {}
        self.pages: Dict[FileId, Page] = {}
        self.targets = targets
        self.pending_program: Optional[SerializableType] = None

    def run(
        self, pages: Dict[FileId, Page]
    ) -> Tuple[Dict[str, SerializableType], Dict[FileId, List[Diagnostic]]]:
        """Run all postprocessing operations and return a dictionary containing the metadata document to be saved."""
        if not pages:
            return {}, {}

        self.pages = pages
        context = Context(pages)
        context.add(self.project_config)
        context.add(self.targets)

        for project_pass in self.PASSES:
            instances = [ty(context) for ty in project_pass]
            for instance in instances:
                context.add(instance)

            self.run_event_parser(
                [
                    (EventParser.OBJECT_START_EVENT, instance.enter_node)
                    for instance in instances
                    if instance.__class__.enter_node is not Handler.enter_node
                ]
                + [
                    (EventParser.OBJECT_END_EVENT, instance.exit_node)
                    for instance in instances
                    if instance.__class__.exit_node is not Handler.exit_node
                ],
                [
                    (EventParser.PAGE_START_EVENT, instance.enter_page)
                    for instance in instances
                    if instance.__class__.enter_page is not Handler.enter_page
                ]
                + [
                    (EventParser.PAGE_END_EVENT, instance.exit_page)
                    for instance in instances
                    if instance.__class__.exit_page is not Handler.exit_page
                ],
            )

        document = self.generate_metadata(context)
        self.finalize(context, document)
        return document, context.diagnostics

    def finalize(self, context: Context, metadata: n.SerializedNode) -> None:
        pass

    @classmethod
    def generate_metadata(cls, context: Context) -> n.SerializedNode:
        project_config = context[ProjectConfig]
        document: Dict[str, SerializableType] = {}
        document["title"] = project_config.title
        if project_config.deprecated_versions:
            document["deprecated_versions"] = project_config.deprecated_versions
        # Update metadata document with key-value pairs defined in event parser
        document["slugToTitle"] = {
            k: [node.serialize() for node in v]
            for k, v in context[HeadingHandler].slug_title_mapping.items()
        }
        # Run postprocessing operations related to toctree and append to metadata document.
        # If iatree is found, use it to generate breadcrumbs and parent paths and save it to metadata as well.
        iatree = cls.build_iatree(context)
        toctree = cls.build_toctree(context)
        if iatree and toctree.get("children"):
            context.diagnostics[FileId("index.txt")].append(InvalidTocTree(0))

        tree = iatree or toctree
        document.update(
            {
                "toctree": toctree,
                "toctreeOrder": cls.toctree_order(tree),
                "parentPaths": cls.breadcrumbs(tree),
            }
        )

        if iatree:
            document["iatree"] = iatree

        return document

    def run_event_parser(
        self,
        node_listeners: Iterable[Tuple[str, Callable[[FileIdStack, n.Node], None]]],
        page_listeners: Iterable[Tuple[str, Callable[[FileIdStack, Page], None]]] = (),
    ) -> None:
        event_parser = EventParser()
        for event, node_listener in node_listeners:
            event_parser.add_event_listener(event, node_listener)

        for event, page_listener in page_listeners:
            event_parser.add_event_listener(event, page_listener)

        event_parser.consume(
            (k, v) for k, v in self.pages.items() if k.suffix == ".txt"
        )

    @staticmethod
    def build_iatree(context: Context) -> Dict[str, SerializableType]:
        def _get_page_from_slug(current_page: Page, slug: str) -> Optional[Page]:
            relative, _ = util.reroot_path(
                FileId(slug),
                current_page.source_path,
                context[ProjectConfig].source_path,
            )

            try:
                fileid_with_ext = context[IncludeHandler].slug_fileid_mapping[
                    relative.as_posix()
                ]
            except KeyError:
                return None
            return context.pages.get(fileid_with_ext)

        def iterate_ia(page: Page, result: Dict[str, SerializableType]) -> None:
            """Construct a tree of similar structure to toctree. Starting from root, identify ia object on page and recurse on its entries to build a tree. Includes all potential properties of an entry including title, URI, project name, and primary status."""
            if not isinstance(page.ast, n.Root):
                return

            ia = page.ast.options.get("ia")
            if not isinstance(ia, List):
                return
            for entry in ia:
                curr: Dict[str, SerializableType] = {**entry, "children": []}
                if isinstance(result["children"], List):
                    result["children"].append(curr)

                slug = curr.get("slug")
                if isinstance(slug, str):
                    child = _get_page_from_slug(page, slug)
                    if child:
                        iterate_ia(child, curr)

        starting_page = context.pages.get(FileId("index.txt"))

        if not starting_page:
            return {}
        if not isinstance(starting_page.ast, n.Root):
            return {}
        if "ia" not in starting_page.ast.options:
            return {}

        title: Sequence[n.InlineNode] = context[HeadingHandler].get_title("index") or [
            n.Text((0,), context[ProjectConfig].title)
        ]
        root: Dict[str, SerializableType] = {
            "title": [node.serialize() for node in title],
            "slug": "/",
            "children": [],
        }
        iterate_ia(starting_page, root)
        return root

    @classmethod
    def build_toctree(cls, context: Context) -> Dict[str, SerializableType]:
        """Build property toctree"""

        # The toctree must begin at either `contents.txt` or `index.txt`.
        # Generally, repositories will have one or the other; but, if a repo has both,
        # the starting point will be `contents.txt`.
        candidates = (FileId("contents.txt"), FileId("index.txt"))
        starting_fileid = next(
            (candidate for candidate in candidates if candidate in context.pages), None
        )
        if starting_fileid is None:
            return {}

        # Build the toctree
        root: Dict[str, SerializableType] = {
            "title": [n.Text((0,), context[ProjectConfig].title).serialize()],
            "slug": "/",
            "children": [],
        }
        ast = context.pages[starting_fileid].ast

        toc_landing_pages = [
            clean_slug(slug) for slug in context[ProjectConfig].toc_landing_pages
        ]
        cls.find_toctree_nodes(
            context, starting_fileid, ast, root, toc_landing_pages, {starting_fileid}
        )

        return root

    @classmethod
    def find_toctree_nodes(
        cls,
        context: Context,
        fileid: FileId,
        ast: n.Node,
        node: Dict[str, Any],
        toc_landing_pages: List[str],
        visited_file_ids: Set[FileId] = set(),
    ) -> None:
        """Iterate over AST to find toctree directives and construct their nodes for the unified toctree"""

        # Base case: stop iterating over AST
        if not isinstance(ast, n.Parent):
            return

        if isinstance(ast, n.TocTreeDirective):
            # Recursively build the tree for each toctree node in this entries list
            for entry in ast.entries:
                toctree_node: Dict[str, object] = {}
                if entry.url:
                    toctree_node = {
                        "title": [n.Text((0,), entry.title).serialize()]
                        if entry.title
                        else None,
                        "url": entry.url,
                        "children": [],
                    }
                elif entry.slug:
                    # Recursively build the tree for internal links
                    slug_cleaned = clean_slug(entry.slug)

                    # Ensure that the user-specified slug is an existing page. We want to add this error
                    # handling to the initial parse layer, but this works for now.
                    # https://jira.mongodb.org/browse/DOCSP-7941
                    try:
                        slug_fileid: FileId = context[
                            IncludeHandler
                        ].slug_fileid_mapping[slug_cleaned]
                    except KeyError:
                        context.diagnostics[fileid].append(
                            MissingTocTreeEntry(slug_cleaned, ast.span[0])
                        )
                        continue

                    slug: str = slug_fileid.without_known_suffix

                    if entry.title:
                        title: SerializableType = [
                            n.Text((0,), entry.title).serialize()
                        ]
                    else:
                        title_nodes = context[HeadingHandler].get_title(slug)
                        title = (
                            [node.serialize() for node in title_nodes]
                            if title_nodes
                            else None
                        )

                    toctree_node = {
                        "title": title,
                        "slug": "/" if slug == "index" else slug,
                        "children": [],
                        "options": {"drawer": slug not in toc_landing_pages},
                    }

                    # Don't recurse on the index page
                    if slug_fileid not in visited_file_ids:
                        new_ast = context.pages[slug_fileid].ast
                        cls.find_toctree_nodes(
                            context,
                            slug_fileid,
                            new_ast,
                            toctree_node,
                            toc_landing_pages,
                            visited_file_ids.union({slug_fileid}),
                        )

                if toctree_node:
                    node["children"].append(toctree_node)

        # Locate the correct directive object containing the toctree within this AST
        for child_ast in ast.children:
            cls.find_toctree_nodes(
                context, fileid, child_ast, node, toc_landing_pages, visited_file_ids
            )

    @staticmethod
    def breadcrumbs(tree: Dict[str, SerializableType]) -> Dict[str, List[str]]:
        """Generate breadcrumbs for each page represented in the provided toctree"""
        page_dict: Dict[str, List[str]] = {}
        all_paths: List[Any] = []

        # Find all node to leaf paths for each node in the toctree
        if "children" in tree:
            assert isinstance(tree["children"], List)
            for node in tree["children"]:
                paths: List[str] = []
                get_paths(node, [], paths)
                all_paths.extend(paths)

        # Populate page_dict with a list of parent paths for each slug
        for path in all_paths:
            for i in range(len(path)):
                slug = path[i]
                page_dict[slug] = path[:i]
        return page_dict

    @staticmethod
    def toctree_order(tree: Dict[str, SerializableType]) -> List[str]:
        """Return a pre-order traversal of the toctree to be used for internal page navigation"""
        order: List[str] = []

        pre_order(tree, order)
        return order


def pre_order(node: Dict[str, Any], order: List[str]) -> None:
    if not node:
        return
    if "slug" in node:
        order.append(node["slug"])
    if "children" in node:
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
        elif "project_name" in node and node.get("primary"):
            path.append(node["project_name"])
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


class DevhubHandler(Handler):
    # TODO: Identify directives that should be exposed in the rstspec.toml to avoid hardcoding
    # These directives are represented as list nodes; they will return a list of strings
    LIST_FIELDS = {"devhub:products", "devhub:tags", ":languages"}
    # These directives have their content represented as children; they will return a list of nodes
    BLOCK_FIELDS = {"devhub:meta-description"}
    # These directives have their content represented as an argument; they will return a string
    ARG_FIELDS = {"devhub:level", "devhub:type", ":atf-image"}
    # These directives have their content represented as children, along with a series of options;
    # they will return a dictionary with all options represented, and with the content represented as a list of nodes whose key is `children`.
    OPTION_BLOCK_FIELDS = {":og", ":twitter"}

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        """To be called at the start of each page: reset the query field dictionary"""
        self.query_fields: Dict[str, Any] = {}

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        """To be called at the end of each page: append the query field dictionary to the
        top level of the page's class instance.
        """
        # Save page title to query_fields, if it exists
        slug = clean_slug(fileid_stack.current.as_posix())
        self.query_fields["slug"] = f"/{slug}" if slug != "index" else "/"
        title = self.context[HeadingHandler].get_title(slug)
        if title is not None:
            self.query_fields["title"] = [node.serialize() for node in title]

        page.query_fields = self.query_fields

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        """Extract fields from a page's AST and expose them as a queryable nested document in the page document."""
        if not isinstance(node, n.Directive):
            return

        key = f"{node.domain}:{node.name}"

        if key == "devhub:author":
            # Create a dict unifying the node's options and children
            author_obj: Dict[str, SerializableType] = {}
            author_obj.update(node.options)
            author_obj["children"] = [child.serialize() for child in node.children]

            self.query_fields.setdefault("author", []).append(author_obj)
        elif key == "devhub:related":
            # Save list of nodes (likely :doc: roles)
            self.query_fields[node.name] = []
            if len(node.children) > 0:
                first_child = node.children[0]
                assert isinstance(first_child, n.Parent)
                for item in first_child.children:
                    paragraph = item.children[0]
                    self.query_fields[node.name].append(
                        paragraph.children[0].serialize()
                    )
        elif key in {":pubdate", ":updated-date"}:
            date = node.options.get("date")
            if date:
                self.query_fields[node.name] = date
        elif key in self.OPTION_BLOCK_FIELDS:
            # Create a dict unifying the node's options and children
            node_obj: Dict[str, SerializableType] = {}
            node_obj.update(node.options)
            node_obj["children"] = [child.serialize() for child in node.children]

            self.query_fields[node.name] = node_obj
        elif key in self.ARG_FIELDS:
            if len(node.argument) > 0:
                self.query_fields[node.name] = node.argument[0].value
        elif key in self.BLOCK_FIELDS:
            self.query_fields[node.name] = [
                child.serialize() for child in node.children
            ]
        elif key in self.LIST_FIELDS:
            self.query_fields[node.name] = []
            if len(node.children) > 0:
                first_child = node.children[0]
                assert isinstance(first_child, n.Parent)
                list_items = first_child.children
                assert isinstance(list_items, List)
                for item in list_items:
                    text_candidate = get_deepest(item)
                    assert isinstance(text_candidate, n.Text)
                    self.query_fields[node.name].append(text_candidate.value)


class DevhubPostprocessor(Postprocessor):
    """Postprocess operation to be run if a project's default_domain is equal to 'devhub'"""

    PASSES: Sequence[Sequence[Type[Handler]]] = [
        [IncludeHandler],
        [SubstitutionHandler],
        [
            HeadingHandler,
            AddTitlesToLabelTargetsHandler,
            ProgramOptionHandler,
            TabsSelectorHandler,
            ContentsHandler,
            BannerHandler,
        ],
        [TargetHandler, IAHandler, NamedReferenceHandlerPass1],
        [RefsHandler, NamedReferenceHandlerPass2, DevhubHandler],
    ]

    def finalize(self, context: Context, metadata: n.SerializedNode) -> None:
        def clean_and_validate_page_group_slug(slug: str) -> Optional[str]:
            """Clean a slug and validate that it is a known page. If it is not, return None."""
            cleaned = clean_slug(slug)
            if cleaned not in context[HeadingHandler]:
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
            metadata.update({"pageGroups": page_groups})

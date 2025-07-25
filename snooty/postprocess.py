import collections
import errno
import logging
import os.path
import sys
import threading
import typing
import urllib.parse
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePath
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

import yaml

from . import n, specparser, util
from .builders import man
from .diagnostics import (
    AmbiguousTarget,
    CannotOpenFile,
    ChapterAlreadyExists,
    ChildlessRef,
    Diagnostic,
    DuplicatedExternalToc,
    DuplicateDirective,
    ExpectedPathArg,
    ExpectedTabs,
    FetchError,
    GuideAlreadyHasChapter,
    InvalidChapter,
    InvalidChild,
    InvalidContextError,
    InvalidIAEntry,
    InvalidIALinkedData,
    InvalidInclude,
    InvalidNestedTabStructure,
    InvalidOpenApiResponse,
    InvalidTocTree,
    InvalidVersion,
    MissingChild,
    MissingOption,
    MissingTab,
    MissingTocTreeEntry,
    NestedDirective,
    OrphanedPage,
    SubstitutionRefError,
    TargetNotFound,
    UnexpectedDirectiveOrder,
    UnknownDefaultTabId,
    UnnamedPage,
    UnsupportedFormat,
)
from .eventparser import EventParser, FileIdStack
from .flutter import check_type, checked
from .n import FileId, SerializableType
from .page import Page
from .target_database import TargetDatabase
from .types import Facet, ProjectConfig
from .util import EXT_FOR_PAGE, SOURCE_FILE_EXTENSIONS, bundle, is_txt_in_reserved_dir

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
    nodes: Union[MutableSequence[n.Node], MutableSequence[n.InlineNode]],
) -> Optional[MutableSequence[n.InlineNode]]:
    """Reach into a node and see if it's trivally transformable into an inline context
    without losing anything aside from a wrapping Paragraph."""
    if all(isinstance(node, n.InlineNode) for node in nodes):
        return cast(MutableSequence[n.InlineNode], nodes)

    node = nodes[0]
    if (
        len(nodes) == 1
        and isinstance(node, n.Paragraph)
        and all(isinstance(child, n.InlineNode) for child in node.children)
    ):
        return cast(MutableSequence[n.InlineNode], util.fast_deep_copy(node.children))

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


def propagate_facets(pages: Dict[FileId, Page], context: Context) -> None:
    """Scans through each directory starting at source/ and
    loads the facets.toml file if one exists. These values get propagated
    to each subsequent level to add them to the page.facets property if a
    facets.toml file does not exist in that child directory.
    """
    config = context[ProjectConfig]
    root = config.source_path
    parent_facets = None

    for base, _, files in os.walk(root):
        if "facets.toml" in files:
            facet_path = Path(os.path.join(base, "facets.toml"))
            curr_facets, diagnostics = config.load_facets_from_file(facet_path)

            if not curr_facets:
                context.diagnostics[config.get_fileid(facet_path)].extend(diagnostics)

            if parent_facets and curr_facets:
                parent_facets = config.merge_facets(parent_facets, curr_facets)
            elif curr_facets:
                parent_facets = curr_facets

        if parent_facets:
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext not in util.RST_EXTENSIONS and ext != ".ast":
                    continue

                file_path = Path(os.path.join(base, file))
                if is_txt_in_reserved_dir(file_path):
                    continue

                fileid = config.get_fileid(file_path)

                if ext == ".ast":
                    # .ast files have their .txt fileids spoofed
                    fileid = FileId(fileid.as_posix().replace(".ast", ".txt"))

                page = pages[fileid]
                page.facets = parent_facets


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
        Comments have Text nodes as children; Labels have TargetIdentifiers as children.
        """
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

        argument = "".join(arg.get_text() for arg in node.argument)
        if not argument:
            return

        include_slug = clean_slug(argument)
        include_fileid = self.slug_fileid_mapping.get(include_slug)
        # Some `include` FileIds in the mapping include file extensions (.yaml) and others do not
        # This will likely be resolved by DOCSP-7159 https://jira.mongodb.org/browse/DOCSP-7159
        if include_fileid is None:
            include_slug = argument.strip("/")
            include_fileid = self.slug_fileid_mapping.get(include_slug)

            if include_fileid is None:
                # sharedinclude diagnostics have already been raised in the JSONVisitor
                if node.name != "sharedinclude":
                    self.context.diagnostics[fileid_stack.current].append(
                        CannotOpenFile(
                            FileId(include_slug),
                            os.strerror(errno.ENOENT),
                            node.span[0],
                        )
                    )
                return

        include_page = self.pages.get(include_fileid)
        assert include_page is not None
        ast = include_page.ast
        self.context.pages[fileid_stack.root].static_assets.update(
            include_page.static_assets
        )
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
        self.named_references: Dict[FileId, Dict[str, str]] = defaultdict(dict)

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.NamedReference):
            return

        self.named_references[fileid_stack.root][node.refname] = node.refuri


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

        refuri = (
            self.context[NamedReferenceHandlerPass1]
            .named_references[fileid_stack.root]
            .get(node.refname)
        )
        if refuri is None:
            line = node.span[0]
            self.context.diagnostics[fileid_stack.current].append(
                TargetNotFound("extlink", node.refname, [], line)
            )
            return

        node.refuri = refuri


SelectorId = Dict[str, Union[str, Dict[str, str], "SelectorId"]]


class ContentsHandler(Handler):
    """Identify all headings on a given page. If a contents directive appears on the page, save list of headings as a page-level option."""

    class HeadingData(NamedTuple):
        depth: int
        id: str
        title: Sequence[n.InlineNode]
        selector_ids: SelectorId

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.contents_depth = sys.maxsize
        self.current_depth = 0
        self.has_contents_directive = False
        self.headings: List[ContentsHandler.HeadingData] = []
        self.scanned_pattern: List[Tuple[str, Union[str, Dict[str, str]]]] = []

    def scan_pattern(
        self, arr: List[Tuple[str, Union[str, Dict[str, str]]]]
    ) -> SelectorId:
        if not arr:
            return {}
        if len(arr) == 1:
            return {arr[0][0]: arr[0][1]}
        scanned_pattern: SelectorId = {
            arr[0][0]: arr[0][1],
            "children": self.scan_pattern(arr[1:]),
        }
        return scanned_pattern

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.contents_depth = sys.maxsize
        self.current_depth = 0
        self.has_contents_directive = False
        self.headings = []

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.has_contents_directive:
            return

        if isinstance(page.ast, n.Root):
            heading_list: SerializableType = [
                {
                    "depth": h.depth,
                    "id": h.id,
                    "title": [node.serialize() for node in h.title],
                    "selector_ids": h.selector_ids,
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

        if isinstance(node, n.Directive):
            if node.name == "method-option":
                self.scanned_pattern.append((node.name, node.options["id"]))
            elif node.name == "tab":
                self.scanned_pattern.append((node.name, node.options["tabid"]))
            elif node.name == "selected-content":
                assert isinstance(node, n.ComposableContent)
                self.scanned_pattern.append((node.name, node.selections))

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

        selector_ids = {}
        if len(self.scanned_pattern) > 0:
            selector_ids = self.scan_pattern(self.scanned_pattern)

        # Omit title headings (depth = 1) from heading list
        if isinstance(node, n.Heading) and self.current_depth > 1:
            self.headings.append(
                ContentsHandler.HeadingData(
                    self.current_depth, node.id, node.children, selector_ids
                )
            )

        if isinstance(node, n.Directive) and node.name == "collapsible":
            self.headings.append(
                ContentsHandler.HeadingData(
                    # Add 1 since section appears as a child
                    self.current_depth + 1,
                    node.options["id"],
                    [n.Text(node.span, node.options["heading"])],
                    selector_ids,
                )
            )

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.Directive) and (
            node.name in ["method-option", "tab", "selected-content"]
        ):
            self.scanned_pattern.pop()
        if isinstance(node, n.Section):
            self.current_depth -= 1


class TabsSelectorHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.default_tabs: Dict[str, str] = {}
        self.selectors: Dict[str, List[Dict[str, MutableSequence[n.Text]]]] = {}
        self.scanned_pattern: List[str] = []
        self.target_pattern = ["tabs", "tabs", "procedure"]

    def scan_for_pattern(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        starting_point = 0
        target_pattern_len = len(self.target_pattern)
        if len(self.scanned_pattern) > 0:
            for item in self.scanned_pattern:
                if item == self.target_pattern[starting_point]:
                    starting_point += 1
                if starting_point >= target_pattern_len:
                    self.context.diagnostics[fileid_stack.current].append(
                        InvalidNestedTabStructure(
                            " ".join(self.scanned_pattern), node.start[0]
                        )
                    )
                    return

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive):
            return

        self.scanned_pattern.append(node.name)

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

            if tabset_name == "drivers" and "default-tabid" in node.options:
                self.default_tabs[tabset_name] = node.options.get("default-tabid", "")

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

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive):
            return

        if node.name == "procedure":
            self.scan_for_pattern(fileid_stack, node)

        self.scanned_pattern.pop()

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.selectors = {}
        self.default_tabs = {}

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.scanned_pattern = []

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

                # If default_tabs are present, append to page options
                if tabset_name in self.default_tabs:
                    default_tab_is_in_selectors = (
                        self.default_tabs[tabset_name]
                        in page.ast.options["selectors"][tabset_name].keys()
                    )
                    if not default_tab_is_in_selectors:
                        self.context.diagnostics[fileid_stack.current].append(
                            UnknownDefaultTabId(self.default_tabs[tabset_name] or "", 0)
                        )
                        return

                    if not page.ast.options.get("default_tabs"):
                        page.ast.options["default_tabs"] = {}

                    assert isinstance(page.ast.options["default_tabs"], Dict)
                    page.ast.options["default_tabs"][tabset_name] = self.default_tabs[
                        tabset_name
                    ]


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
        if not (
            isinstance(node, n.Heading)
            or (isinstance(node, n.Directive) and node.name == "collapsible")
        ):
            return

        id = node.id if isinstance(node, n.Heading) else node.options.get("id", "")

        # ensure uniqueness within headings
        counter = self.heading_counter[id]
        self.heading_counter[id] += 1
        if counter > 0:
            if isinstance(node, n.Heading):
                node.id += f"-{counter}"
            if isinstance(node, n.Directive):
                node.options["id"] += f"-{counter}"

        if not isinstance(node, n.Heading):
            return

        slug = fileid_stack.root.without_known_suffix

        # Save the first heading we encounter to the slug title mapping
        if slug not in self.slug_title_mapping:
            self.targets.define_local_target(
                "std",
                "doc",
                (slug,),
                fileid_stack.root,
                node.children,
                util.make_html5_id(id),
            )
            self.slug_title_mapping[slug] = node.children
            self.targets.define_local_target(
                "std",
                "doc",
                (fileid_stack.root.without_known_suffix,),
                fileid_stack.root,
                node.children,
                util.make_html5_id(id),
            )


class TocTitleHandler(Handler):
    """Construct a slug - toctree label mapping of all pages in property"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.slug_title_mapping: Dict[str, str] = {}

    def get_title(self, slug: str) -> Optional[str]:
        return self.slug_title_mapping.get(slug)

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.TocTreeDirective):
            return

        for entry in node.entries:
            slug = entry.slug
            # Save the first heading we encounter to the slug title mapping
            if slug and entry.title and slug not in self.slug_title_mapping:
                self.slug_title_mapping[slug] = entry.title


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
        If so, return the index position after the first detected heading. Otherwise, return 0.
        """
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
        assert fileid.suffix == EXT_FOR_PAGE

        for target in targets:
            if page.fileid.match(target):
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


class GuidesHandler(Handler):
    """Constructs a dictionary of chapters and their data and returns metadata on individual guides."""

    @dataclass
    class ChapterData:
        id: str
        chapter_number: int
        description: Optional[str]
        guides: List[str]
        icon: Optional[str]

    @dataclass
    class GuideData:
        chapter_name: str = ""
        completion_time: int = 0
        description: MutableSequence[n.Node] = field(default_factory=list)
        title: Sequence[n.InlineNode] = field(default_factory=list)

        def serialize(self) -> n.SerializedNode:
            result: n.SerializedNode = {
                "chapter_name": self.chapter_name,
                "completion_time": self.completion_time,
                "description": [node.serialize() for node in self.description],
                "title": [node.serialize() for node in self.title],
            }
            return result

    def add_guides_metadata(self, document: Dict[str, SerializableType]) -> None:
        """Adds the guides-related metadata to the project's metadata document"""
        if self.chapters:
            document["chapters"] = {k: asdict(v) for k, v in self.chapters.items()}

        if self.guides:
            slug_title_mapping = self.context[HeadingHandler].slug_title_mapping
            for slug, title in slug_title_mapping.items():
                if slug in self.guides:
                    self.guides[slug].title = title
            document["guides"] = {k: v.serialize() for k, v in self.guides.items()}

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.chapters: Dict[str, GuidesHandler.ChapterData] = {}
        self.guides: Dict[str, GuidesHandler.GuideData] = defaultdict(
            GuidesHandler.GuideData
        )

    def __get_guides(
        self, chapter: n.Directive, chapter_title: str, current_file: FileId
    ) -> List[str]:
        """Returns the eligible guides that belong to a given chapter"""

        guides: List[str] = []

        for child in chapter.get_child_of_type(n.Directive):
            line = child.span[0]

            if child.name != "guide":
                self.context.diagnostics[current_file].append(
                    InvalidChild(child.name, "chapter", "guide", line, None)
                )
                continue

            guide_argument = child.argument
            if not guide_argument:
                self.context.diagnostics[current_file].append(
                    ExpectedPathArg(child.name, line)
                )
                continue

            guide_slug = clean_slug(guide_argument[0].get_text())

            current_guide_data = self.guides[guide_slug]
            if current_guide_data.chapter_name:
                self.context.diagnostics[current_file].append(
                    GuideAlreadyHasChapter(
                        guide_slug,
                        current_guide_data.chapter_name,
                        chapter_title,
                        line,
                    )
                )
                continue
            else:
                current_guide_data.chapter_name = chapter_title

            guides.append(guide_slug)

        return guides

    def __handle_chapter(self, chapter: n.Directive, current_file: FileId) -> None:
        """Saves a chapter's data into the handler's dictionary of chapters"""

        line = chapter.span[0]
        title_argument = chapter.argument
        if len(title_argument) != 1:
            self.context.diagnostics[current_file].append(
                InvalidChapter(
                    "Invalid title argument. The title should be plain text.", line
                )
            )
            return

        title = title_argument[0].get_text()
        if not title:
            self.context.diagnostics[current_file].append(
                InvalidChapter(
                    "Invalid title argument. The title should be plain text.", line
                )
            )
            return

        # DocUtilsParseError will be appended to diagnostics if there is no description
        description = chapter.options.get("description")
        if not description:
            return

        guides: List[str] = self.__get_guides(chapter, title, current_file)
        # A chapter should always have at least one guide
        if not guides:
            self.context.diagnostics[current_file].append(
                MissingChild("chapter", "guide", line)
            )
            return

        if not self.chapters.get(title):
            icon = chapter.options.get("icon")
            self.chapters[title] = GuidesHandler.ChapterData(
                util.make_html5_id(title).lower(),
                len(self.chapters) + 1,
                description,
                guides,
                icon,
            )
        else:
            self.context.diagnostics[current_file].append(
                ChapterAlreadyExists(title, line)
            )

    def __handle_include(self, node: n.Directive, current_file: FileId) -> None:
        """Looks for chapters nested within include directives."""

        if len(node.children) == 1:
            root = node.children[0]
            if isinstance(root, n.Root):
                self.__handle_chapters(root, current_file)

    def __handle_chapters(
        self, chapters: n.Parent[n.Node], current_file: FileId
    ) -> None:
        """Handles the nested directives found under the chapters directive."""

        line = chapters.span[0]

        for child in chapters.get_child_of_type(n.Directive):
            if child.name == "chapter":
                self.__handle_chapter(child, current_file)
            # Provide support for using an include for multiple chapters on a separate file
            elif child.name == "include":
                self.__handle_include(child, current_file)
            else:
                # Chapters directive should contain only chapter directives
                self.context.diagnostics[current_file].append(
                    InvalidChild(child.name, "chapters", "chapter", line)
                )
                continue

        if not self.chapters:
            self.context.diagnostics[current_file].append(
                MissingChild("chapters", "chapter", line)
            )

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive):
            return

        current_file: FileId = fileid_stack.current
        current_slug = clean_slug(current_file.without_known_suffix)

        if node.name == "chapters" and current_file == FileId("index.txt"):
            if self.chapters:
                return
            self.__handle_chapters(node, current_file)
        elif node.name == "time":
            if not node.argument:
                return
            try:
                completion_time = int(node.argument[0].get_text())
                self.guides[current_slug].completion_time = completion_time
            except ValueError:
                pass
        elif node.name == "short-description":
            self.guides[current_slug].description = node.children


@checked
@dataclass
class OpenAPIData:
    versions: Dict[str, List[str]]


class OpenAPIHandler(Handler):
    """Constructs metadata for OpenAPI content pages."""

    @dataclass
    class SourceData:
        source_type: str
        source: str
        api_version: Optional[str]
        resource_versions: Optional[List[str]]

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.openapi_pages: Dict[str, OpenAPIHandler.SourceData] = {}

    def get_metadata(self) -> Dict[str, SerializableType]:
        """Returns serialized object to be used as part of the build's metadata."""

        return {k: asdict(v) for k, v in self.openapi_pages.items()}

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if (
            not isinstance(node, n.Directive)
            or node.name != "openapi"
            or node.options.get("preview")
        ):
            return

        current_file = fileid_stack.current
        current_slug = clean_slug(current_file.without_known_suffix)

        if current_slug in self.openapi_pages:
            self.context.diagnostics[current_file].append(
                DuplicateDirective(node.name, node.start[0])
            )
            return

        # source_type should be assigned in the parsing layer
        source_type = node.options.get("source_type")
        if not source_type:
            return

        source = ""
        argument = node.argument[0]
        # The parser determines the source_type based on the given argument and its
        # node structure. We echo that logic here to grab the source without needing
        # to worry about the argument's node structure.
        # The source_type cannot be manually set in rST as long as the option is not exposed
        # in the rstspec.
        if source_type == "local" or source_type == "atlas":
            assert isinstance(argument, n.Text)
            source = argument.get_text()
        else:
            assert isinstance(argument, n.Reference)
            source = argument.refuri

        api_version = node.options.get("api-version", None)
        resource_versions: Optional[List[str]] = None

        # Fetch OpenAPI versioning data if options are present
        if api_version and source == "cloud":
            # Fetch latest git_hash for S3 versioning data
            try:
                # TODO: Move urls to snooty-toml configurable constants
                git_hash_url = "https://cloud.mongodb.com/version"
                git_hash_response = util.HTTPCache.singleton().get(git_hash_url)
                git_hash = str(git_hash_response, "utf-8")

                version_url = f"https://mongodb-mms-prod-build-server.s3.amazonaws.com/openapi/{git_hash}-api-versions.json"
                version_response = util.HTTPCache.singleton().get(version_url)
                decoded = str(version_response, "utf-8")
                data = check_type(OpenAPIData, yaml.safe_load(decoded))
            except Exception as err:
                self.context.diagnostics[fileid_stack.current].append(
                    FetchError(
                        f"Fetching OpenAPI version errored: {err}", node.start[0]
                    )
                )
                return

            # Malformed Version data
            if "major" not in data.versions:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidOpenApiResponse(node.start[0])
                )
                return

            version_data = data.versions
            major_versions = version_data.get("major", [])
            resource_versions = version_data.get(api_version, [])

            # Version not present in version data
            if api_version not in major_versions:
                # Allows error-free diagnostic report
                if not (
                    isinstance(major_versions, list)
                    and all(isinstance(mv, str) for mv in major_versions)
                ):
                    major_versions = []
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidVersion(
                        node.name, api_version, major_versions, node.start[0]
                    )
                )
                return

        else:
            api_version = None

        self.openapi_pages[current_slug] = self.SourceData(
            source_type, source, api_version, resource_versions
        )


class OpenAPIChangelogHandler(Handler):
    """Constructs metadata for OpenAPI content pages."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.has_changelog_directive = False

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.has_changelog_directive = False

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "openapi-changelog":
            return

        if isinstance(node, n.Directive) and node.name == "openapi-changelog":
            if self.has_changelog_directive:
                self.context.diagnostics[fileid_stack.current].append(
                    DuplicateDirective(node.name, node.start[0])
                )
                return
            self.has_changelog_directive = True
            return


class InstruqtHandler(Handler):
    """Identify if Instruqt directive is present on a page and add title as a page-level option if so"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.has_instruqt_drawer = False

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.has_instruqt_drawer = False

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.has_instruqt_drawer:
            return

        page.ast.options["instruqt"] = self.has_instruqt_drawer

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "instruqt":
            return

        elif self.has_instruqt_drawer:
            self.context.diagnostics[fileid_stack.current].append(
                DuplicateDirective(node.name, node.start[0])
            )
            return

        elif node.options.get("drawer"):
            self.has_instruqt_drawer = True
            return

        self.has_instruqt_drawer = False


class IAHandler(Handler):
    """Identify IA directive on a page and save a list of its entries as a page-level option."""

    class IAData(NamedTuple):
        title: Sequence[n.InlineNode]
        url: Optional[str]
        slug: Optional[str]
        project_name: Optional[str]
        primary: Optional[bool]
        entry_id: Optional[str]

        def serialize(
            self, entry_ids: Dict[str, List[Dict[str, str]]]
        ) -> n.SerializedNode:
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
            if self.entry_id is not None:
                result["id"] = self.entry_id
                if self.entry_id in entry_ids:
                    result["linked_data"] = entry_ids[self.entry_id]

            return result

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.ia: List[IAHandler.IAData] = []
        self.entry_ids: Dict[str, List[Dict[str, str]]] = {}

    def add_linked_data(
        self, card_group: n.Directive, entry_id: str, current_file: FileId
    ) -> None:
        for card in card_group.get_child_of_type(n.Directive):
            if card.name != "card":
                self.context.diagnostics[current_file].append(
                    InvalidChild(card.name, "card_group", "card", card.span[0])
                )
                continue

            # The following options are the most important for ensuring working
            # links on the side nav, but we can extend this to all options if needed
            headline = card.options.get("headline", "")
            url = card.options.get("url", "")
            if not headline or not url:
                self.context.diagnostics[current_file].append(
                    InvalidIALinkedData(
                        "Missing headline and/or url for card", card.span[0]
                    )
                )
                continue

            self.entry_ids[entry_id].append(card.options)

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if (
            not isinstance(node, n.Directive)
            or not node.name in {"ia", "card-group"}
            or not node.domain in {"", "mongodb"}
        ):
            return

        # A card-group directive can have data linked to a particular IA entry
        # for the side nav
        if node.name == "card-group":
            entry_id = node.options.get("ia-entry-id")
            if not entry_id:
                return
            elif entry_id in self.entry_ids:
                self.add_linked_data(node, entry_id, fileid_stack.current)
            else:
                self.context.diagnostics[fileid_stack.current].append(
                    InvalidIALinkedData(
                        f'No IA entry with ID "{entry_id}" found', node.span[0]
                    )
                )
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

            entry_id = entry.options.get("id")
            self.ia.append(
                IAHandler.IAData(
                    title,
                    url,
                    slug,
                    project_name,
                    bool(entry.options.get("primary", False)) if project_name else None,
                    entry_id,
                )
            )

            if entry_id:
                self.entry_ids[entry_id] = []

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.ia = []

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.ia:
            return

        if isinstance(page.ast, n.Root):
            page.ast.options["ia"] = [
                entry.serialize(self.entry_ids) for entry in self.ia
            ]


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
        if not substitution:
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

        # If we're injecting inline nodes, wrap them in a paragraph. Coalesce adjacent
        # inline elements into a single paragraph.
        output: List[n.Node] = []
        current_paragraph: List[n.InlineNode] = []
        for element in result:
            if isinstance(element, n.InlineNode):
                current_paragraph.append(element)
            else:
                if current_paragraph:
                    output.append(n.Paragraph(node.span, current_paragraph))  # type: ignore
                    current_paragraph = []
                output.append(element)

        if current_paragraph:
            output.append(n.Paragraph(node.span, current_paragraph))  # type: ignore

        return output

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
        if not isinstance(node, (n.Target, n.Section, n.TargetIdentifier)) and not (
            isinstance(node, n.Directive) and "heading" in node.options
        ):
            self.pending_targets = []

        if isinstance(node, n.Target) and node.domain == "std" and node.name == "label":
            self.pending_targets.extend(node.children)
        elif isinstance(node, n.Section) or (
            isinstance(node, n.Directive) and "heading" in node.options
        ):
            for target in self.pending_targets:
                if isinstance(node, n.Section):
                    heading = next(node.get_child_of_type(n.Heading), None)
                elif isinstance(node, n.Directive) and "heading" in node.options:
                    heading_option = node.options.get("heading")
                    if heading_option:
                        heading = n.Heading(
                            (node.span[0],),
                            [n.Text((node.span[0],), heading_option)],
                            util.make_html5_id(heading_option.strip()).lower(),
                        )
                if heading is not None:
                    assert isinstance(target, n.Parent)
                    target.children = heading.children
            self.pending_targets = []


class FootnoteHandler(Handler):
    """
    Handles normalizing footnotes and their references to make sure footnotes spread across include files are not repeated
    across a single page.
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        # Footnote reference ids from tinydocutils starts at 1
        self.id_counter = 1

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.id_counter = 1

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.FootnoteReference):
            return

        node.id = f"id{self.id_counter}"
        self.id_counter += 1


class RefsHandler(Handler):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.project_config = context[ProjectConfig]
        self.targets = context[TargetDatabase]
        self.spec = specparser.Spec.get(self.project_config.config_path)

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
            target_dict = self.spec.rstobject
            target_key = f"{node.domain}:{node.name}"
            title = node.target
            # abstract title from node's target to insert into new text node
            if target_key in target_dict and target_dict[target_key].prefix:
                title = title.replace(f"{target_dict[target_key].prefix}.", "")
            text_node = n.Text((line,), title)
            injection_candidate = get_title_injection_candidate(node)

            if injection_candidate is not None:
                injection_candidate.children = [text_node]

            # See if there are any near matches
            suggestions = self.targets.get_suggestions(key)

            self.context.diagnostics[fileid_stack.current].append(
                TargetNotFound(node.name, node.target, suggestions, line)
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

            if not node.children:
                line = node.span[0]
                self.context.diagnostics[fileid_stack.current].append(
                    ChildlessRef(node.target, line)
                )

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


class FacetsHandler(Handler):
    """Builds page.facets depending on facets found on nodes on this page"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)

        self.facets: List[Facet] = []
        self.parent_stack: List[Tuple[Facet, int]] = []
        self.removal_nodes: List[n.Node] = []

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "facet":
            return

        def get_children_total(
            child: n.Node,
        ) -> int:
            return (
                len(child.options["values"].split(","))
                if hasattr(child, "options")
                else 0
            )

        facet_values = node.options["values"]
        parent = None
        parent_facets = []
        if self.parent_stack:
            parent = self.parent_stack[-1][0]
            parent_facets = list(map(lambda tuple: tuple[0], self.parent_stack))

        for facet_value in facet_values.split(","):
            unparsed_facet = {
                "value": facet_value.strip(),
                "category": node.options["name"],
            }
            facet_display_name = ProjectConfig.get_facet_display_name(
                parent_facets, unparsed_facet
            )
            facet_node = Facet(
                category=unparsed_facet["category"],
                value=unparsed_facet["value"],
                display_name=facet_display_name,
            )

            if not parent:
                self.facets.append(facet_node)
            if parent and parent.sub_facets is not None:
                parent.sub_facets.append(facet_node)

            if node.children:
                facet_node.sub_facets = []
                num_children = sum(
                    list(
                        map(
                            get_children_total,
                            node.children,
                        )
                    )
                )
                self.parent_stack.append((facet_node, num_children))

        self.removal_nodes.append(node)

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "facet":
            return

        if self.parent_stack:
            parent, num_children = self.parent_stack[-1]

            if parent.sub_facets is not None and len(parent.sub_facets) == num_children:
                self.parent_stack.pop()

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.facets = []
        self.target = self.facets

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        curr_facets: List[Facet] = page.facets or []
        page.facets = ProjectConfig.merge_facets(curr_facets, self.facets)
        for facet_node in self.removal_nodes:
            try:
                page.ast.children.remove(facet_node)
            except ValueError:
                pass


class ImageHandler(Handler):
    """Inspects the images on the page and appends a lazy loading option if the image is considered to be below the fold.

    An image is considered below the fold if section index > 1 or index of image on page > 2
    """

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.current_section = 0
        self.current_img_index = 0
        self.min_section_depth = 1
        self.min_img_index = 2

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.current_section = 0
        self.current_img_index = 0

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.Section):
            self.current_section += 1
            return

        if isinstance(node, n.Directive) and (
            node.name == "image" or node.name == "figure"
        ):
            if (
                self.current_section > self.min_section_depth
                or self.current_img_index > self.min_img_index
            ):
                node.options["loading"] = "lazy"
            self.current_img_index += 1


class CollapsibleHandler(Handler):
    """Handles nested collapsible directives on a single page.
    If a page has multiple collapsibles, raise a diagnostic"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.collapsible_detected = False

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "collapsible":
            return
        if self.collapsible_detected:
            self.context.diagnostics[fileid_stack.current].append(
                NestedDirective("collapsible", node.span[0])
            )
        self.collapsible_detected = True

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if isinstance(node, n.Directive) and node.name == "collapsible":
            self.collapsible_detected = False


class DismissibleSkillsCardHandler(Handler):
    """Handles 'dismissible-skills-card' directives on a page.
    Only one is allowed per page. Adds the data to page AST options."""

    @dataclass
    class DismissibleSkillsCard:
        skill: str
        url: str

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.dismissible_skills_card: Optional[
            DismissibleSkillsCardHandler.DismissibleSkillsCard
        ] = None

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.dismissible_skills_card = None

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != "dismissible-skills-card":
            return
        if self.dismissible_skills_card:
            self.context.diagnostics[fileid_stack.current].append(
                DuplicateDirective(node.name, node.span[0])
            )

        skill = node.options.get("skill")
        url = node.options.get("url")
        if skill and url:
            self.dismissible_skills_card = self.DismissibleSkillsCard(
                skill=skill, url=url
            )

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if self.dismissible_skills_card:
            page.ast.options["dismissible_skills_card"] = {
                "skill": self.dismissible_skills_card.skill,
                "url": self.dismissible_skills_card.url,
            }


class NestedDirectiveHandler(Handler):
    """Prevents a directive from being nested deeper than intended on a page and from being used twice in a single page."""

    def __init__(
        self, context: Context, directive_name: str, skippable_directives: Set[str]
    ):
        super().__init__(context)
        self.directive_name = directive_name
        self.skippable_directives = skippable_directives
        self.directive_detected = False
        self.nesting_level = 0

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.nesting_level = 0
        self.directive_detected = False

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name in self.skippable_directives:
            return

        # Track if node is nested deeper than intended
        if node.name != self.directive_name:
            self.nesting_level += 1
            return

        line_start = node.span[0]

        if self.directive_detected:
            self.context.diagnostics[fileid_stack.current].append(
                DuplicateDirective(node.name, line_start)
            )
            return

        if self.nesting_level > 0:
            self.context.diagnostics[fileid_stack.current].append(
                NestedDirective(node.name, line_start)
            )
            return

        self.directive_detected = True

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name in self.skippable_directives:
            return
        if node.name != self.directive_name:
            self.nesting_level -= 1


class WayfindingHandler(NestedDirectiveHandler):
    """Handles page-level validations for wayfinding directive and its children."""

    def __init__(self, context: Context) -> None:
        super().__init__(context, "wayfinding", {"include", "sharedinclude"})


class MethodSelectorHandler(Handler):
    """Handles page-level validations for method-selector directive and its children."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.method_option_name = "method-option"
        self.method_description_name = "method-description"
        self.within_description = False
        self.current_method_option: Optional[str] = None
        self.pending_diagnostics: List[Diagnostic] = []
        self.page_has_method_selector = False

    def __add_pending_diagnostics(self, fileid: FileId) -> None:
        self.context.diagnostics[fileid].extend(self.pending_diagnostics)

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.page_has_method_selector = False

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive):
            return

        if node.name == "tabs-selector" and (
            self.current_method_option != "driver" and not self.within_description
        ):
            self.pending_diagnostics.append(
                UnexpectedDirectiveOrder(
                    'tabs-selector can only be used in the method-description of the "driver" option when page has method-selector.',
                    node.start[0],
                )
            )
            return

        option_id = node.options.get("id", "")
        if node.name == "method-selector":
            if self.page_has_method_selector:
                self.context.diagnostics[fileid_stack.current].append(
                    DuplicateDirective(node.name, node.span[0])
                )
                return
            self.page_has_method_selector = True
        elif node.name == self.method_option_name and option_id:
            self.current_method_option = option_id
        elif node.name == self.method_description_name:
            self.within_description = True

    def exit_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not (isinstance(node, n.Directive)):
            return

        if node.name == self.method_option_name:
            self.current_method_option = None
        elif node.name == self.method_description_name:
            self.within_description = False

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if self.page_has_method_selector:
            page.ast.options["has_method_selector"] = True
            self.__add_pending_diagnostics(fileid_stack.current)
        self.pending_diagnostics = []


class MultiPageTutorialHandler(Handler):
    """Handles page-wide settings for a multi-page tutorial page."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.target_directive_name = "multi-page-tutorial"
        self.found_directive: Optional[n.Directive] = None
        self.pending_node_removals: List[n.Directive] = []

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.found_directive = None
        self.pending_node_removals = []

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.Directive) or node.name != self.target_directive_name:
            return

        self.pending_node_removals.append(node)

        if self.found_directive:
            DuplicateDirective(self.target_directive_name, node.start[0])
            return

        self.found_directive = node

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.found_directive:
            return

        page.ast.options["multi_page_tutorial_settings"] = {
            "time_required": self.found_directive.options.get("time-required", 0),
            "show_next_top": self.found_directive.options.get("show-next-top", False),
        }

        # Remove AST(s) to avoid unnecessary duplicate data
        for node in self.pending_node_removals:
            page.ast.children.remove(node)


class ComposableTutorialHandler(Handler):
    """Handles composable tutorial directivepresence in page.
    Should not be simultaneously present on page with other directives"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.target_directive_name = "composable-tutorial"
        self.composable_tutorial = False
        self.colliding_ast_options = (
            ("selectors", "tabs-selectors"),
            ("has_method_selector", "method-selector"),
        )
        self.composable_node_start = 0

    def enter_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        self.composable_tutorial = False

    def enter_node(self, fileid_stack: FileIdStack, node: n.Node) -> None:
        if not isinstance(node, n.ComposableDirective):
            return

        if self.composable_tutorial:
            self.context.diagnostics[fileid_stack.current].append(
                DuplicateDirective(self.target_directive_name, (node.start[0]))
            )
            return

        self.composable_tutorial = True
        self.composable_node_start = node.start[0]

    def exit_page(self, fileid_stack: FileIdStack, page: Page) -> None:
        if not self.composable_tutorial:
            return
        for colliding_tuple in self.colliding_ast_options:
            colliding_ast_option = colliding_tuple[0]
            if page.ast.options.get(colliding_ast_option, None):
                self.context.diagnostics[fileid_stack.current].append(
                    UnexpectedDirectiveOrder(
                        f"{self.target_directive_name} cannot be used with {colliding_tuple[1]} on the same page",
                        self.composable_node_start,
                    )
                )
        page.ast.options["has_composable_tutorial"] = True


class PostprocessorResult(NamedTuple):
    pages: Dict[FileId, Page]
    metadata: Dict[str, SerializableType]
    diagnostics: Dict[FileId, List[Diagnostic]]
    targets: TargetDatabase


def build_manpages(context: Context) -> Dict[str, Union[str, bytes]]:
    config = context[ProjectConfig]
    result: Dict[str, Union[str, bytes]] = {}

    # Build manpages
    manpages: List[Tuple[str, str]] = []
    for name, definition in config.manpages.items():
        fileid = FileId(definition.file)
        manpage_page = context.pages.get(fileid)
        if not manpage_page:
            context.diagnostics[
                FileId(config.config_path.relative_to(config.root))
            ].append(CannotOpenFile(PurePath(fileid), "Page not found", 0))
            continue

        for filename, rendered in man.render(
            manpage_page, name, definition.title, definition.section
        ).items():
            manpages.append((filename.as_posix(), rendered))
            result[filename.as_posix()] = rendered

    if manpages and config.bundle.manpages:
        try:
            result[config.bundle.manpages] = bundle(
                PurePath(config.bundle.manpages), manpages
            )
        except ValueError:
            context.diagnostics[
                FileId(config.config_path.relative_to(config.root))
            ].append(UnsupportedFormat(config.bundle.manpages, (".tar", ".tar.gz"), 0))

    return result


class Postprocessor:
    """Handles all postprocessing operations on parsed AST files.

    The only method that should be called on an instance of Postprocessor is run(). This method
    handles calling all other methods and ensures that parse operations are run in the correct order.
    """

    PASSES: Sequence[Sequence[Type[Handler]]] = [
        [IncludeHandler],
        [SubstitutionHandler],
        [
            HeadingHandler,
            TocTitleHandler,
            AddTitlesToLabelTargetsHandler,
            FootnoteHandler,
            ProgramOptionHandler,
            TabsSelectorHandler,
            ContentsHandler,
            InstruqtHandler,
            BannerHandler,
            GuidesHandler,
            OpenAPIHandler,
            OpenAPIChangelogHandler,
            FacetsHandler,
            ImageHandler,
            CollapsibleHandler,
            WayfindingHandler,
            DismissibleSkillsCardHandler,
            MethodSelectorHandler,
            MultiPageTutorialHandler,
            ComposableTutorialHandler,
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
        self, pages: Dict[FileId, Page], cancellation_token: threading.Event
    ) -> PostprocessorResult:
        """Run all postprocessing operations and return a dictionary containing the metadata document to be saved."""
        if not pages:
            return PostprocessorResult({}, {}, {}, self.targets)

        self.pages = pages
        self.cancellation_token = cancellation_token
        context = Context(pages)
        context.add(self.project_config)
        context.add(self.targets)

        propagate_facets(self.pages, context)

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
        return PostprocessorResult(
            self.pages, document, context.diagnostics, self.targets
        )

    def finalize(self, context: Context, metadata: n.SerializedNode) -> None:
        pass

    @classmethod
    def generate_metadata(cls, context: Context) -> n.SerializedNode:
        project_config = context[ProjectConfig]
        document: Dict[str, SerializableType] = {}
        document["title"] = project_config.title
        document["eol"] = project_config.eol if project_config.eol else False
        document["canonical"] = (
            project_config.canonical if project_config.canonical else None
        )
        if project_config.deprecated_versions:
            document["deprecated_versions"] = project_config.deprecated_versions
        if project_config.associated_products:
            document["associated_products"] = [
                product.serialize() for product in project_config.associated_products
            ]
        # Update metadata document with key-value pairs defined in event parser
        document["slugToTitle"] = {
            k: [node.serialize() for node in v]
            for k, v in context[HeadingHandler].slug_title_mapping.items()
        }
        document["slugToBreadcrumbLabel"] = {
            k: (
                context[TocTitleHandler].get_title(f"/{k}")
                if f"/{k}" in context[TocTitleHandler].slug_title_mapping
                else "".join(node.get_text() for node in v)
            )
            for k, v in context[HeadingHandler].slug_title_mapping.items()
        }
        multi_pages_tutorials = context[ProjectConfig].multi_page_tutorials
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
                "multiPageTutorials": cls.generate_multi_page_tutorials(
                    tree, multi_pages_tutorials
                ),
            }
        )

        if iatree:
            document["iatree"] = iatree

        context[GuidesHandler].add_guides_metadata(document)

        openapi_pages_metadata = context[OpenAPIHandler].get_metadata()
        if len(openapi_pages_metadata) > 0:
            document["openapi_pages"] = openapi_pages_metadata

        manpages = build_manpages(context)
        document["static_files"] = manpages

        return document

    def run_event_parser(
        self,
        node_listeners: Iterable[Tuple[str, Callable[[FileIdStack, n.Node], None]]],
        page_listeners: Iterable[Tuple[str, Callable[[FileIdStack, Page], None]]] = (),
    ) -> None:
        event_parser = EventParser(self.cancellation_token)
        for event, node_listener in node_listeners:
            event_parser.add_event_listener(event, node_listener)

        for event, page_listener in page_listeners:
            event_parser.add_event_listener(event, page_listener)

        event_parser.consume(
            (k, v) for k, v in self.pages.items() if k.suffix == EXT_FOR_PAGE
        )

    @staticmethod
    def build_iatree(context: Context) -> Dict[str, SerializableType]:
        def _get_page_from_slug(current_page: Page, slug: str) -> Optional[Page]:
            relative, _ = util.reroot_path(
                FileId(slug),
                current_page.fileid,
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
        associated_project_names: Set[str] = set(
            [project.name for project in context[ProjectConfig].associated_products]
        )
        ref_project_set: Set[Tuple[Optional[str], Optional[str]]] = set()
        visited_fileids: Set[FileId] = {starting_fileid}
        cls.find_toctree_nodes(
            context,
            starting_fileid,
            ast,
            root,
            toc_landing_pages,
            associated_project_names,
            ref_project_set,
            visited_fileids,
        )

        # Locate orphaned files
        for fileid in context.pages:
            if fileid.suffix != EXT_FOR_PAGE:
                continue

            if fileid not in visited_fileids:
                if "orphan" not in context.pages[fileid].ast.options:
                    context.diagnostics[fileid].append(OrphanedPage())

        return root

    @classmethod
    def find_toctree_nodes(
        cls,
        context: Context,
        fileid: FileId,
        ast: n.Node,
        node: Dict[str, Any],
        toc_landing_pages: List[str],
        associated_project_names: Set[str],
        external_nodes: Set[Tuple[Optional[str], Optional[str]]],
        visited_file_ids: Set[FileId],
    ) -> None:
        """Iterate over AST to find toctree directives and construct their nodes for the unified toctree"""

        # Base case: stop iterating over AST
        if not isinstance(ast, n.Parent):
            return

        if isinstance(ast, n.TocTreeDirective):
            # Recursively build the tree for each toctree node in this entries list
            for entry in ast.entries:
                toctree_node: Dict[str, object] = {}
                if entry.ref_project:
                    toctree_node = {
                        "title": (
                            [n.Text((0,), entry.title).serialize()]
                            if entry.title
                            else None
                        ),
                        "options": {"project": entry.ref_project},
                        "children": [],
                        "slug": entry.ref_project,
                    }
                    ref_project_pair = (entry.title, entry.ref_project)
                    if ref_project_pair in external_nodes:
                        context.diagnostics[fileid].append(
                            DuplicatedExternalToc(entry.ref_project, ast.span[0])
                        )
                    external_nodes.add(ref_project_pair)
                if entry.url:
                    toctree_node = {
                        "title": (
                            [n.Text((0,), entry.title).serialize()]
                            if entry.title
                            else None
                        ),
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

                    toctree_node_options: Dict[str, Any] = {
                        "drawer": slug not in toc_landing_pages
                    }

                    # Ensure Osiris-built TOC parent nodes are functional
                    if ast.options:
                        if ast.options.get("osiris_parent"):
                            toctree_node_options = {"drawer": False}

                    # Check if the cleaned slug corresponds to an associated project name, indicating an external node
                    if slug in associated_project_names:
                        toctree_node_options["project"] = slug
                        ref_project_pair = (entry.title, slug)
                        if ref_project_pair in external_nodes:
                            context.diagnostics[fileid].append(
                                DuplicatedExternalToc(slug, ast.span[0])
                            )
                        external_nodes.add(ref_project_pair)

                    # Check if tocicon is a page level option
                    if context.pages[FileId(slug_fileid)].ast.options:
                        if "tocicon" in context.pages[FileId(slug_fileid)].ast.options:
                            toctree_node_options["tocicon"] = context.pages[
                                FileId(slug_fileid)
                            ].ast.options["tocicon"]

                    toctree_node = {
                        "title": title,
                        "slug": "/" if slug == "index" else slug,
                        "children": [],
                        "options": toctree_node_options,
                    }

                    # Don't recurse on the index page
                    if slug_fileid not in visited_file_ids:
                        visited_file_ids.add(slug_fileid)
                        new_ast = context.pages[slug_fileid].ast
                        cls.find_toctree_nodes(
                            context,
                            slug_fileid,
                            new_ast,
                            toctree_node,
                            toc_landing_pages,
                            associated_project_names,
                            external_nodes,
                            visited_file_ids,
                        )

                if toctree_node:
                    node["children"].append(toctree_node)

        # Locate the correct directive object containing the toctree within this AST
        for child_ast in ast.children:
            cls.find_toctree_nodes(
                context,
                fileid,
                child_ast,
                node,
                toc_landing_pages,
                associated_project_names,
                external_nodes,
                visited_file_ids,
            )

    @staticmethod
    def generate_multi_page_tutorials(
        tree: Dict[str, SerializableType], multi_page_tutorials: List[str]
    ) -> Dict[str, n.SerializedNode]:
        """Generate steps for multi page tutorials for each parent listed in the multi_page_tutorials array"""
        result: Dict[str, n.SerializedNode] = {}

        if not multi_page_tutorials:
            return result

        if "children" in tree and isinstance(tree["children"], List):
            for node in tree["children"]:
                find_multi_page_tutorial_children(node, multi_page_tutorials, result)

        return result

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


def find_multi_page_tutorial_children(
    node: Dict[str, SerializableType],
    multi_page_tutorials: List[str],
    result: Dict[str, n.SerializedNode],
) -> None:
    slug = node.get("slug", "")
    if not (slug and isinstance(slug, str)):
        return

    children = node.get("children", [])
    if not (children and isinstance(children, List)):
        return

    formatted_slug = f"/{slug}"
    if formatted_slug in multi_page_tutorials:
        result[slug] = {
            "total_steps": len(children),
            "slugs": [child["slug"] for child in children],
        }

    for child in children:
        find_multi_page_tutorial_children(child, multi_page_tutorials, result)


def clean_slug(slug: str) -> str:
    """Strip file extension and leading/trailing slashes (/) from string"""
    slug = slug.strip("/")

    # TODO: remove file extensions in initial parse layer
    # https://jira.mongodb.org/browse/DOCSP-7595
    root, ext = os.path.splitext(slug)
    if ext in SOURCE_FILE_EXTENSIONS or ext == ".ast":
        return root

    return slug

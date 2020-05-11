import os.path
import logging
from collections import defaultdict
from copy import deepcopy
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Iterable,
    Sequence,
    MutableSequence,
)
from .eventparser import EventParser
from .types import FileId, Page, ProjectConfig, SerializableType, TargetDatabase
from .diagnostics import (
    Diagnostic,
    MissingOption,
    TargetNotFound,
    AmbiguousTarget,
    SubstitutionRefError,
    ExpectedPathArg,
    UnnamedPage,
    InvalidLiteralInclude,
    CannotOpenFile,
)
from . import n, util
from .util import SOURCE_FILE_EXTENSIONS

logger = logging.getLogger(__name__)


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


class ProgramOptionHandler:
    """Handle the program & option rstobjects, using the last program target
       to populate option targets."""

    def __init__(self, diagnostics: Dict[FileId, List[Diagnostic]]) -> None:
        self.pending_program: Optional[n.Target] = None
        self.diagnostics = diagnostics

    def __call__(self, filename: FileId, node: n.Node) -> None:
        if not isinstance(node, n.Target):
            return

        identifier = f"{node.domain}:{node.name}"
        if identifier == "std:program":
            self.pending_program = node
        elif identifier == "std:option":
            if not self.pending_program:
                line = node.start[0]
                self.diagnostics[filename].append(MissingOption(line))
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


class Postprocessor:
    """Handles all postprocessing operations on parsed AST files.

    The only method that should be called on an instance of Postprocessor is run(). This method
    handles calling all other methods and ensures that parse operations are run in the correct order."""

    def __init__(self, project_config: ProjectConfig, targets: TargetDatabase) -> None:
        self.project_config = project_config
        self.slug_title_mapping: Dict[str, Sequence[n.InlineNode]] = {}
        self.toctree: Dict[str, SerializableType] = {}
        self.pages: Dict[FileId, Page] = {}
        self.pending_targets: List[n.Node] = []
        self.targets = targets
        self.substitution_definitions: Dict[str, MutableSequence[n.InlineNode]] = {}
        self.unreplaced_nodes: List[Tuple[n.SubstitutionReference, int]] = []
        self.seen_definitions: Optional[Set[str]] = None
        self.toc_landing_pages = [
            clean_slug(slug) for slug in project_config.toc_landing_pages
        ]
        self.pending_program: Optional[SerializableType] = None

    def run(
        self, pages: Dict[FileId, Page]
    ) -> Tuple[Dict[str, SerializableType], Dict[FileId, List[Diagnostic]]]:
        """Run all postprocessing operations and return a dictionary containing the metadata document to be saved."""
        if not pages:
            return {}, {}

        self.pages = pages
        self.build_slug_fileid_mapping()
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)

        self.run_event_parser(
            [(EventParser.OBJECT_START_EVENT, self.populate_include_nodes)]
        )

        self.handle_substitutions()

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.build_slug_title_mapping),
                (EventParser.OBJECT_START_EVENT, self.add_titles_to_label_targets),
                (
                    EventParser.OBJECT_START_EVENT,
                    ProgramOptionHandler(self.diagnostics),
                ),
            ],
            [(EventParser.PAGE_START_EVENT, self.reset_program)],
        )

        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_target)])
        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_refs)])
        document = self.generate_metadata()

        return document, self.diagnostics

    def generate_metadata(self) -> n.SerializedNode:
        document: Dict[str, SerializableType] = {}
        document["title"] = self.project_config.title
        if self.project_config.deprecated_versions:
            document["deprecated_versions"] = self.project_config.deprecated_versions
        # Update metadata document with key-value pairs defined in event parser
        document["slugToTitle"] = {
            k: [node.serialize() for node in v]
            for k, v in self.slug_title_mapping.items()
        }
        # Run postprocessing operations related to toctree and append to metadata document
        document.update(
            {
                "toctree": self.build_toctree(),
                "toctreeOrder": self.toctree_order(),
                "parentPaths": self.breadcrumbs(),
            }
        )
        return document

    def run_event_parser(
        self,
        node_listeners: Iterable[Tuple[str, Callable[[FileId, n.Node], None]]],
        page_listeners: Iterable[Tuple[str, Callable[[FileId, Page], None]]] = (),
    ) -> None:
        event_parser = EventParser()
        for event, node_listener in node_listeners:
            event_parser.add_event_listener(event, node_listener)

        for event, page_listener in page_listeners:
            event_parser.add_event_listener(event, page_listener)

        event_parser.consume(
            (k, v) for k, v in self.pages.items() if k.suffix == ".txt"
        )

    def reset_program(self, filename: FileId, page: Page) -> None:
        self.pending_program = None

    def _attach_doc_title(self, filename: FileId, node: n.RefRole) -> None:
        if not isinstance(node.fileid, str):
            line = node.span[0]
            self.diagnostics[filename].append(ExpectedPathArg(node.name, line))
            return

        relative, _ = util.reroot_path(
            FileId(node.fileid), filename, self.project_config.source_path
        )
        slug = clean_slug(relative.as_posix())
        title = self.slug_title_mapping.get(slug)

        if not title:
            line = node.span[0]
            self.diagnostics[filename].append(UnnamedPage(node.fileid, line))
            return

        node.children = [deepcopy(node) for node in title]

    def handle_refs(self, filename: FileId, node: n.Node) -> None:
        """When a node of type ref_role is encountered, ensure that it references a valid target.

        If so, append the full URL to the AST node. If not, throw an error.
        """
        if not isinstance(node, n.RefRole):
            return
        key = f"{node.domain}:{node.name}"

        if key == "std:doc":
            if not node.children:
                # If title is not explicitly given, search slug-title mapping for the page's title
                self._attach_doc_title(filename, node)
            return

        key += f":{node.target}"

        # Add title and link target to AST
        target_candidates = self.targets[key]
        if not target_candidates:
            line = node.span[0]
            self.diagnostics[filename].append(
                TargetNotFound(node.name, node.target, line)
            )
            return

        if len(target_candidates) > 1:
            line = node.span[0]
            self.diagnostics[filename].append(
                AmbiguousTarget(node.name, node.target, line)
            )

        # Choose the most recently-defined target candidate if it is ambiguous
        target_type, target, canonical_target_name, title_nodes = target_candidates[-1]
        node.target = canonical_target_name
        setattr(node, target_type.name, target)
        injection_candidate = get_title_injection_candidate(node)
        # If there is no explicit title given, use the target's title
        if injection_candidate is not None:
            cloned_title_nodes: MutableSequence[n.Node] = list(
                deepcopy(node) for node in title_nodes
            )
            for title_node in cloned_title_nodes:
                deep_copy_position(node, title_node)
            injection_candidate.children = cloned_title_nodes

    def handle_substitutions(self) -> None:
        """Find and replace substitutions throughout project"""
        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.replace_substitutions),
                (EventParser.OBJECT_END_EVENT, self.reset_seen_definitions),
            ],
            [(EventParser.PAGE_END_EVENT, self.finalize_substitutions)],
        )

    def replace_substitutions(self, filename: FileId, node: n.Node) -> None:
        """When a substitution is defined, add it to the page's index.

        When a substitution is referenced, populate its children if possible.
        If not, save this node to be populated at the end of the page.
        """

        try:
            line = node.span[0]
            if isinstance(node, n.SubstitutionDefinition):
                self.substitution_definitions[node.name] = node.children
                self.seen_definitions = set()
            elif isinstance(node, n.SubstitutionReference):
                # Get substitution from page. If not found, attempt to source from snooty.toml. Otherwise, save substitution to be populated at the end of page
                substitution = self.substitution_definitions.get(
                    node.name
                ) or self.project_config.substitution_nodes.get(node.name)

                if (
                    self.seen_definitions is not None
                    and node.name in self.seen_definitions
                ):
                    # Catch circular substitution
                    del self.substitution_definitions[node.name]
                    node.children = []
                    self.diagnostics[filename].append(
                        SubstitutionRefError(
                            f'Circular substitution definition referenced: "{node.name}"',
                            line,
                        )
                    )
                elif substitution is not None:
                    node.children = substitution
                else:
                    # Save node in order to populate it at the end of the page
                    self.unreplaced_nodes.append((node, line))

                if self.seen_definitions is not None:
                    self.seen_definitions.add(node.name)
        except KeyError:
            # If node does not contain "name" field, it is a duplicate substitution definition.
            # An error has already been thrown for this on parse, so pass.
            pass

    def finalize_substitutions(self, filename: FileId, page: Page) -> None:
        """Attempt to populate any yet-unresolved substitutions (substitutions defined after usage) .

        Clear definitions and unreplaced nodes for the next page.
        """
        for node, line in self.unreplaced_nodes:
            substitution = self.substitution_definitions.get(node.name)
            if substitution is not None:
                node.children = substitution
            else:
                self.diagnostics[filename].append(
                    SubstitutionRefError(
                        f'Substitution reference could not be replaced: "|{node.name}|"',
                        line,
                    )
                )

        self.substitution_definitions = {}
        self.unreplaced_nodes = []

    def reset_seen_definitions(self, filename: FileId, node: n.Node) -> None:
        if isinstance(node, n.SubstitutionDefinition):
            self.seen_definitions = None

    def add_titles_to_label_targets(self, filename: FileId, node: n.Node) -> None:
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

    def handle_target(self, filename: FileId, node: n.Node) -> None:
        if not isinstance(node, n.Target):
            return

        for target_node in node.get_child_of_type(n.TargetIdentifier):
            if not target_node.children:
                title: List[n.InlineNode] = []
            else:
                title = target_node.children  # type: ignore

            target_ids = target_node.ids
            self.targets.define_local_target(
                node.domain, node.name, target_ids, filename, title
            )

    def populate_include_nodes(self, filename: FileId, node: n.Node) -> None:
        """Iterate over all pages to find include directives. When found, replace their
        `children` property with the contents of the include file.
        Because the include contents are added to the tree on which the event parser is
        running, they will automatically be parsed and have their includes expanded, too.
        Literally-included contents may not be automatically parsed, and are handled below."""

        def get_include_argument(node: n.Directive) -> str:
            """Get filename of include"""
            argument_list = node.argument
            assert len(argument_list) > 0
            return argument_list[0].value

        if not isinstance(node, n.Directive):
            return

        if node.name == "include":
            argument = get_include_argument(node)
            include_slug = clean_slug(argument)
            include_fileid = self.slug_fileid_mapping.get(include_slug)
            # Some `include` FileIds in the mapping include file extensions (.yaml) and others do not
            # This will likely be resolved by DOCSP-7159 https://jira.mongodb.org/browse/DOCSP-7159
            if include_fileid is None:
                return

            include_page = self.pages.get(include_fileid)
            assert include_page is not None
            ast = include_page.ast
            assert isinstance(ast, n.Parent)
            node.children = ast.children

        elif node.name == "literalinclude":
            argument = get_include_argument(node)
            include_slug = clean_slug(argument)
            include_filepath = (
                self.project_config.root / self.project_config.source / include_slug
            )

            # Attempt to read the literally included file
            try:
                with open(include_filepath) as file:
                    text = file.read()

            except OSError as err:
                self.diagnostics[filename].append(
                    CannotOpenFile(include_filepath, err.strerror, node.span + (-1,))
                )
                return

            lines = text.split("\n")

            # Locate the start_after query
            start_after = 0
            if "start-after" in node.options:
                start_after_text = node.options["start-after"]
                assert isinstance(start_after_text, str)
                start_after = next(
                    (idx for idx, line in enumerate(lines) if start_after_text in line),
                    -1,
                )
                if start_after < 0:
                    self.diagnostics[filename].append(
                        InvalidLiteralInclude(
                            f'"{start_after_text}" not found in {include_filepath}',
                            node.span + (-1,),
                        )
                    )
                    return

                # Only increment start_after if text is specified, to avoid capturing the start_after_text
                start_after += 1

            # ...now locate the end_before query
            end_before = len(lines)
            if "end-before" in node.options:
                end_before_text = node.options["end-before"]
                assert isinstance(end_before_text, str)
                end_before = next(
                    (
                        idx
                        for idx, line in enumerate(lines, start=start_after)
                        if end_before_text in line
                    ),
                    -1,
                )
                if end_before < 0:
                    self.diagnostics[filename].append(
                        InvalidLiteralInclude(
                            f'"{end_before_text}" not found in {include_filepath}',
                            node.span + (-1,),
                        )
                    )
                    return
                end_before -= start_after

            # Check that start_after_text precedes end_before_text
            if start_after >= end_before:
                self.diagnostics[filename].append(
                    InvalidLiteralInclude(
                        f'"{end_before_text}" precedes {start_after_text} in {include_filepath}',
                        node.span + (-1,),
                    )
                )
                return

            lines = lines[start_after:end_before]

            if "dedent" in node.options:
                assert isinstance(node.options["dedent"], int)
                lines = [line[node.options["dedent"] :] for line in lines]

            selected_content = "\n".join(lines)

            language = node.options["language"] if "language" in node.options else ""

            code = n.Code((1,), language, True, [], selected_content, True)

            node.children.append(code)

    def build_slug_title_mapping(self, filename: FileId, node: n.Node) -> None:
        """Construct a slug-title mapping of all pages in property"""
        slug = filename.without_known_suffix

        # Save the first heading we encounter to the slug title mapping
        if slug not in self.slug_title_mapping and isinstance(node, n.Heading):
            self.targets.define_local_target(
                "std", "doc", (slug,), filename, node.children
            )
            self.slug_title_mapping[slug] = node.children
            self.targets.define_local_target(
                "std", "doc", (filename.without_known_suffix,), filename, node.children
            )

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
        ast = self.pages[starting_fileid].ast

        self.find_toctree_nodes(starting_fileid, ast, root)

        self.toctree = root
        return root

    def find_toctree_nodes(
        self, fileid: FileId, ast: n.Node, node: Dict[str, Any]
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
                        "title": entry.title,
                        "url": entry.url,
                        "children": [],
                    }
                elif entry.slug:
                    # Recursively build the tree for internal links
                    slug_cleaned = clean_slug(entry.slug)

                    # Ensure that the user-specified slug is an existing page. We want to add this error
                    # handling to the initial parse layer, but this works for now.
                    # https://jira.mongodb.org/browse/DOCSP-7941
                    slug_fileid: FileId = self.slug_fileid_mapping[slug_cleaned]
                    slug: str = slug_fileid.without_known_suffix

                    if entry.title:
                        title: SerializableType = entry.title
                    else:
                        title_nodes = self.slug_title_mapping.get(slug)
                        title = (
                            [node.serialize() for node in title_nodes]
                            if title_nodes
                            else None
                        )

                    toctree_node = {
                        "title": title,
                        "slug": slug,
                        "children": [],
                        "options": {"drawer": slug not in self.toc_landing_pages},
                    }

                    new_ast = self.pages[slug_fileid].ast
                    self.find_toctree_nodes(slug_fileid, new_ast, toctree_node)
                node["children"].append(toctree_node)

        # Locate the correct directive object containing the toctree within this AST
        for child_ast in ast.children:
            self.find_toctree_nodes(fileid, child_ast, node)

    def breadcrumbs(self) -> Dict[str, List[str]]:
        """Generate breadcrumbs for each page represented in the toctree"""
        page_dict: Dict[str, List[str]] = {}
        all_paths: List[Any] = []

        # Find all node to leaf paths for each node in the toctree
        if "children" in self.toctree:
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


class DevhubPostprocessor(Postprocessor):
    """Postprocess operation to be run if a project's default_domain is equal to 'devhub'"""

    # TODO: Identify directives that should be exposed in the rstspec.toml to avoid hardcoding
    # These directives are represented as list nodes; they will return a list of strings
    LIST_FIELDS = {"devhub:products", "devhub:tags", ":languages"}
    # These directives have their content represented as children; they will return a list of nodes
    BLOCK_FIELDS = {"devhub:meta-description"}
    # These directives have their content represented as an argument; they will return a string
    ARG_FIELDS = {"devhub:level", "devhub:type", "devhub:atf-image"}
    # These directives have their content represented as children, along with a series of options;
    # they will return a dictionary with all options represented, and with the content represented as a list of nodes whose key is `children`.
    OPTION_BLOCK_FIELDS = {":og", ":twitter"}

    def run(
        self, pages: Dict[FileId, Page]
    ) -> Tuple[Dict[str, SerializableType], Dict[FileId, List[Diagnostic]]]:
        if not pages:
            return {}, {}

        self.pages = pages
        self.build_slug_fileid_mapping()
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)

        self.run_event_parser(
            [(EventParser.OBJECT_START_EVENT, self.populate_include_nodes)]
        )

        self.handle_substitutions()

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.build_slug_title_mapping),
                (EventParser.OBJECT_START_EVENT, self.add_titles_to_label_targets),
                (
                    EventParser.OBJECT_START_EVENT,
                    ProgramOptionHandler(self.diagnostics),
                ),
            ],
            [(EventParser.PAGE_START_EVENT, self.reset_program)],
        )

        self.run_event_parser([(EventParser.OBJECT_START_EVENT, self.handle_target)])

        def clean_and_validate_page_group_slug(slug: str) -> Optional[str]:
            """Clean a slug and validate that it is a known page. If it is not, return None."""
            cleaned = clean_slug(slug)
            if cleaned not in self.slug_title_mapping:
                # XXX: Because reporting errors in config.toml properly is dodgy right now, just
                # log to stderr.
                logger.error(f"Cannot find slug '{cleaned}'")
                return None

            return cleaned

        self.run_event_parser(
            [
                (EventParser.OBJECT_START_EVENT, self.handle_refs),
                (EventParser.OBJECT_START_EVENT, self.flatten_devhub_article),
            ],
            [
                (EventParser.PAGE_START_EVENT, self.reset_query_fields),
                (EventParser.PAGE_END_EVENT, self.append_query_fields),
            ],
        )

        document = self.generate_metadata()
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

        return document, self.diagnostics

    def reset_query_fields(self, filename: FileId, page: Page) -> None:
        """To be called at the start of each page: reset the query field dictionary"""
        self.query_fields: Dict[str, Any] = {}

    def append_query_fields(self, filename: FileId, page: Page) -> None:
        """To be called at the end of each page: append the query field dictionary to the
        top level of the page's class instance.
        """
        # Save page title to query_fields, if it exists
        slug = clean_slug(filename.as_posix())
        self.query_fields["slug"] = f"/{slug}" if slug != "index" else "/"
        title = self.slug_title_mapping.get(slug)
        if title is not None:
            self.query_fields["title"] = [node.serialize() for node in title]

        page.query_fields = self.query_fields

    def flatten_devhub_article(self, filename: FileId, node: n.Node) -> None:
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

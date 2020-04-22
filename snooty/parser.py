import collections
import dataclasses
import docutils.nodes
import logging
import multiprocessing
import os
import errno
import pwd
import subprocess
import threading
import yaml
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePath
from typing import Any, Dict, MutableSequence, Tuple, Optional, Set, List, Iterable
from typing_extensions import Protocol
import docutils.utils
import watchdog.events
import networkx

from .flutter import check_type, LoadError
from . import n, gizaparser, rstparser, util
from .gizaparser.nodes import GizaCategory
from .gizaparser.published_branches import PublishedBranches
from .postprocess import DevhubPostprocessor, Postprocessor
from .util import RST_EXTENSIONS
from .types import (
    SerializableType,
    Page,
    StaticAsset,
    ProjectConfig,
    PendingTask,
    FileId,
    ProjectInterface,
    Cache,
    TargetDatabase,
    BuildIdentifierSet,
)
from .diagnostics import (
    Diagnostic,
    OptionsNotSupported,
    UnexpectedIndentation,
    ExpectedPathArg,
    ExpectedImageArg,
    ImageSuggested,
    TodoInfo,
    DocUtilsParseError,
    CannotOpenFile,
    InvalidURL,
    InvalidLiteralInclude,
    InvalidTableStructure,
    UnmarshallingError,
    ErrorParsingYAMLFile,
)

# XXX: Work around to get snooty working with Python 3.8 until we can fix
# our implicit data flow issues.
multiprocessing.set_start_method("fork")

NO_CHILDREN = (n.SubstitutionReference,)
logger = logging.getLogger(__name__)


@dataclass
class _DefinitionListTerm(n.InlineParent):
    """A private node used for internal book-keeping that should not be exported to the AST."""

    __slots__ = ()
    type = "definition_list_term"

    def verify(self) -> None:
        assert (
            False
        ), f"{self.__class__.__name__} is private and should have been removed from AST"


class PendingLiteralInclude(PendingTask):
    """Transform a literal-include directive AST node into a code node."""

    def __init__(
        self, node: n.Code, asset: StaticAsset, options: Dict[str, SerializableType]
    ) -> None:
        super().__init__(node)
        self.node: n.Code = node
        self.asset = asset
        self.options = options

    def __call__(
        self, diagnostics: List[Diagnostic], project: ProjectInterface
    ) -> None:
        """Load the literalinclude target text into our node."""
        cache = project.expensive_operation_cache
        # Use the cached node if our parameters match the cache entry
        options_key = hash(tuple(((k, v) for k, v in self.options.items())))
        entry = cache[(self.asset.fileid, options_key)]
        if entry is not None:
            assert isinstance(entry, n.Code)
            dataclasses.replace(self.node, **dataclasses.asdict(entry))
            return

        try:
            text = self.asset.path.read_text(encoding="utf-8")
        except OSError as err:
            diagnostics.append(
                CannotOpenFile(self.asset.path, err.strerror, self.node.start[0])
            )
            return

        # Split the file into lines, and find our start-after query
        lines = text.split("\n")
        start_after = 0
        end_before = len(lines)
        if "start-after" in self.options:
            start_after_text = self.options["start-after"]
            assert isinstance(start_after_text, str)
            start_after = next(
                (idx for idx, line in enumerate(lines) if start_after_text in line), -1
            )
            if start_after < 0:
                diagnostics.append(
                    InvalidLiteralInclude(
                        f'"{start_after_text}" not found in {self.asset.path}',
                        self.node.start[0],
                    )
                )
                return

        # ...now find the end-before query
        if "end-before" in self.options:
            end_before_text = self.options["end-before"]
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
                diagnostics.append(
                    InvalidLiteralInclude(
                        f'"{end_before_text}" not found in {self.asset.path}',
                        self.node.start[0],
                    )
                )
                return
            end_before -= start_after

        # Find the requested lines
        lines = lines[(start_after + 1) : end_before]

        # Deduce a reasonable dedent, if requested.
        if "dedent" in self.options:
            try:
                dedent = min(
                    len(line) - len(line.lstrip())
                    for line in lines
                    if len(line.lstrip()) > 0
                )
            except ValueError:
                # Handle the (unlikely) case where there are no non-empty lines
                dedent = 0
            lines = [line[dedent:] for line in lines]

        if "emphasize_lines" in self.options:
            self.node.emphasize_lines = self.options["emphasize_lines"]  # type: ignore

        self.node.value = "\n".join(lines)

        # Update the cache with this node
        cache[(self.asset.fileid, options_key)] = self.node


class PendingFigure(PendingTask):
    """Add an image's checksum."""

    def __init__(self, node: n.Directive, asset: StaticAsset) -> None:
        super().__init__(node)
        self.node: n.Directive = node
        self.asset = asset

    def __call__(
        self, diagnostics: List[Diagnostic], project: ProjectInterface
    ) -> None:
        """Compute this figure's checksum and store it in our node."""
        cache = project.expensive_operation_cache

        # Use the cached checksum if possible. Note that this does not currently
        # update the underlying asset: if the asset is used by the current backend,
        # the image will still have to be read.
        if self.node.options is None:
            self.node.options = {}
        options = self.node.options
        entry = cache[(self.asset.fileid, 0)]
        if entry is not None:
            assert isinstance(entry, str)
            options["checksum"] = entry
            return

        try:
            checksum = self.asset.get_checksum()
            options["checksum"] = checksum
            cache[(self.asset.fileid, 0)] = checksum
        except OSError as err:
            diagnostics.append(
                CannotOpenFile(self.asset.path, err.strerror, self.node.start[0])
            )


class JSONVisitor:
    """Node visitor that creates a JSON-serializable structure."""

    def __init__(
        self,
        project_config: ProjectConfig,
        docpath: PurePath,
        document: docutils.nodes.document,
    ) -> None:
        self.project_config = project_config
        self.docpath = docpath
        self.document = document
        self.state: List[n.Node] = []
        self.diagnostics: List[Diagnostic] = []
        self.static_assets: Set[StaticAsset] = set()
        self.pending: List[PendingTask] = []

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        line = util.get_line(node)

        if isinstance(node, docutils.nodes.system_message):
            level = int(node["level"])
            if level >= 2:
                level = Diagnostic.Level.from_docutils(level)
                msg = node[0].astext()
                self.diagnostics.append(DocUtilsParseError(msg, util.get_line(node)))
            raise docutils.nodes.SkipNode()
        elif isinstance(node, (docutils.nodes.definition, docutils.nodes.field_list)):
            return
        elif isinstance(node, docutils.nodes.document):
            self.state.append(n.Root((0,), [], {}))
            return
        elif isinstance(node, docutils.nodes.field):
            key = node.children[0].astext()
            value = node.children[1].astext()
            top = self.state[-1]
            if isinstance(top, n.Root):
                top.options[key] = value
            else:
                self.diagnostics.append(
                    OptionsNotSupported(
                        "Options not supported here", util.get_line(node.children[0])
                    )
                )
            raise docutils.nodes.SkipNode()
        elif isinstance(node, rstparser.code):
            doc = n.Code(
                (line,),
                node["lang"] if "lang" in node else None,
                node["copyable"],
                node["emphasize_lines"] if "emphasize_lines" in node else None,
                node.astext(),
                node["linenos"],
            )
            top_of_state = self.state[-1]
            assert isinstance(top_of_state, n.Parent)
            top_of_state.children.append(doc)
            raise docutils.nodes.SkipNode()
        elif isinstance(node, docutils.nodes.block_quote):
            # We are uninterested in docutils blockquotes: they're too easy to accidentally
            # invoke. Treat them as an error.
            self.diagnostics.append(
                UnexpectedIndentation(
                    "Unexpected indentation", util.get_line(node.children[0])
                )
            )
            raise docutils.nodes.SkipDeparture()
        elif isinstance(node, rstparser.target_directive):
            self.state.append(n.Target((line,), [], node["domain"], node["name"], None))
        elif isinstance(node, rstparser.directive):
            directive = self.handle_directive(node, line)
            if directive:
                self.state.append(directive)
        elif isinstance(node, docutils.nodes.Text):
            self.state.append(n.Text((line,), str(node)))
            return
        elif isinstance(node, docutils.nodes.literal_block):
            self.state.append(n.LiteralBlock((line,), []))
            return
        elif isinstance(node, docutils.nodes.literal):
            self.state.append(n.Literal((line,), []))
            return
        elif isinstance(node, docutils.nodes.emphasis):
            self.state.append(n.Emphasis((line,), []))
            return
        elif isinstance(node, docutils.nodes.strong):
            self.state.append(n.Strong((line,), []))
            return
        elif isinstance(node, rstparser.ref_role):
            role_name = node["name"]
            flag = node["flag"] if "flag" in node else ""
            role: n.Role = n.RefRole(
                (line,), [], node["domain"], role_name, node["target"], flag, None, None
            )
            self.state.append(role)
            return
        elif isinstance(node, rstparser.role):
            role_name = node["name"]
            target = node["target"] if "target" in node else ""
            flag = node["flag"] if "flag" in node else ""

            if role_name == "doc":
                self.validate_doc_role(node)
                role = n.RefRole(
                    (line,), [], node["domain"], role_name, "", flag, target, None
                )
                self.state.append(role)
                return

            role = n.Role((line,), [], node["domain"], role_name, target, flag)
            self.state.append(role)
            return
        elif isinstance(node, docutils.nodes.target):
            assert (
                len(node["ids"]) <= 1
            ), f"Too many ids in this node: {self.docpath} {node}"
            if "refuri" in node:
                raise docutils.nodes.SkipNode()

            if not node["ids"]:
                self.diagnostics.append(InvalidURL(util.get_line(node)))
                # Remove the malformed node so it doesn't cause problems down the road
                self.state.pop()
                raise docutils.nodes.SkipNode()

            node_id = node["ids"][0]
            children: Any = [n.TargetIdentifier((line,), [], [node_id])]
            refuri = node["refuri"] if "refuri" in node else None
            self.state.append(n.Target((line,), children, "std", "label", refuri))
        elif isinstance(node, rstparser.target_identifier):
            self.state.append(n.TargetIdentifier((line,), [], node["ids"]))
        elif isinstance(node, docutils.nodes.definition_list):
            self.state.append(n.DefinitionList((line,), []))
        elif isinstance(node, docutils.nodes.definition_list_item):
            self.state.append(n.DefinitionListItem((line,), [], []))
        elif isinstance(node, docutils.nodes.bullet_list):
            self.state.append(n.ListNode((line,), [], False))
        elif isinstance(node, docutils.nodes.enumerated_list):
            self.state.append(n.ListNode((line,), [], True))
        elif isinstance(node, docutils.nodes.list_item):
            self.state.append(n.ListNodeItem((line,), []))
        elif isinstance(node, docutils.nodes.title):
            # Attach an anchor ID to this section
            assert node.parent
            self.state.append(n.Heading((line,), [], node.parent["ids"][0]))
        elif isinstance(node, docutils.nodes.reference):
            self.state.append(
                n.Reference(
                    (line,),
                    [],
                    node["refuri"] if "refuri" in node else None,
                    node["refname"] if "refname" in node else None,
                )
            )
        elif isinstance(node, docutils.nodes.substitution_definition):
            try:
                name = node["names"][0]
                self.state.append(n.SubstitutionDefinition((line,), [], name))
            except IndexError:
                pass
        elif isinstance(node, docutils.nodes.substitution_reference):
            self.state.append(n.SubstitutionReference((line,), [], node["refname"]))
        elif isinstance(node, docutils.nodes.footnote):
            # Autonumbered footnotes do not have a refname
            name = node["names"] if "names" in node else None
            if isinstance(name, list):
                name = name[0] if name else None
            self.state.append(n.Footnote((line,), [], node["ids"][0], name))
        elif isinstance(node, docutils.nodes.footnote_reference):
            # Autonumbered footnotes do not have a refname
            refname = node["refname"] if "refname" in node else None
            self.state.append(n.FootnoteReference((line,), [], node["ids"][0], refname))
        elif isinstance(node, docutils.nodes.section):
            self.state.append(n.Section((line,), []))
        elif isinstance(node, docutils.nodes.paragraph):
            self.state.append(n.Paragraph((line,), []))
        elif isinstance(node, rstparser.directive_argument):
            self.state.append(n.DirectiveArgument((line,), []))
        elif isinstance(node, docutils.nodes.term):
            self.state.append(_DefinitionListTerm((line,), []))
        elif isinstance(node, docutils.nodes.line_block):
            self.state.append(n.LineBlock((line,), []))
        elif isinstance(node, docutils.nodes.line):
            self.state.append(n.Line((line,), []))
        elif isinstance(node, docutils.nodes.transition):
            self.state.append(n.Transition((line,)))
        elif isinstance(node, docutils.nodes.table):
            raise docutils.nodes.SkipNode()
        elif isinstance(
            node,
            (docutils.nodes.comment, docutils.nodes.problematic, docutils.nodes.label),
        ):
            raise docutils.nodes.SkipNode()
        else:
            raise NotImplementedError(f"Unknown node type: {node.__class__.__name__}")

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        if len(self.state) == 1 or isinstance(node, docutils.nodes.definition):
            return

        popped = self.state.pop()

        top_of_state = self.state[-1]

        if isinstance(popped, _DefinitionListTerm):
            assert isinstance(
                top_of_state, n.DefinitionListItem
            ), "Definition list terms must be children of definition list items"
            top_of_state.term = popped.children
            return

        if not isinstance(top_of_state, NO_CHILDREN):
            if isinstance(top_of_state, n.Parent):
                top_of_state.children.append(popped)
            else:
                # This should not happen; unfortunately, it does: see DOCSP-7122.
                # Log some details so we can hopefully fix it when it happens next.
                logger.error(
                    "Malformed node in file %s: %s, %s",
                    self.docpath.as_posix(),
                    repr(top_of_state),
                    repr(popped),
                )

    def handle_directive(
        self, node: docutils.nodes.Node, line: int
    ) -> Optional[n.Node]:
        name = node["name"]
        domain = node["domain"]
        options = node["options"] or {}

        if name == "toctree":
            doc: n.Directive = n.TocTreeDirective(
                (line,), [], domain, name, [], options, node["entries"]
            )
            return doc

        doc = n.Directive((line,), [], domain, name, [], options)

        if (
            node.children
            and node.children[0].__class__.__name__ == "directive_argument"
        ):
            visitor = self.__make_child_visitor()
            node.children[0].walkabout(visitor)
            top_of_visitor_state = visitor.state[-1]
            assert isinstance(top_of_visitor_state, n.Parent)
            argument = top_of_visitor_state.children
            doc.argument = argument  # type: ignore
            node.children = node.children[1:]
        else:
            argument = []
            doc.argument = argument

        argument_text = None
        try:
            argument_text = argument[0].value
        except (IndexError, AttributeError):
            pass

        key: str = f"{domain}:{name}"
        if name == "todo":
            todo_text = ["TODO"]
            if argument_text:
                todo_text.extend([": ", argument_text])
            TodoInfo("".join(todo_text), util.get_line(node))
            return None

        if name in {"figure", "image", "atf-image"}:
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, util.get_line(node)))
                return doc

            try:
                static_asset = self.add_static_asset(Path(argument_text), upload=True)
                self.pending.append(PendingFigure(doc, static_asset))
            except OSError as err:
                self.diagnostics.append(
                    CannotOpenFile(argument_text, err.strerror, util.get_line(node))
                )

        elif name == "list-table":
            # Calculate the expected number of columns for this list-table structure.
            expected_num_columns = 0
            if "widths" in options:
                expected_num_columns = len(options["widths"].split(" "))
            bullet_list = node.children[0]
            for list_item in bullet_list.children:
                if expected_num_columns == 0:
                    expected_num_columns = len(list_item.children[0].children)
                for bullets in list_item.children:
                    self.validate_list_table(bullets, expected_num_columns)

        elif name == "literalinclude":
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, line))
                return doc

            asset_path = Path(argument_text)
            lang = (
                options["language"]
                if "language" in options
                else asset_path.suffix.lstrip(".")
            )
            code = n.Code(
                (line,),
                lang,
                "copyable" not in options or options["copyable"] == "true",
                [],
                "",
                "linenos" in options,
            )

            try:
                static_asset = self.add_static_asset(asset_path, False)
                self.pending.append(PendingLiteralInclude(code, static_asset, options))
            except OSError as err:
                self.diagnostics.append(
                    CannotOpenFile(argument_text, err.strerror, util.get_line(node))
                )
            except ValueError as err:
                msg = f'Invalid "literalinclude": {err}'
                self.diagnostics.append(InvalidLiteralInclude(msg, util.get_line(node)))
            return code
        elif name == "include":
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, util.get_line(node)))
                return doc

            fileid, path = util.reroot_path(
                Path(argument_text), self.docpath, self.project_config.source_path
            )

            # Validate if file exists
            if not path.is_file():
                # Check if file is snooty-generated
                if (
                    fileid.match("steps/*.rst")
                    or fileid.match("extracts/*.rst")
                    or fileid.match("release/*.rst")
                    or fileid.match("option/*.rst")
                    or fileid.match("toc/*.rst")
                    or fileid.match("apiargs/*.rst")
                    or fileid == FileId("includes/hash.rst")
                ):
                    pass
                else:
                    self.diagnostics.append(
                        CannotOpenFile(
                            argument_text,
                            os.strerror(errno.ENOENT),
                            util.get_line(node),
                        )
                    )
        elif name == "cardgroup-card":
            image_argument = options.get("image", None)

            if image_argument is None:
                self.diagnostics.append(
                    ExpectedImageArg(
                        f'"{name}" expected an image argument', util.get_line(node)
                    )
                )
                return doc

            try:
                static_asset = self.add_static_asset(Path(image_argument), upload=True)
                self.pending.append(PendingFigure(doc, static_asset))
            except OSError as err:
                self.diagnostics.append(
                    CannotOpenFile(image_argument, err.strerror, util.get_line(node))
                )
        elif name in {"pubdate", "updated-date"}:
            if "date" in node:
                doc.options["date"] = node["date"]
        elif key in {"devhub:author", ":og", ":twitter"}:
            # Grab image from options array and save as static asset
            image_argument = options.get("image")

            if not image_argument:
                # Warn writers that an image is suggested, but do not require
                self.diagnostics.append(ImageSuggested(name, util.get_line(node)))
            else:
                try:
                    static_asset = self.add_static_asset(
                        Path(image_argument), upload=True
                    )
                    self.pending.append(PendingFigure(doc, static_asset))
                except OSError as err:
                    self.diagnostics.append(
                        CannotOpenFile(
                            image_argument, err.strerror, util.get_line(node)
                        )
                    )

        return doc

    def validate_doc_role(self, node: docutils.nodes.Node) -> None:
        """Validate target for doc role"""
        resolved_target_path = util.add_doc_target_ext(
            node["target"], self.docpath, self.project_config.source_path
        )

        if not resolved_target_path.is_file():
            self.diagnostics.append(
                CannotOpenFile(
                    resolved_target_path, os.strerror(errno.ENOENT), util.get_line(node)
                )
            )

    def validate_list_table(
        self, node: docutils.nodes.Node, expected_num_columns: int
    ) -> None:
        """Validate list-table structure"""
        if (
            isinstance(node, docutils.nodes.bullet_list)
            and len(node.children) != expected_num_columns
        ):
            msg = (
                f'expected "{expected_num_columns}" columns, saw "{len(node.children)}"'
            )
            self.diagnostics.append(
                InvalidTableStructure(msg, util.get_line(node) + len(node.children) - 1)
            )
            return

    def add_static_asset(self, path: Path, upload: bool) -> StaticAsset:
        fileid, path = util.reroot_path(
            path, self.docpath, self.project_config.source_path
        )
        static_asset = StaticAsset.load(fileid, path, upload)
        self.static_assets.add(static_asset)
        return static_asset

    def add_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def __make_child_visitor(self) -> "JSONVisitor":
        visitor = type(self)(self.project_config, self.docpath, self.document)
        visitor.diagnostics = self.diagnostics
        visitor.static_assets = self.static_assets
        visitor.pending = self.pending
        return visitor


class InlineJSONVisitor(JSONVisitor):
    """A JSONVisitor subclass which does not emit block nodes."""

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body) and not isinstance(
            node, docutils.nodes.Inline
        ):
            return

        JSONVisitor.dispatch_visit(self, node)

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body) and not isinstance(
            node, docutils.nodes.Inline
        ):
            return

        JSONVisitor.dispatch_departure(self, node)


def parse_rst(
    parser: rstparser.Parser[JSONVisitor], path: Path, text: Optional[str] = None
) -> Tuple[Page, List[Diagnostic]]:
    visitor, text = parser.parse(path, text)

    top_of_state = visitor.state[-1]
    assert isinstance(top_of_state, n.Parent)
    page = Page.create(path, None, text, top_of_state)
    page.static_assets = visitor.static_assets
    page.pending_tasks = visitor.pending
    return (page, visitor.diagnostics)


@dataclass
class EmbeddedRstParser:
    __slots__ = ("project_config", "page", "diagnostics")

    project_config: ProjectConfig
    page: Page
    diagnostics: List[Diagnostic]

    def parse_block(self, rst: str, lineno: int) -> MutableSequence[n.Node]:
        # Crudely make docutils line numbers match
        text = "\n" * lineno + rst.strip()
        parser = rstparser.Parser(self.project_config, JSONVisitor)
        visitor, _ = parser.parse(self.page.source_path, text)
        top_of_state = visitor.state[-1]
        children: MutableSequence[n.Node] = top_of_state.children  # type: ignore

        self.diagnostics.extend(visitor.diagnostics)
        self.page.static_assets.update(visitor.static_assets)
        self.page.pending_tasks.extend(visitor.pending)

        return children

    def parse_inline(self, rst: str, lineno: int) -> MutableSequence[n.InlineNode]:
        # Crudely make docutils line numbers match
        text = "\n" * lineno + rst.strip()
        parser = rstparser.Parser(self.project_config, InlineJSONVisitor)
        visitor, _ = parser.parse(self.page.source_path, text)
        top_of_state = visitor.state[-1]
        children: MutableSequence[n.InlineNode] = top_of_state.children  # type: ignore

        self.diagnostics.extend(visitor.diagnostics)
        self.page.static_assets.update(visitor.static_assets)
        self.page.pending_tasks.extend(visitor.pending)

        return children


def get_giza_category(path: PurePath) -> str:
    """Infer the Giza category of a YAML file."""
    return path.name.split("-", 1)[0]


class ProjectBackend(Protocol):
    def on_progress(self, progress: int, total: int, message: str) -> None:
        ...

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        ...

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        ...

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        ...

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        ...


class _Project:
    """Internal representation of a Snooty project with no data locking."""

    def __init__(
        self,
        root: Path,
        backend: ProjectBackend,
        filesystem_watcher: util.FileWatcher,
        build_identifiers: BuildIdentifierSet,
    ) -> None:
        root = root.resolve(strict=True)
        self.config, config_diagnostics = ProjectConfig.open(root)
        self.targets = TargetDatabase.load(self.config)

        if config_diagnostics:
            backend.on_diagnostics(
                FileId(self.config.config_path.relative_to(root)), config_diagnostics
            )

        self.parser = rstparser.Parser(self.config, JSONVisitor)
        self.backend = backend
        self.filesystem_watcher = filesystem_watcher
        self.build_identifiers = build_identifiers

        self.postprocessor = (
            DevhubPostprocessor(self.config, self.targets)
            if self.config.default_domain
            else Postprocessor(self.config, self.targets)
        )

        self.yaml_mapping: Dict[str, GizaCategory[Any]] = {
            "steps": gizaparser.steps.GizaStepsCategory(self.config),
            "extracts": gizaparser.extracts.GizaExtractsCategory(self.config),
            "release": gizaparser.release.GizaReleaseSpecificationCategory(self.config),
        }

        # For each repo-wide substitution, parse the string and save to our project config
        inline_parser = rstparser.Parser(self.config, InlineJSONVisitor)
        substitution_nodes: Dict[str, List[n.InlineNode]] = {}
        for k, v in self.config.substitutions.items():
            page, substitution_diagnostics = parse_rst(inline_parser, root, v)
            substitution_nodes[k] = list(
                deepcopy(child) for child in page.ast.children  # type: ignore
            )

            if substitution_diagnostics:
                backend.on_diagnostics(
                    self.get_fileid(self.config.config_path), substitution_diagnostics
                )

        self.config.substitution_nodes = substitution_nodes

        username = pwd.getpwuid(os.getuid()).pw_name
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, encoding="utf-8"
        ).strip()
        self.prefix = [self.config.name, username, branch]

        self.pages: Dict[FileId, Page] = {}

        self.asset_dg: "networkx.DiGraph[FileId]" = networkx.DiGraph()
        self.expensive_operation_cache = Cache()

        published_branches, published_branches_diagnostics = self.get_parsed_branches()
        if published_branches:
            self.backend.on_update_metadata(
                self.prefix,
                self.build_identifiers,
                {"publishedBranches": published_branches.serialize()},
            )

        if published_branches_diagnostics:
            backend.on_diagnostics(
                self.get_fileid(self.config.config_path), published_branches_diagnostics
            )

    def get_parsed_branches(
        self
    ) -> Tuple[Optional[PublishedBranches], List[Diagnostic]]:
        path = self.config.root
        try:
            with path.joinpath("published-branches.yaml").open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
                try:
                    result = check_type(PublishedBranches, data)
                    return result, []
                except LoadError as err:
                    line: int = getattr(err.bad_data, "_start_line", 0) + 1
                    error_node: Diagnostic = UnmarshallingError(str(err), line)
                    return None, [error_node]
        except FileNotFoundError:
            pass
        except LoadError as err:
            load_error_line: int = getattr(err.bad_data, "_start_line", 0) + 1
            load_error_node: Diagnostic = UnmarshallingError(str(err), load_error_line)
            return None, [load_error_node]
        except yaml.error.MarkedYAMLError as err:
            yaml_error_node: Diagnostic = ErrorParsingYAMLFile(
                path, str(err), err.problem_mark.line
            )
            return None, [yaml_error_node]
        return None, []

    def get_fileid(self, path: PurePath) -> FileId:
        return FileId(os.path.relpath(path, self.config.source_path))

    def get_full_path(self, fileid: FileId) -> Path:
        return self.config.source_path.joinpath(fileid)

    def get_page_ast(self, path: Path) -> n.Node:
        """Update page file (.txt) with current text and return fully populated page AST"""
        # Get incomplete AST of page
        fileid = self.get_fileid(path)
        page = self.pages[fileid]

        # Fill in missing include nodes
        assert isinstance(page.ast, n.Parent)
        return self._populate_include_nodes(page.ast)

    def get_project_name(self) -> str:
        return self.config.name

    def get_project_title(self) -> str:
        return self.config.title

    def update(self, path: Path, optional_text: Optional[str] = None) -> None:
        diagnostics: Dict[PurePath, List[Diagnostic]] = {path: []}
        prefix = get_giza_category(path)
        _, ext = os.path.splitext(path)
        pages: List[Page] = []
        if ext in RST_EXTENSIONS:
            page, page_diagnostics = parse_rst(self.parser, path, optional_text)
            pages.append(page)
            diagnostics[path] = page_diagnostics
        elif ext == ".yaml" and prefix in self.yaml_mapping:
            file_id = os.path.basename(path)
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
                    giza_node = giza_category.reify_file_id(file_id, diagnostics)
                except KeyError:
                    logging.warn("No file found in registry: %s", file_id)
                    continue

                steps, text, parse_diagnostics = giza_category.parse(
                    path, optional_text
                )
                file_diagnostics.extend(parse_diagnostics)

                def create_page(filename: str) -> Tuple[Page, EmbeddedRstParser]:
                    page = Page.create(
                        giza_node.path, filename, text, n.Root((-1,), [], {})
                    )
                    return (
                        page,
                        EmbeddedRstParser(self.config, page, file_diagnostics),
                    )

                giza_category.add(path, text, steps)
                pages = giza_category.to_pages(
                    giza_node.path, create_page, giza_node.data
                )
                path = giza_node.path
                diagnostics.setdefault(path).extend(file_diagnostics)
        else:
            raise ValueError("Unknown file type: " + str(path))

        for source_path, diagnostic_list in diagnostics.items():
            self.backend.on_diagnostics(self.get_fileid(source_path), diagnostic_list)

        for page in pages:
            self._page_updated(page, diagnostic_list)
            fileid = self.get_fileid(page.fake_full_path())
            self.backend.on_update(self.prefix, self.build_identifiers, fileid, page)

    def delete(self, path: PurePath) -> None:
        file_id = os.path.basename(path)
        for giza_category in self.yaml_mapping.values():
            del giza_category[file_id]

        self.backend.on_delete(self.get_fileid(path), self.build_identifiers)

    def build(self, max_workers: Optional[int] = None) -> None:
        all_yaml_diagnostics: Dict[PurePath, List[Diagnostic]] = {}
        pool = multiprocessing.Pool(max_workers)
        with util.PerformanceLogger.singleton().start("parse rst"):
            try:
                paths = util.get_files(self.config.source_path, RST_EXTENSIONS)
                logger.debug("Processing rst files")
                results = pool.imap_unordered(partial(parse_rst, self.parser), paths)
                for page, diagnostics in results:
                    self._page_updated(page, diagnostics)
            finally:
                # We cannot use the multiprocessing.Pool context manager API due to the following:
                # https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html#if-you-use-multiprocessing-pool
                pool.close()
                pool.join()

        # Categorize our YAML files
        logger.debug("Categorizing YAML files")
        categorized: Dict[str, List[Path]] = collections.defaultdict(list)
        for path in util.get_files(self.config.source_path, (".yaml",)):
            prefix = get_giza_category(path)
            if prefix in self.yaml_mapping:
                categorized[prefix].append(path)

        # Initialize our YAML file registry
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug("Parsing %s YAML", prefix)
            for path in categorized[prefix]:
                steps, text, diagnostics = giza_category.parse(path)
                all_yaml_diagnostics[path] = diagnostics
                giza_category.add(path, text, steps)

        # Now that all of our YAML files are loaded, generate a page for each one
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug("Processing %s YAML: %d nodes", prefix, len(giza_category))
            for file_id, giza_node in giza_category.reify_all_files(
                all_yaml_diagnostics
            ):

                def create_page(filename: str) -> Tuple[Page, EmbeddedRstParser]:
                    page = Page.create(
                        giza_node.path, filename, giza_node.text, n.Root((-1,), [], {})
                    )
                    return (
                        page,
                        EmbeddedRstParser(
                            self.config,
                            page,
                            all_yaml_diagnostics.setdefault(giza_node.path, []),
                        ),
                    )

                for page in giza_category.to_pages(
                    giza_node.path, create_page, giza_node.data
                ):
                    self._page_updated(
                        page, all_yaml_diagnostics.get(page.source_path, [])
                    )

        with util.PerformanceLogger.singleton().start("postprocessing"):
            post_metadata, post_diagnostics = self.postprocessor.run(self.pages)

        static_files = {
            "objects.inv": self.targets.generate_inventory("").dumps(
                self.config.name, ""
            )
        }
        post_metadata["static_files"] = static_files

        for fileid, page in self.postprocessor.pages.items():
            self.backend.on_update(self.prefix, self.build_identifiers, fileid, page)
        for fileid, diagnostics in post_diagnostics.items():
            self.backend.on_diagnostics(fileid, diagnostics)

        self.backend.on_update_metadata(
            self.prefix, self.build_identifiers, post_metadata
        )

    def _populate_include_nodes(self, root: n.Parent[n.Node]) -> n.Node:
        """
        Add include nodes to page AST's children.

        To render images on the Snooty extension's Snooty Preview,
        we must use the full path of the image on the user's local machine. Note that this does change the
        figure's value within the parser's dict. However, this should not change the value when using the parser
        outside of Snooty Preview, since this function is currently only called by the language server.
        """

        def replace_nodes(node: n.Node) -> n.Node:
            if isinstance(node, n.Directive):
                if node.name == "include":
                    # Get the name of the file
                    argument = node.argument[0]
                    include_filename = argument.value
                    include_filename = include_filename[1:]

                    # Get children of include file
                    include_file_page_ast = self.pages[FileId(include_filename)].ast
                    assert isinstance(include_file_page_ast, n.Parent)
                    include_node_children = include_file_page_ast.children

                    # Resolve includes within include node
                    replaced_include = list(map(replace_nodes, include_node_children))
                    node.children = replaced_include
                # Replace instances of an image's name with its full path. This allows Snooty Preview to render an image by
                # using the location of the image on the user's local machine
                elif node.name == "figure":
                    # Obtain subset of the image's path (name)
                    argument = node.argument[0]
                    image_value = argument.value

                    # Prevents the image from having a redundant path if Snooty Preview already replaced
                    # its original value.
                    source_path_str = self.config.source_path.as_posix()
                    index_match = image_value.find(source_path_str)
                    if index_match != -1:
                        repeated_offset = index_match + len(source_path_str)
                        image_value = image_value[repeated_offset:]

                    # Replace subset of path with full path of image
                    if image_value[0] == "/":
                        image_value = image_value[1:]
                    full_path = self.get_full_path(FileId(image_value))
                    argument.value = full_path.as_posix()
                # Check for include nodes among current node's children
            elif isinstance(node, n.Parent):
                for child in node.children:
                    replace_nodes(child)
            return node

        return dataclasses.replace(
            root, children=list(map(replace_nodes, root.children))
        )

    def _page_updated(self, page: Page, diagnostics: List[Diagnostic]) -> None:
        """Update any state associated with a parsed page."""
        # Finish any pending tasks
        page.finish(diagnostics, self)

        # Synchronize our asset watching
        old_assets: Set[StaticAsset] = set()
        removed_assets: Set[StaticAsset] = set()
        fileid = self.get_fileid(page.fake_full_path())

        logger.debug("Updated: %s", fileid)

        if fileid in self.pages:
            old_page = self.pages[fileid]
            old_assets = old_page.static_assets
            removed_assets = old_page.static_assets.difference(page.static_assets)

        new_assets = page.static_assets.difference(old_assets)
        for asset in new_assets:
            try:
                self.filesystem_watcher.watch_file(asset.path)
            except OSError as err:
                # Missing static asset directory: don't process it. We've already raised a
                # diagnostic to the user.
                logger.debug(f"Failed to set up watch: {err}")
                page.static_assets.remove(asset)
        for asset in removed_assets:
            self.filesystem_watcher.end_watch(asset.path)

        # Update dependents
        try:
            self.asset_dg.remove_node(self.get_fileid(page.source_path))
        except networkx.exception.NetworkXError:
            pass
        self.asset_dg.add_edges_from(
            (self.get_fileid(page.source_path), self.get_fileid(asset.path))
            for asset in page.static_assets
        )

        # Report to our backend
        self.pages[fileid] = page
        self.backend.on_diagnostics(self.get_fileid(page.source_path), diagnostics)

    def on_asset_event(self, ev: watchdog.events.FileSystemEvent) -> None:
        asset_path = self.get_fileid(Path(ev.src_path))

        # Revoke any caching that might have been performed on this file
        try:
            del self.expensive_operation_cache[asset_path]
        except KeyError:
            pass

        # Rebuild any pages depending on this asset
        for page_id in list(self.asset_dg.predecessors(asset_path)):
            self.update(self.pages[page_id].source_path)


class Project:
    """A Snooty project, providing high-level operations on a project such as
       requesting a rebuild, and updating a file based on new contents.

       This class's public methods are thread-safe."""

    __slots__ = ("_project", "_lock", "_filesystem_watcher")

    def __init__(
        self, root: Path, backend: ProjectBackend, build_identifiers: BuildIdentifierSet
    ) -> None:
        self._filesystem_watcher = util.FileWatcher(self._on_asset_event)
        self._project = _Project(
            root, backend, self._filesystem_watcher, build_identifiers
        )
        self._lock = threading.Lock()
        self._filesystem_watcher.start()

    @property
    def config(self) -> ProjectConfig:
        return self._project.config

    def get_fileid(self, path: PurePath) -> FileId:
        """Create a FileId from a path."""
        # We don't need to obtain a lock because this method only operates on
        # _Project.root, which never changes after creation.
        return self._project.get_fileid(path)

    def get_full_path(self, fileid: FileId) -> Path:
        # We don't need to obtain a lock because this method only operates on
        # _Project.root, which never changes after creation.
        return self._project.get_full_path(fileid)

    def get_page_ast(self, path: Path) -> n.Node:
        """Return complete AST of page with updated text"""
        with self._lock:
            return self._project.get_page_ast(path)

    def get_project_name(self) -> str:
        return self._project.get_project_name()

    def update(self, path: Path, optional_text: Optional[str] = None) -> None:
        """Re-parse a file, optionally using the provided text rather than reading the file."""
        with self._lock:
            self._project.update(path, optional_text)

    def delete(self, path: PurePath) -> None:
        """Mark a path as having been deleted."""
        with self._lock:
            self._project.delete(path)

    def build(self, max_workers: Optional[int] = None) -> None:
        """Build the full project."""
        with self._lock:
            self._project.build(max_workers)

    def stop_monitoring(self) -> None:
        """Stop the filesystem monitoring thread associated with this project."""
        self._filesystem_watcher.stop(join=True)

    def _on_asset_event(self, ev: watchdog.events.FileSystemEvent) -> None:
        with self._lock:
            self._project.on_asset_event(ev)

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_monitoring()

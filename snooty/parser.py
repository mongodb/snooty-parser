from __future__ import annotations

import collections
import errno
import getpass
import json
import logging
import multiprocessing
import os
import queue
import re
import subprocess
import threading
import urllib.parse
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePath
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    MutableSequence,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

import docutils.nodes
import docutils.utils
import networkx
import requests.exceptions
import watchdog.events
from yaml import safe_load

from . import gizaparser, n, rstparser, specparser, util
from .cache import Cache
from .diagnostics import (
    CannotOpenFile,
    ConfigurationProblem,
    Diagnostic,
    DocUtilsParseError,
    ExpectedPathArg,
    FetchError,
    ImageSuggested,
    InvalidDirectiveStructure,
    InvalidField,
    InvalidLiteralInclude,
    InvalidTableStructure,
    InvalidURL,
    MalformedGlossary,
    MalformedRelativePath,
    MissingChild,
    RemovedLiteralBlockSyntax,
    TabMustBeDirective,
    TodoInfo,
    UnexpectedIndentation,
    UnknownTabID,
    UnknownTabset,
)
from .gizaparser.nodes import GizaCategory
from .n import FileId, SerializableType
from .openapi import OpenAPI
from .page import Page, PendingTask
from .postprocess import DevhubPostprocessor, Postprocessor, PostprocessorResult
from .target_database import ProjectInterface, TargetDatabase
from .types import BuildIdentifierSet, ParsedBannerConfig, ProjectConfig, StaticAsset
from .util import RST_EXTENSIONS

NO_CHILDREN = (n.SubstitutionReference,)
logger = logging.getLogger(__name__)


def eligible_for_paragraph_to_block_substitution(node: docutils.nodes.Node) -> bool:
    """Test if a docutils node should emit a BlockSubstitutionReference *instead* of a normal
    Paragraph."""
    return (
        isinstance(node, docutils.nodes.paragraph)
        and len(node.children) == 1
        and isinstance(node.children[0], docutils.nodes.substitution_reference)
    )


@dataclass
class _DefinitionListTerm(n.InlineParent):
    """A vate node used for internal book-keeping that should not be exported to the AST."""

    __slots__ = ()
    type = "definition_list_term"

    def verify(self) -> None:
        assert (
            False
        ), f"{self.__class__.__name__} is private and should have been removed from AST"


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

        # It's possible for pages to synthetically create other pages that don't
        # exist in the filesystem
        self.synthetic_pages: Dict[FileId, str] = {}

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        line = util.get_line(node)

        if isinstance(node, docutils.nodes.definition):
            return
        if isinstance(node, docutils.nodes.field_list):
            top = self.state[-1]
            if isinstance(top, n.Root):
                for field in node.children:
                    key = field.children[0].astext()
                    value = field.children[1].astext()
                    top.options[key] = value
                raise docutils.nodes.SkipNode()

            self.state.append(n.FieldList((line,), []))
            return
        elif isinstance(node, docutils.nodes.document):
            self.state.append(
                n.Root((0,), [], self.project_config.get_fileid(self.docpath), {})
            )
            return
        elif isinstance(node, docutils.nodes.field):
            field_name = node.children[0].astext()
            field_list = node.parent
            assert isinstance(field_list, docutils.nodes.field_list)
            rstobject = field_list.parent
            if isinstance(rstobject, rstparser.directive):
                try:
                    # Convert list of mixed strings and tuples into a key: value map
                    supported_fields = {
                        (f if isinstance(f, str) else f[0]): (
                            None if isinstance(f, str) else f[1]
                        )
                        for f in rstobject["fields"]
                    }

                    self.state.append(
                        n.Field((line,), [], field_name, supported_fields[field_name])
                    )
                    return
                except KeyError:
                    # Handle case where field is not included in directive's rstspec entry
                    assert isinstance(rstobject, rstparser.directive)
                    self.diagnostics.append(
                        InvalidField(
                            f"""Field {field_name} not supported by directive {rstobject["name"]}""",
                            util.get_line(node.children[0]),
                        )
                    )
            else:
                # Handle case where :field: does not appear in a directive
                self.diagnostics.append(
                    InvalidField(
                        f"""Field {field_name} must be used in a valid directive""",
                        util.get_line(node.children[0]),
                    )
                )
            raise docutils.nodes.SkipNode()
        elif isinstance(node, docutils.nodes.field_name):
            raise docutils.nodes.SkipNode()
        elif isinstance(node, docutils.nodes.field_body):
            # Omit the field_body wrapper, but parse its children
            raise docutils.nodes.SkipDeparture()
        elif isinstance(node, rstparser.code):
            doc = n.Code(
                (line,),
                node["lang"] if "lang" in node else None,
                node["caption"] if "caption" in node else None,
                node["copyable"],
                node["emphasize_lines"] if "emphasize_lines" in node else None,
                node.astext(),
                node["linenos"],
                node["lineno_start"] if "lineno_start" in node else None,
                node["source"] if "source" in node else None,
            )
            top_of_state = self.state[-1]
            assert isinstance(top_of_state, n.Parent)
            top_of_state.children.append(doc)
            raise docutils.nodes.SkipNode()
        elif isinstance(node, docutils.nodes.block_quote):
            # We are uninterested in docutils blockquotes: they're too easy to accidentally
            # invoke. Treat them as an error.
            self.diagnostics.append(
                UnexpectedIndentation(util.get_line(node.children[0]))
            )
            raise docutils.nodes.SkipDeparture()
        elif isinstance(node, rstparser.target_directive):
            self.state.append(n.Target((line,), [], node["domain"], node["name"], None))
        elif isinstance(node, rstparser.directive):
            directive = self.handle_directive(node, line)
            if directive:
                self.state.append(directive)
        elif isinstance(node, docutils.nodes.Text):
            # docutils will inject \0000 characters into text nodes when there are escape characters
            text = str(node).replace("\x00", "")
            self.state.append(n.Text((line,), text))
            return
        elif isinstance(node, docutils.nodes.literal_block):
            self.diagnostics.append(
                RemovedLiteralBlockSyntax(util.get_line(node.children[0]))
            )
            raise docutils.nodes.SkipNode()
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
                    (line,), [], node["domain"], role_name, "", flag, (target, ""), None
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
            if not node["ids"]:
                self.diagnostics.append(InvalidURL(util.get_line(node)))
                raise docutils.nodes.SkipNode()

            node_id = node["names"][0]

            if "refuri" in node:
                self.state.append(n.NamedReference((line,), node_id, node["refuri"]))
                return

            children: Any = [n.TargetIdentifier((line,), [], [node_id])]
            self.state.append(n.Target((line,), children, "std", "label", None))
        elif isinstance(node, rstparser.target_identifier):
            self.state.append(n.TargetIdentifier((line,), [], node["ids"]))
        elif isinstance(node, docutils.nodes.definition_list):
            self.state.append(n.DefinitionList((line,), []))
        elif isinstance(node, docutils.nodes.definition_list_item):
            self.state.append(n.DefinitionListItem((line,), [], []))
        elif isinstance(node, docutils.nodes.bullet_list):
            self.state.append(n.ListNode((line,), [], n.ListEnumType.unordered, None))
        elif isinstance(node, docutils.nodes.enumerated_list):
            self.state.append(
                n.ListNode(
                    (line,),
                    [],
                    n.ListEnumType[node["enumtype"]],
                    node["start"] if "start" in node else None,
                )
            )
        elif isinstance(node, docutils.nodes.list_item):
            assert isinstance(
                self.state[-1], n.ListNode
            ), "Attempting to place a list item in a non-list context"
            self.state.append(n.ListNodeItem((line,), []))
        elif isinstance(node, docutils.nodes.title):
            # Attach an anchor ID to this section
            assert node.parent
            title_id = util.make_html5_id(node.astext().strip()).lower()
            self.state.append(n.Heading((line,), [], title_id))
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
            if node.parent and eligible_for_paragraph_to_block_substitution(
                node.parent
            ):
                block_substitution_node = n.BlockSubstitutionReference(
                    (line,), [], node["refname"]
                )
                self.state.append(block_substitution_node)
            else:
                self.state.append(n.SubstitutionReference((line,), [], node["refname"]))

            raise docutils.nodes.SkipChildren()
        elif isinstance(node, docutils.nodes.paragraph):
            if eligible_for_paragraph_to_block_substitution(node):
                # We don't want a paragraph node here: instead, we'll (next) create a BlockSubstitutionReference node
                raise docutils.nodes.SkipDeparture()
            self.state.append(n.Paragraph((line,), []))
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
        elif isinstance(node, (docutils.nodes.problematic, docutils.nodes.label)):
            raise docutils.nodes.SkipNode()
        elif isinstance(node, docutils.nodes.comment):
            self.state.append(n.Comment((line,), []))
        elif isinstance(node, docutils.nodes.system_message):
            level = int(node["level"])
            if level >= 2:
                level = Diagnostic.Level.from_docutils(level)
                msg = node[0].astext()
                diagnostic = DocUtilsParseError(msg, util.get_line(node))
                diagnostic.severity = level
                self.diagnostics.append(diagnostic)
            raise docutils.nodes.SkipNode()
        elif isinstance(node, rstparser.snooty_diagnostic):
            self.diagnostics.append(node["diagnostic"])
            raise docutils.nodes.SkipNode()
        else:
            lineno = util.get_line(node)
            raise NotImplementedError(
                f"Unknown node type: {node.__class__.__name__} at {self.docpath}:{lineno}"
            )

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

        if (
            isinstance(popped, n.Directive)
            and popped.options
            and "tabset" in popped.options
            and popped.options["tabset"] != "tab"
        ):
            self.handle_tabset(popped)

        elif isinstance(popped, n.Directive) and popped.name == "tabs":
            self.validate_tabs_children(popped)

        elif isinstance(popped, n.Directive) and popped.name == "io-code-block":
            self.diagnostics.extend(_validate_io_code_block_children(popped))

        elif (
            isinstance(popped, n.Directive)
            and f"{popped.domain}:{popped.name}" == ":glossary"
        ):

            definition_list = next(popped.get_child_of_type(n.DefinitionList), None)

            if definition_list is None:
                return

            if len(popped.children) != 1:
                self.diagnostics.append(MalformedGlossary(util.get_line(node)))
                return

            if popped.options.get("sorted", False):
                definition_list.children = sorted(
                    definition_list.children,
                    key=lambda DefinitionListItem: "".join(
                        term.get_text().casefold() for term in DefinitionListItem.term
                    ),
                )

            for item in definition_list.get_child_of_type(n.DefinitionListItem):
                term_text = "".join(term.get_text() for term in item.term)
                identifier = n.TargetIdentifier(item.start, [], [term_text])
                identifier.children = item.term[:]
                target = n.InlineTarget(item.start, [], "std", "term", None)
                target.children = [identifier]
                item.term.append(target)

        elif isinstance(popped, n.Directive) and popped.name == "step":
            popped.children = [n.Section((util.get_line(node),), popped.children)]

    def handle_tabset(self, node: n.Directive) -> None:
        tabset = node.options["tabset"]
        line = node.start[0]
        # retrieve dictionary associated with this specific tabset
        try:
            tab_definitions_list = specparser.Spec.get().tabs[tabset]
        except KeyError:
            self.diagnostics.append(UnknownTabset(tabset, line))
            return

        old_children = node.children
        new_children: List[n.Node] = []
        for child in old_children:
            if (not isinstance(child, n.Directive)) or child.name != "tab":
                self.diagnostics.append(
                    TabMustBeDirective(str(type(child).__class__.__name__), line)
                )
                continue

            tabid = child.options.get("tabid")
            if tabid is None:
                # Required options get warned about elsewhere, so no need to log an error
                continue

            if not isinstance(tabid, str):
                self.diagnostics.append(
                    UnknownTabID(
                        tabid,
                        tabset,
                        f"{tabid} is of type {str(type(tabid).__class__)}. Tab ids must be strings ",
                        line,
                    )
                )
                continue

            unknown_tabid = True
            # find matching title given id and insert directive_argument
            for t_idx, entry in enumerate(tab_definitions_list):
                if entry.id == tabid:
                    child.argument = [n.Text((line,), entry.title)]
                    unknown_tabid = False

            if unknown_tabid:
                self.diagnostics.append(
                    UnknownTabID(
                        tabid,
                        tabset,
                        f"{tabid} is not defined in rstspec.toml for this tabset",
                        line,
                    )
                )
                continue

            new_children.append(child)

        node.children = new_children

        # Sort tab directives based on order defined in rstspec.toml
        tabid_list = [tab.id for tab in tab_definitions_list]
        node.children = sorted(
            node.children,
            key=lambda x: tabid_list.index(cast(n.Directive, x).options["tabid"]),
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

        # Find and move the argument from the children to the "argument" field.
        argument: MutableSequence[Any] = []
        if node.children:
            index_of_argument = next(
                (
                    idx
                    for idx, value in enumerate(node.children)
                    if isinstance(value, rstparser.directive_argument)
                ),
                None,
            )
            if index_of_argument is not None:
                visitor = self.__make_child_visitor()
                node.children[index_of_argument].walkabout(visitor)
                top_of_visitor_state = visitor.state[-1]
                assert isinstance(top_of_visitor_state, n.Parent)
                argument = top_of_visitor_state.children
                del node.children[index_of_argument]

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
            TodoInfo("".join(todo_text), line)
            return None

        if name in {"figure", "image", "atf-image"}:
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, line))
                return doc

            self.validate_and_add_asset(doc, argument_text, line)

        elif name == "list-table":
            # Calculate the expected number of columns for this list-table structure.
            if not node.children:
                return doc

            expected_num_columns = 0
            if "widths" in options:
                widths = re.split(r"[,\s][\s]?", options["widths"])
                expected_num_columns = len(widths)
            bullet_list = node.children[0]
            for list_item in bullet_list.children:
                if expected_num_columns == 0 and list_item.children:
                    expected_num_columns = len(list_item.children[0].children)
                for bullets in list_item.children:
                    self.validate_list_table(bullets, expected_num_columns)

        elif name == "openapi":
            # Parsing should be done by the OpenAPI renderer on the frontend by default
            uses_rst = options.get("uses-rst", False)
            # The frontend will grab the file contents from Realm, using the argument as its key
            uses_realm = options.get("uses-realm", False)

            if argument_text is None:
                if uses_realm or uses_rst:
                    self.diagnostics.append(ExpectedPathArg(name, line))
                    return doc

                # Check if argument is a url instead
                url_argument = None
                spec = None
                try:
                    url_argument = argument[0].refuri
                    response = util.HTTPCache.singleton().get(url_argument)
                    file_content = str(response, "utf-8")
                    spec = json.dumps(safe_load(file_content))
                    spec_node = n.Text((line,), spec)
                    doc.children.append(spec_node)
                    return doc
                except:
                    pass
                if url_argument is None:
                    self.diagnostics.append(ExpectedPathArg(name, line))
                elif spec is None:
                    self.diagnostics.append(InvalidURL(line))
                return doc

            if uses_realm:
                return doc

            openapi_fileid, filepath = util.reroot_path(
                FileId(argument_text), self.docpath, self.project_config.source_path
            )

            try:
                if uses_rst:
                    with open(filepath) as f:
                        openapi = OpenAPI.load(f)

                    def create_page() -> Tuple[Page, EmbeddedRstParser]:
                        # Create dummy page in order to use EmbeddedRstParser
                        page = Page.create(
                            filepath,
                            None,
                            "",
                            n.Root((-1,), [], openapi_fileid, {}),
                        )
                        diagnostics: Dict[PurePath, List[Diagnostic]] = {}
                        return (
                            page,
                            EmbeddedRstParser(
                                self.project_config,
                                page,
                                diagnostics.setdefault(filepath, []),
                            ),
                        )

                    openapi_ast, diagnostics = openapi.to_ast(filepath, create_page)
                    self.diagnostics.extend(diagnostics)
                    doc.children.extend(openapi_ast)

                else:
                    with open(filepath) as f:
                        spec = json.dumps(safe_load(f))
                        spec_node = n.Text((line,), spec)
                        doc.children.append(spec_node)

            except OSError as err:
                self.diagnostics.append(
                    CannotOpenFile(argument_text, err.strerror, line)
                )
                return doc

        elif name == "literalinclude" or name == "input" or name == "output":
            if name == "literalinclude":
                if argument_text is None:
                    self.diagnostics.append(ExpectedPathArg(name, line))
                    return doc
            if argument_text is None:
                return doc

            _, filepath = util.reroot_path(
                FileId(argument_text), self.docpath, self.project_config.source_path
            )

            # Attempt to read the literally included file
            try:
                text = filepath.read_text(encoding="utf-8")
            except OSError as err:
                self.diagnostics.append(
                    CannotOpenFile(argument_text, err.strerror, line)
                )
                return doc
            except UnicodeDecodeError as err:
                self.diagnostics.append(CannotOpenFile(argument_text, str(err), line))
                return doc

            lines = text.split("\n")
            # Capture the original file-length before splicing it
            len_file = len(lines)

            def _locate_text(text: str) -> int:
                """
                Searches the literally-included file ('lines') for the specified text. If no such text is found,
                add an InvalidLiteralInclude diagnostic.
                """
                assert isinstance(text, str)
                loc = next((idx for idx, line in enumerate(lines) if text in line), -1)
                if loc < 0:
                    self.diagnostics.append(
                        InvalidLiteralInclude(f'"{text}" not found in {filepath}', line)
                    )
                return loc

            # Locate the start_after query
            start_after = 0
            if "start-after" in options:
                start_after_text = options["start-after"]
                # start_after = self._locate_text(start_after_text, lines, line, text)
                start_after = _locate_text(start_after_text)
                # Only increment start_after if text is specified, to avoid capturing the start_after_text
                start_after += 1

            # ...now locate the end_before query
            end_before = len(lines)
            if "end-before" in options:
                end_before_text = options["end-before"]
                # end_before = self._locate_text(end_before_text, lines, line, text)
                end_before = _locate_text(end_before_text)

            # Check that start_after_text precedes end_before_text (and end_before exists)
            if start_after >= end_before >= 0:
                self.diagnostics.append(
                    InvalidLiteralInclude(
                        f'"{end_before_text}" precedes "{start_after_text}" in {filepath}',
                        line,
                    )
                )

            # If we failed to locate end_before text, default to the end-of-file
            if end_before == -1:
                end_before = len(lines)

            lines = lines[start_after:end_before]

            dedent = 0
            if "dedent" in options:
                # Dedent is specified as a flag
                if isinstance(options["dedent"], bool):
                    # Deduce a reasonable dedent
                    try:
                        dedent = min(
                            len(line) - len(line.lstrip())
                            for line in lines
                            if len(line.lstrip()) > 0
                        )
                    except ValueError:
                        # Handle the (unlikely) case where there are no non-empty lines
                        dedent = 0
                # Dedent is specified as a nonnegative integer (number of characters):
                # Note: since boolean is a subtype of int, this conditonal must follow the
                # above bool-type conditional.
                elif isinstance(options["dedent"], int):
                    dedent = options["dedent"]
                else:
                    self.diagnostics.append(
                        InvalidLiteralInclude(
                            f'Dedent "{dedent}" of type {type(dedent)}; expected nonnegative integer or flag',
                            line,
                        )
                    )
                    return doc

            lines = [line[dedent:] for line in lines]

            emphasize_lines = None
            if "emphasize-lines" in options:
                try:
                    emphasize_lines = rstparser.parse_linenos(
                        options["emphasize-lines"], len_file
                    )
                except ValueError as err:
                    self.diagnostics.append(
                        InvalidLiteralInclude(
                            f"Invalid emphasize-lines specification caused: {err}",
                            line,
                        )
                    )

            span = (line,)
            language = options["language"] if "language" in options else ""
            caption = options["caption"] if "caption" in options else None
            copyable = "copyable" not in options or options["copyable"] == "True"
            selected_content = "\n".join(lines)
            linenos = "linenos" in options
            lineno_start = (
                options["lineno-start"] if "lineno-start" in options else None
            )
            source = options["source"] if "source" in options else None

            code = n.Code(
                span,
                language,
                caption,
                copyable,
                emphasize_lines,
                selected_content,
                linenos,
                lineno_start,
                source,
            )

            doc.children.append(code)

        elif name == "io-code-block":
            if argument_text is not None:
                self.diagnostics.append(
                    InvalidDirectiveStructure(
                        "did not expect an argument, language should be passed as an option to input/output directives",
                        line,
                    )
                )
                return doc

        elif name == "include":
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, util.get_line(node)))
                return doc

            fileid, path = util.reroot_path(
                FileId(argument_text), self.docpath, self.project_config.source_path
            )

        elif name == "sharedinclude":
            if argument_text is None:
                self.diagnostics.append(ExpectedPathArg(name, util.get_line(node)))
                return doc

            if self.project_config.sharedinclude_root is None:
                self.diagnostics.append(
                    ConfigurationProblem(
                        "To use sharedinclude, you must provide a 'sharedinclude_root' option in snooty.toml",
                        util.get_line(node),
                    )
                )
                return doc

            url = urllib.parse.urljoin(
                self.project_config.sharedinclude_root, argument_text
            )
            try:
                response = util.HTTPCache.singleton().get(url)
            except requests.exceptions.RequestException as err:
                self.diagnostics.append(
                    CannotOpenFile(argument_text, str(err), util.get_line(node))
                )
                return doc

            new_fileid = FileId("sharedinclude").joinpath(argument_text)
            doc.argument = [n.Text((line,), new_fileid.as_posix())]
            self.synthetic_pages[new_fileid] = str(response, "utf-8")

        elif name == "step":
            # Create heading for the step's argument, similar to titles of Giza/YAML steps
            if argument:
                argument_text = "".join(node.get_text() for node in argument)
                heading_id = util.make_html5_id(argument_text.strip()).lower()

                heading = n.Heading((line,), [], heading_id)
                heading.children = argument
                doc.children.insert(0, heading)

        elif name == "chapter":
            image_argument = options.get("image")
            if image_argument:
                self.validate_and_add_asset(doc, image_argument, line)

            icon_argument = options.get("icon")
            if icon_argument:
                self.validate_and_add_asset(doc, icon_argument, line)

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
                self.validate_and_add_asset(doc, image_argument, line)

        elif key in {"mongodb:card"}:
            image_argument = options.get("icon")
            url_argument = options.get("url")

            if image_argument:
                self.validate_and_add_asset(doc, image_argument, line)
            if url_argument and not url_argument.startswith("http"):
                self.validate_relative_url(url_argument, line)

        return doc

    def validate_and_add_asset(
        self, doc: n.Directive, image_argument: str, line: int
    ) -> None:
        try:
            static_asset = self.add_static_asset(image_argument, upload=True)
            self.pending.append(PendingFigure(doc, static_asset))
        except OSError as err:
            self.diagnostics.append(
                CannotOpenFile(Path(image_argument), err.strerror, line)
            )

    def validate_relative_url(self, url_argument: str, line: int) -> None:
        """Validate relative URL points to page within current docs site.
        URLs can be of the form /foo, foo, /foo/"""
        target_path = util.add_doc_target_ext(
            url_argument, self.docpath, self.project_config.source_path
        )

        if not target_path.is_file():
            err_message = f"{os.strerror(errno.ENOENT)} for relative path {url_argument}"
            self.diagnostics.append(CannotOpenFile(target_path, err_message, line))
        elif re.search(r"([\/])\1", url_argument) is not None:
            self.diagnostics.append(MalformedRelativePath(url_argument, line))

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
                f'Expected "{expected_num_columns}" columns, saw "{len(node.children)}"'
            )
            self.diagnostics.append(
                InvalidTableStructure(msg, util.get_line(node) + len(node.children) - 1)
            )
            return

    def validate_tabs_children(self, node: n.Directive) -> None:
        new_children: List[n.Node] = []
        line = node.start[0]
        for child in node.children:
            if (not isinstance(child, n.Directive)) or child.name != "tab":
                self.diagnostics.append(
                    TabMustBeDirective(str(type(child).__class__.__name__), line)
                )
                continue
            new_children.append(child)
        node.children = new_children
        return

    def add_static_asset(self, raw_path: str, upload: bool) -> StaticAsset:
        fileid, path = util.reroot_path(
            FileId(raw_path), self.docpath, self.project_config.source_path
        )
        static_asset = StaticAsset.load(raw_path, fileid, path, upload)
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


def _validate_io_code_block_children(node: n.Directive) -> List[Diagnostic]:
    """Validates that a given io-code-block directive has 1 input and 1 output
    child nodes, and copies the io-code-block's options into the options of the
    underlying code nodes."""
    # new_children should contain input and output directives
    new_children: List[n.Node] = []
    line = node.start[0]
    expected_children = {"input", "output"}
    diagnostics: List[Diagnostic] = []

    for child in node.children:
        if not isinstance(child, n.Directive):
            diagnostics.append(
                InvalidDirectiveStructure(
                    f"expected input/output child directives, saw {child.type}",
                    line,
                )
            )
            continue

        if child.name in expected_children:
            new_grandchildren: List[n.Node] = []

            # Input or output should have 1 child Code node
            if len(child.children) == 1:
                expected_children.remove(child.name)

                # child nodes for input/output will inherit parent options
                grandchild = child.children[0]
                if isinstance(grandchild, n.Code):
                    grandchild.lang = (
                        child.options["language"]
                        if "language" in child.options
                        else None
                    )
                    grandchild.caption = (
                        node.options["caption"] if "caption" in node.options else None
                    )
                    grandchild.copyable = (
                        True
                        if "copyable" in node.options and node.options["copyable"]
                        else False
                    )
                    grandchild.source = (
                        node.options["source"] if "source" in node.options else None
                    )
                    new_grandchildren.append(grandchild)
                child.children = new_grandchildren
                new_children.append(child)
        else:
            # either duplicate input/output or invalid child is provided
            msg = f"already contains an {child.name} directive"
            if not (child.name == "input" or child.name == "output"):
                msg = f"does not accept child {child.name}"
            diagnostics.append(
                InvalidDirectiveStructure(
                    msg,
                    line,
                )
            )

    # handle missing nested input and/or output directives
    if len(expected_children) != 0 or len(new_children) != 2:
        for expected_child in expected_children:
            diagnostics.append(MissingChild("io-code-block", expected_child, line))
            if expected_child == "input":
                new_children = []

    node.children = new_children
    return diagnostics


class InlineJSONVisitor(JSONVisitor):
    """A JSONVisitor subclass which does not emit block nodes."""

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body) and not isinstance(
            node, (docutils.nodes.Inline, docutils.nodes.system_message)
        ):
            return

        JSONVisitor.dispatch_visit(self, node)

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body) and not isinstance(
            node, (docutils.nodes.Inline, docutils.nodes.system_message)
        ):
            return

        JSONVisitor.dispatch_departure(self, node)


def parse_rst(
    parser: rstparser.Parser[JSONVisitor], path: Path, text: Optional[str] = None
) -> Sequence[Tuple[Page, List[Diagnostic]]]:
    visitor, text = parser.parse(path, text)

    top_of_state = visitor.state[-1]
    assert isinstance(top_of_state, n.Root)
    page = Page.create(path, None, text, top_of_state)
    page.static_assets = visitor.static_assets
    page.pending_tasks = visitor.pending
    result = [(page, visitor.diagnostics)]

    # Pages can create additional pages that are not "real" filesystem artifacts
    for synthetic_page, synthetic_page_text in visitor.synthetic_pages.items():
        result.extend(
            parse_rst(
                parser,
                parser.project_config.source_path.joinpath(synthetic_page),
                synthetic_page_text,
            )
        )

    return result


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


class ProjectBackend:
    def on_config(self, config: ProjectConfig) -> None:
        pass

    def on_progress(self, progress: int, total: int, message: str) -> None:
        ...

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        ...

    def set_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
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

    def flush(self) -> None:
        ...

    def close(self) -> None:
        pass


class PageDatabase:
    """A database of FileId->Page mappings that ensures the postprocessing pipeline
    is run correctly. Raw parsed pages are added, flush() is called, then postprocessed
    pages can be accessed.

    All methods are thread-safe, but data returned should not be mutated by more than one
    thread."""

    def __init__(self, postprocessor_factory: Callable[[], Postprocessor]) -> None:
        self._lock = threading.Lock()

        self.postprocessor_factory = postprocessor_factory
        self._parsed: Dict[FileId, Tuple[Page, FileId, List[Diagnostic]]] = {}
        self._orphan_diagnostics: Dict[FileId, List[Diagnostic]] = {}
        self.__cached = PostprocessorResult({}, {}, {}, TargetDatabase())
        self.__changed_pages: Set[FileId] = set()

        def start(
            cancellation_token: threading.Event,
            args: Postprocessor,
        ) -> PostprocessorResult:
            with self._lock:
                if not self.__changed_pages:
                    return self.__cached

                with util.PerformanceLogger.singleton().start("copy"):
                    copied_pages = {}
                    for k, v in self._parsed.items():
                        if cancellation_token.is_set():
                            raise util.CancelledException()

                        copied_pages[k] = util.fast_deep_copy(v[0])

            with util.PerformanceLogger.singleton().start("postprocessing"):
                result = args.run(copied_pages, cancellation_token)

            with self._lock:
                self.__cached = result
                self.__changed_pages.clear()

            return result

        self.worker: util.WorkerLauncher[
            Postprocessor, PostprocessorResult
        ] = util.WorkerLauncher("postprocessor", start)

    def set_orphan_diagnostics(self, key: FileId, value: List[Diagnostic]) -> None:
        """Some diagnostics can't be associated with a parsed Page because of underlying
        problems like invalid YAML syntax. These are orphan diagnostics, and we need
        to track them too."""
        with self._lock:
            self._orphan_diagnostics[key] = value

    def __setitem__(
        self, key: FileId, value: Tuple[Page, FileId, List[Diagnostic]]
    ) -> None:
        """Set a raw parsed page."""
        with self._lock:
            self._parsed[key] = value
            self.__changed_pages.add(key)

    def get(self, key: FileId) -> Optional[Page]:
        try:
            return self[key]
        except KeyError:
            return None

    def __getitem__(self, key: FileId) -> Page:
        """If the postprocessor has been run since modifications were made, fetch a postprocessed page."""
        with self._lock:
            assert not self.__changed_pages
            return self.__cached.pages[key]

    def __contains__(self, key: FileId) -> bool:
        """Check if a given page exists in the parsed set."""
        with self._lock:
            return key in self._parsed

    def __delitem__(self, key: FileId) -> None:
        with self._lock:
            try:
                del self._parsed[key]
            except KeyError:
                pass

            try:
                del self._orphan_diagnostics[key]
            except KeyError:
                pass

    def merge_diagnostics(
        self, *others: Dict[FileId, List[Diagnostic]]
    ) -> Dict[FileId, List[Diagnostic]]:
        with self._lock:
            result: Dict[FileId, List[Diagnostic]] = {
                v[1]: list(v[2]) for v in self._parsed.values()
            }

            for key, diagnostics in self._orphan_diagnostics.items():
                if key in result:
                    result[key].extend(diagnostics)
                else:
                    result[key] = list(diagnostics)

        all_keys: Set[FileId] = set()
        for other in others:
            all_keys.update(other.keys())

        for key in all_keys:
            try:
                lst = result[key]
            except KeyError:
                lst = []
                result[key] = lst
            for other in others:
                try:
                    lst.extend(other[key])
                except KeyError:
                    pass

        return result

    def flush(
        self,
    ) -> queue.Queue[Tuple[Optional[PostprocessorResult], Optional[Exception]]]:
        """Run the postprocessor if and only if any pages have changed, and return postprocessing results."""
        postprocessor = self.postprocessor_factory()
        return self.worker.run(postprocessor)

    def flush_and_wait(self) -> PostprocessorResult:
        result, exception = self.flush().get()
        if exception:
            raise exception
        assert result is not None
        return result

    def cancel(self) -> None:
        self.worker.cancel()


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

        # We might have found the project in a parent directory. Use that.
        root = self.config.root

        self.targets, failed_requests = TargetDatabase.load(self.config)
        self.initialization_diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(
            list
        )

        snooty_config_fileid = FileId(self.config.config_path.relative_to(root))

        if failed_requests:
            fetch_diagnostics: List[Diagnostic] = [
                FetchError(message, 0) for _, message in failed_requests
            ]
            self.initialization_diagnostics[snooty_config_fileid].extend(
                fetch_diagnostics
            )
            backend.on_diagnostics(
                snooty_config_fileid,
                fetch_diagnostics,
            )

        if config_diagnostics:
            self.initialization_diagnostics[snooty_config_fileid].extend(
                config_diagnostics
            )
            backend.on_diagnostics(snooty_config_fileid, config_diagnostics)

        self.parser = rstparser.Parser(self.config, JSONVisitor)

        self.backend = backend
        self._backend_lock = threading.Lock()

        self.filesystem_watcher = filesystem_watcher
        self.build_identifiers = build_identifiers

        self.yaml_mapping: Dict[str, GizaCategory[Any]] = {
            "steps": gizaparser.steps.GizaStepsCategory(self.config),
            "extracts": gizaparser.extracts.GizaExtractsCategory(self.config),
            "release": gizaparser.release.GizaReleaseSpecificationCategory(self.config),
        }

        # For each repo-wide substitution, parse the string and save to our project config
        inline_parser = rstparser.Parser(self.config, InlineJSONVisitor)
        substitution_nodes: Dict[str, List[n.InlineNode]] = {}
        for k, v in self.config.substitutions.items():
            # XXX: Assume that a single Page is generated (e.g. there's no sharedinclude)
            page, substitution_diagnostics = parse_rst(inline_parser, root, v)[0]
            substitution_nodes[k] = list(
                deepcopy(child) for child in page.ast.children  # type: ignore
            )

            if substitution_diagnostics:
                self.initialization_diagnostics[snooty_config_fileid].extend(
                    substitution_diagnostics
                )
                backend.on_diagnostics(
                    self.config.get_fileid(self.config.config_path),
                    substitution_diagnostics,
                )

        self.config.substitution_nodes = substitution_nodes

        # Parse banner value and instantiate a banner node for postprocessing, if a banner value is defined.
        for banner in self.config.banners:
            if banner.value:

                options = {"variant": banner.variant}
                banner_node = ParsedBannerConfig(
                    banner.targets,
                    n.Directive((-1,), [], "mongodb", "banner", [], options),
                )

                # XXX: Assume that a single Page is generated (e.g. there's no sharedinclude)
                page, banner_diagnostics = parse_rst(inline_parser, root, banner.value)[
                    0
                ]
                banner_node.node.children = page.ast.children
                if banner_node.node.children:
                    self.config.banner_nodes.append(banner_node)
                if banner_diagnostics:
                    self.initialization_diagnostics[snooty_config_fileid].extend(
                        banner_diagnostics
                    )
                    backend.on_diagnostics(
                        self.config.get_fileid(self.config.config_path),
                        banner_diagnostics,
                    )

        username = getpass.getuser()
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=root,
                encoding="utf-8",
                stderr=subprocess.PIPE,
            ).strip()
        except subprocess.CalledProcessError as err:
            logger.info("git error getting branch name: %s", err.stderr)
            branch = "current"

        self.prefix = [self.config.name, username, branch]

        self.pages = PageDatabase(
            lambda: DevhubPostprocessor(self.config, self.targets.copy_clean_slate())
            if self.config.default_domain == "devhub"
            else Postprocessor(self.config, self.targets.copy_clean_slate())
        )

        self.asset_dg: "networkx.DiGraph[FileId]" = networkx.DiGraph()
        self.expensive_operation_cache: Cache[FileId] = Cache()
        self.backend.on_config(self.config)

    def get_full_path(self, fileid: FileId) -> Path:
        return self.config.source_path.joinpath(fileid)

    def get_page_ast(self, path: Path) -> n.Node:
        """Update page file (.txt) with current text and return fully populated page AST"""
        # Get incomplete AST of page
        fileid = self.config.get_fileid(path)
        result = self.pages.flush_and_wait()
        page = result.pages[fileid]
        assert isinstance(page.ast, n.Parent)
        return page.ast

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
            for page, page_diagnostics in parse_rst(self.parser, path, optional_text):
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
                        giza_node.path,
                        filename,
                        text,
                        n.Root((-1,), [], self.config.get_fileid(FileId(filename)), {}),
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
                diagnostics.setdefault(path, []).extend(file_diagnostics)
        else:
            raise ValueError("Unknown file type: " + str(path))

        with self._backend_lock:
            for source_path, diagnostic_list in diagnostics.items():
                self.backend.on_diagnostics(
                    self.config.get_fileid(source_path), diagnostic_list
                )

        for page in pages:
            self._page_updated(page, diagnostic_list)
            fileid = self.config.get_fileid(page.fake_full_path())
            with self._backend_lock:
                self.backend.on_update(
                    self.prefix, self.build_identifiers, fileid, page
                )

            self.backend.flush()

    def delete(self, path: PurePath) -> None:
        file_id = os.path.basename(path)
        for giza_category in self.yaml_mapping.values():
            try:
                del giza_category[file_id]
            except KeyError:
                pass

        fileid = self.config.get_fileid(path)

        with self._backend_lock:
            self.backend.on_delete(fileid, self.build_identifiers)

        del self.pages[fileid]

    def build(
        self, max_workers: Optional[int] = None, postprocess: bool = True
    ) -> None:
        all_yaml_diagnostics: Dict[PurePath, List[Diagnostic]] = {}
        pool = multiprocessing.Pool(max_workers)
        with util.PerformanceLogger.singleton().start("parse rst"):
            try:
                paths = util.get_files(
                    self.config.source_path, RST_EXTENSIONS, self.config.root
                )
                logger.debug("Processing rst files")
                results = pool.imap_unordered(partial(parse_rst, self.parser), paths)
                for sequence in results:
                    for page, diagnostics in sequence:
                        self._page_updated(page, diagnostics)
            finally:
                # We cannot use the multiprocessing.Pool context manager API due to the following:
                # https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html#if-you-use-multiprocessing-pool
                pool.close()
                pool.join()

        # Categorize our YAML files
        logger.debug("Categorizing YAML files")
        categorized: Dict[str, List[Path]] = collections.defaultdict(list)
        for path in util.get_files(
            self.config.source_path, (".yaml",), self.config.root
        ):
            prefix = get_giza_category(path)
            if prefix in self.yaml_mapping:
                categorized[prefix].append(path)

        # Initialize our YAML file registry
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug("Parsing %s YAML", prefix)
            for path in categorized[prefix]:
                artifacts, text, diagnostics = giza_category.parse(path)
                if diagnostics:
                    all_yaml_diagnostics[path] = diagnostics
                giza_category.add(path, text, artifacts)

        # Now that all of our YAML files are loaded, generate a page for each one
        seen_paths: Set[Path] = set()
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
                        n.Root((-1,), [], self.config.get_fileid(FileId(filename)), {}),
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
                    seen_paths.add(page.source_path)
                    self._page_updated(
                        page, all_yaml_diagnostics.get(page.source_path, [])
                    )

        # Handle parsing and unmarshaling errors that lead to diagnostics not associated with
        # any page.
        for key in all_yaml_diagnostics:
            if key not in seen_paths:
                self.pages.set_orphan_diagnostics(
                    self.config.get_fileid(key), all_yaml_diagnostics[key]
                )

        if postprocess:
            postprocessor_result = self.postprocess()

            static_files: Dict[str, Union[str, bytes]] = {
                "objects.inv": self.targets.generate_inventory("").dumps(
                    self.config.name, ""
                )
            }

            if "static_files" in postprocessor_result.metadata:
                cast(
                    Dict[str, Union[str, bytes]],
                    postprocessor_result.metadata["static_files"],
                ).update(static_files)

            with util.PerformanceLogger.singleton().start("commit"):
                with self._backend_lock:
                    for fileid, page in postprocessor_result.pages.items():
                        self.backend.on_update(
                            self.prefix, self.build_identifiers, fileid, page
                        )
                    self.backend.flush()

            with self._backend_lock:
                self.backend.on_update_metadata(
                    self.prefix, self.build_identifiers, postprocessor_result.metadata
                )

    def cancel_postprocessor(self) -> None:
        self.pages.cancel()

    def postprocess(self) -> PostprocessorResult:
        logger.debug("Starting self.pages.flush_and_wait()")
        result = self.pages.flush_and_wait()

        merged_diagnostics = self.pages.merge_diagnostics(
            result.diagnostics, self.initialization_diagnostics
        )

        # Update our targets database
        self.targets = result.targets

        logger.debug("flush_and_wait() finished")
        with self._backend_lock:
            for fileid, diagnostics in result.diagnostics.items():
                self.backend.on_diagnostics(fileid, diagnostics)

            for fileid, diagnostics in merged_diagnostics.items():
                self.backend.set_diagnostics(fileid, diagnostics)

        return result

    def _page_updated(self, page: Page, diagnostics: List[Diagnostic]) -> None:
        """Update any state associated with a parsed page."""
        # Finish any pending tasks
        page.finish(diagnostics, self)

        # Synchronize our asset watching
        old_assets: Set[StaticAsset] = set()
        removed_assets: Set[StaticAsset] = set()
        fileid = self.config.get_fileid(page.fake_full_path())

        logger.debug("Updated: %s", fileid)

        if fileid in self.pages:
            old_page = self.pages._parsed[fileid][0]
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
            self.asset_dg.remove_node(self.config.get_fileid(page.source_path))
        except networkx.exception.NetworkXError:
            pass
        self.asset_dg.add_edges_from(
            (
                self.config.get_fileid(page.source_path),
                self.config.get_fileid(asset.path),
            )
            for asset in page.static_assets
        )

        # Report to our backend
        self.pages[fileid] = (
            page,
            self.config.get_fileid(page.source_path),
            diagnostics,
        )
        with self._backend_lock:
            self.backend.on_diagnostics(
                self.config.get_fileid(page.source_path), diagnostics
            )

    def on_asset_event(self, ev: watchdog.events.FileSystemEvent) -> None:
        asset_path = self.config.get_fileid(Path(ev.src_path))

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

    def __init__(
        self,
        root: Path,
        backend: ProjectBackend,
        build_identifiers: BuildIdentifierSet,
        watch: bool = True,
    ) -> None:
        self._filesystem_watcher = util.FileWatcher(self._on_asset_event)
        self._project = _Project(
            root, backend, self._filesystem_watcher, build_identifiers
        )
        self._lock = threading.Lock()

        self.watch = watch
        if watch:
            self._filesystem_watcher.start()

    @property
    def config(self) -> ProjectConfig:
        return self._project.config

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

    def build(
        self, max_workers: Optional[int] = None, postprocess: bool = True
    ) -> None:
        """Build the full project."""
        with self._lock:
            self._project.build(max_workers, postprocess)

    def postprocess(self) -> None:
        # The postprocessor is the only method that is intended to be thread-safe without the
        # big project lock.
        self._project.postprocess()

    def cancel_postprocessor(self) -> None:
        self._project.cancel_postprocessor()

    def stop_monitoring(self) -> None:
        """Stop the filesystem monitoring thread associated with this project."""
        if self.watch:
            self._filesystem_watcher.stop(join=True)

    def _on_asset_event(self, ev: watchdog.events.FileSystemEvent) -> None:
        with self._lock:
            self._project.on_asset_event(ev)

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_monitoring()

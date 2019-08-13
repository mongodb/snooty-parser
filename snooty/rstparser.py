import re
import sys
import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.parsers.rst.directives
import docutils.parsers.rst.directives.misc
import docutils.parsers.rst.roles
import docutils.parsers.rst.states
import docutils.statemachine
import docutils.utils
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Dict, Generic, Optional, List, Tuple, Type, TypeVar, Iterable
from typing_extensions import Protocol
from .gizaparser.parse import load_yaml
from .gizaparser import nodes
from .types import Diagnostic, ProjectConfig
from .flutter import checked, check_type, LoadError
from . import util
from . import specparser

PAT_EXPLICIT_TILE = re.compile(
    r"^(?P<label>.+?)\s*(?<!\x00)<(?P<target>.*?)>$", re.DOTALL
)
PAT_WHITESPACE = re.compile(r"^\x20*")
PAT_BLOCK_HAS_ARGUMENT = re.compile(r"^\x20*\.\.\x20[^\s]+::\s*\S+")
PACKAGE_ROOT = Path(sys.modules["snooty"].__file__).resolve().parent
if PACKAGE_ROOT.is_file():
    PACKAGE_ROOT = PACKAGE_ROOT.parent

# Remove the built-in directives we don't want
# TODO: This hack can be removed once we refactor role and directive handling
docutils.parsers.rst.directives._directive_registry = {
    k: v
    for k, v in docutils.parsers.rst.directives._directive_registry.items()
    if k in {"replace", "unicode"}
}


@checked
@dataclass
class LegacyTabDefinition(nodes.Node):
    id: str
    name: Optional[str]
    content: str


@checked
@dataclass
class LegacyTabsDefinition(nodes.Node):
    hidden: Optional[bool]
    tabs: List[LegacyTabDefinition]


class directive_argument(docutils.nodes.General, docutils.nodes.TextElement):
    pass


class directive(docutils.nodes.General, docutils.nodes.Element):
    def __init__(self, name: str) -> None:
        super(directive, self).__init__()
        self["name"] = name


class code(docutils.nodes.General, docutils.nodes.FixedTextElement):
    pass


class role(docutils.nodes.Inline, docutils.nodes.Element):
    """Docutils node representing a role."""

    def __init__(
        self, name: str, lineno: int, label: Optional[str], target: Optional[str]
    ) -> None:
        super(role, self).__init__()
        self["name"] = name

        if label is not None:
            self["label"] = {
                "type": "text",
                "value": label,
                "position": {"start": {"line": lineno}},
            }

        if target is not None:
            self["target"] = target


def handle_role_text(
    typ: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: docutils.parsers.rst.states.Inliner,
    options: Dict[str, object] = {},
    content: List[object] = [],
) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.Node]]:
    """Handle roles with plain text content."""
    node = role(typ, lineno, text, None)
    return [node], []


def handle_role_explicit_title(
    typ: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: docutils.parsers.rst.states.Inliner,
    options: Dict[str, object] = {},
    content: List[object] = [],
) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.Node]]:
    """Handle link-like roles with a target and an optional title."""
    match = PAT_EXPLICIT_TILE.match(text)
    if match:
        node = role(typ, lineno, match["label"], match["target"])
    else:
        node = role(typ, lineno, None, text)

    return [node], []


class LinkRoleHandler:
    """Handle roles which generate a link from a template."""

    def __init__(self, url_template: str) -> None:
        self.url_template = url_template

    def __call__(
        self,
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        inliner: docutils.parsers.rst.states.Inliner,
        options: Dict[str, object] = {},
        content: List[object] = [],
    ) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.Node]]:
        match = PAT_EXPLICIT_TILE.match(text)
        label: Optional[str] = None
        if match:
            label, target = match["label"], match["target"]
        else:
            target = text

        url = self.url_template % target
        if not label:
            label = url
        node = docutils.nodes.reference(label, label, internal=False, refuri=url)
        return [node], []


def parse_linenos(term: str, max_val: int) -> List[Tuple[int, int]]:
    """Parse a comma-delimited list of line numbers and ranges."""
    results: List[Tuple[int, int]] = []
    for term in (term for term in term.split(",") if term.strip()):
        parts = term.split("-", 1)
        lower = int(parts[0])
        higher = int(parts[1]) if len(parts) == 2 else lower

        if (
            lower < 0
            or lower > max_val
            or higher < 0
            or higher > max_val
            or lower > higher
        ):
            raise ValueError(f"Invalid line number specification: {term}")

        results.append((lower, higher))

    return results


class BaseDocutilsDirective(docutils.parsers.rst.Directive):
    required_arguments = 0

    def run(self) -> List[docutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        node = directive(self.name)
        node.document = self.state.document
        node.source, node.line = source, line
        node["options"] = self.options
        self.add_name(node)

        # Parse the directive's argument. An argument spans from the 0th line to the first
        # non-option line; this is a heuristic that is not part of docutils, since docutils
        # requires each directive to define its syntax.
        if self.arguments and not self.arguments[0].startswith(":"):
            arg_lines = self.arguments[0].split("\n")
            if (
                len(arg_lines) > 1
                and not self.options
                and PAT_BLOCK_HAS_ARGUMENT.match(self.block_text)
            ):
                content_lines = prepare_viewlist(self.arguments[0])
                self.state.nested_parse(
                    docutils.statemachine.ViewList(
                        content_lines, source=self.arguments[0]
                    ),
                    self.state_machine.line_offset,
                    node,
                    match_titles=True,
                )
            else:
                argument_text = arg_lines[0]
                textnodes, messages = self.state.inline_text(argument_text, self.lineno)
                argument = directive_argument(argument_text, "", *textnodes)
                argument.document = self.state.document
                argument.source, argument.line = source, line
                node.append(argument)

        # Parse the content
        if self.name in {"include", "raw"}:
            raw = docutils.nodes.FixedTextElement()
            raw.document = self.state.document
            raw.source, raw.line = source, line
            node.append(raw)
        else:
            self.state.nested_parse(
                self.content, self.state_machine.line_offset, node, match_titles=True
            )

        return [node]


def prepare_viewlist(text: str, ignore: int = 1) -> List[str]:
    lines = docutils.statemachine.string2lines(
        text, tab_width=4, convert_whitespace=True
    )

    # Remove any leading blank lines.
    while lines and not lines[0]:
        lines.pop(0)

    # make sure there is an empty line at the end
    if lines and lines[-1]:
        lines.append("")

    return lines


class TabsDirective(BaseDocutilsDirective):
    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True
    option_spec = {"tabset": str, "hidden": util.option_bool}

    def run(self) -> List[docutils.nodes.Node]:
        # Transform the old YAML-based syntax into the new pure-rst syntax.
        # This heuristic guesses whether we have the old syntax or the NEW.
        if any(line == "tabs:" for line in self.content):
            parsed = load_yaml("\n".join(self.content))[0]
            try:
                loaded = check_type(LegacyTabsDefinition, parsed)
            except LoadError as err:
                line = self.lineno + getattr(err.bad_data, "_start_line", 0) + 1
                error_node = self.state.document.reporter.error(str(err), line=line)
                return [error_node]

            tabset = self.name.split("-", 1)[-1]
            node = directive("tabs")
            node.document = self.state.document
            source, node.line = self.state_machine.get_source_and_line(self.lineno)
            node.source = source
            self.add_name(node)

            options: Dict[str, object] = {}
            node["options"] = options
            if loaded.hidden:
                options["hidden"] = True

            if tabset and tabset != "tabs":
                options["tabset"] = tabset

            for child in loaded.tabs:
                node.append(self.make_tab_node(child.id, child.name, source, child))

            return [node]

        # The new syntax needs no special handling
        return super().run()

    def make_tab_node(
        self, tabid: str, title: Optional[str], source: str, child: LegacyTabDefinition
    ) -> docutils.nodes.Node:
        """Synthesize a new-style tab node out of a legacy (YAML) tab definition."""
        line = self.lineno + child.line

        node = directive("tab")
        node.document = self.state.document
        node.source = source
        node.line = line

        if title is not None:
            textnodes, messages = self.state.inline_text(title, line)
            argument = directive_argument(title, "", *textnodes)
            argument.document = self.state.document
            argument.source, argument.line = source, line
            node.append(argument)

        options: Dict[str, object] = {}
        node["options"] = options
        options["tabid"] = tabid

        content_lines = prepare_viewlist(child.content)
        self.state.nested_parse(
            docutils.statemachine.ViewList(content_lines, source=source),
            self.state_machine.line_offset,
            node,
            match_titles=True,
        )

        return node


class CodeDirective(docutils.parsers.rst.Directive):
    required_arguments = 1
    optional_arguments = 0
    has_content = True
    final_argument_whitespace = True
    option_spec = {
        "copyable": util.option_bool,
        "emphasize-lines": str,
        "class": str,
        "linenos": util.option_flag,
    }

    def run(self) -> List[docutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        copyable = "copyable" not in self.options or self.options["copyable"] == "true"

        try:
            n_lines = len(self.content)
            emphasize_lines = parse_linenos(
                self.options.get("emphasize-lines", ""), n_lines
            )
        except ValueError as err:
            error_node = self.state.document.reporter.error(str(err), line=self.lineno)
            return [error_node]

        value = "\n".join(self.content)
        node = code(value, value)
        node["name"] = "code"
        node["lang"] = self.arguments[0]
        node["copyable"] = copyable
        node["emphasize_lines"] = emphasize_lines
        node.document = self.state.document
        node.source, node.line = source, line
        return [node]


class NoTransformRstParser(docutils.parsers.rst.Parser):
    def get_transforms(self) -> List[object]:
        return []


class Visitor(Protocol):
    def __init__(
        self, project_root: Path, docpath: PurePath, document: docutils.nodes.document
    ) -> None:
        ...

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        ...

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        ...

    def add_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        ...


_V = TypeVar("_V", bound=Visitor)


def register_spec_with_docutils(spec: specparser.Spec) -> None:
    """Register all of the definitions in the spec with docutils."""
    from .legacy_guides import LegacyGuideDirective, LegacyGuideIndexDirective

    directives = list(spec.directive.items())
    roles = list(spec.role.items())

    # Define rstobjects
    for name, rst_object in spec.rstobject.items():
        directive = rst_object.create_directive()
        role = rst_object.create_role()
        directives.append((name, directive))
        roles.append((name, role))

    for name, directive in directives:
        # Skip abstract base directives
        if name.startswith("_"):
            continue

        # Tabs have special handling because of the need to support legacy syntax
        if name == "tabs" or name.startswith("tabs-"):
            docutils.parsers.rst.directives.register_directive(name, TabsDirective)
            continue

        options: Dict[str, object] = {
            option_name: spec.get_validator(option)
            for option_name, option in directive.options.items()
        }

        class DocutilsDirective(BaseDocutilsDirective):
            has_content = bool(directive.content_type)
            optional_arguments = 1 if directive.argument_type else 0
            final_argument_whitespace = True
            option_spec = options

        new_name = (
            "".join(e for e in name.title() if e.isalnum() or e == "_") + "Directive"
        )
        DocutilsDirective.__name__ = DocutilsDirective.__qualname__ = new_name
        docutils.parsers.rst.directives.register_directive(name, DocutilsDirective)

    # Some directives currently have special handling
    docutils.parsers.rst.directives.register_directive("code-block", CodeDirective)
    docutils.parsers.rst.directives.register_directive("code", CodeDirective)
    docutils.parsers.rst.directives.register_directive("sourcecode", CodeDirective)
    docutils.parsers.rst.directives.register_directive("guide", LegacyGuideDirective)
    docutils.parsers.rst.directives.register_directive(
        "guide-index", LegacyGuideIndexDirective
    )

    # Define roles
    for name, role_spec in roles:
        handler = None
        if not role_spec.type or role_spec.type == specparser.PrimitiveRoleType.text:
            handler = handle_role_text
        elif isinstance(role_spec.type, specparser.LinkRoleType):
            handler = LinkRoleHandler(role_spec.type.link)
        elif role_spec.type == specparser.PrimitiveRoleType.explicit_title:
            handler = handle_role_explicit_title

        if not handler:
            raise ValueError('Unknown role type "{}"'.format(role_spec.type))

        docutils.parsers.rst.roles.register_local_role(name, handler)


class Parser(Generic[_V]):
    __slots__ = ("project_config", "visitor_class")
    spec: Optional[specparser.Spec] = None

    def __init__(self, project_config: ProjectConfig, visitor_class: Type[_V]) -> None:
        self.project_config = project_config
        self.visitor_class = visitor_class

        if not self.spec:
            with PACKAGE_ROOT.joinpath("rstspec.toml").open(encoding="utf-8") as f:
                spec = Parser.spec = specparser.Spec.loads(f.read())
            register_spec_with_docutils(spec)

    def parse(self, path: Path, text: Optional[str]) -> Tuple[_V, str]:
        diagnostics: List[Diagnostic] = []
        if text is None:
            text, diagnostics = self.project_config.read(path)
        else:
            text, diagnostics = self.project_config.substitute(text)

        parser = NoTransformRstParser()
        settings = docutils.frontend.OptionParser(
            components=(docutils.parsers.rst.Parser,)
        ).get_default_values()
        settings.report_level = 10000
        settings.halt_level = 10000
        document = docutils.utils.new_document(str(path), settings)

        parser.parse(text, document)

        visitor = self.visitor_class(self.project_config.source_path, path, document)
        visitor.add_diagnostics(diagnostics)
        document.walkabout(visitor)
        return visitor, text

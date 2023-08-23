import dataclasses
import re
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from mimetypes import guess_type
from pathlib import PurePath
from typing import (
    AbstractSet,
    Any,
    Callable,
    DefaultDict,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from typing_extensions import Protocol

from . import n, specparser, tinydocutils, util
from .diagnostics import Diagnostic, IncorrectLinkSyntax, IncorrectMonospaceSyntax
from .flutter import LoadError, check_type, checked
from .gizaparser import nodes
from .gizaparser.parse import load_yaml
from .types import ProjectConfig

RoleHandlerType = Callable[
    [
        str,
        str,
        str,
        int,
        tinydocutils.states.Inliner,
        Dict[str, object],
        List[object],
    ],
    Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]],
]
PAT_EXPLICIT_TITLE = re.compile(
    r"^(?P<label>.*?)\s*(?<!\x00)<(?P<target>.*?)>$", re.DOTALL
)
PAT_WHITESPACE = re.compile(r"^\x20*")
PAT_BLOCK_HAS_ARGUMENT = re.compile(r"^\x20*\.\.\x20[^\s]+::\s*\S+")
PAT_OPTION = re.compile(r"((?:/|--|-|\+)?[^\s=]+)(=?\s*.*)")
PAT_ISO_8601 = re.compile(r"^([0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])$")
PAT_PARAMETERS = re.compile(r"\s*\(.*?\)\s*$")

#: Hard-coded sequence of domains in which to search for a directives
#: and roles if no domain is explicitly provided.. Eventually this should
#: not be hard-coded.
DOMAIN_RESOLUTION_SEQUENCE = ("mongodb", "std", "")

#: Handler function type for docutils roles
RoleHandler = Callable[..., Any]

# Docutils by default will move existing label names into a node key called "dupnames".
# We don't want it to do this: we just want docutils to be a dumb parser, since we handle
# references and such in our own logic.
tinydocutils.nodes.dupname = lambda node, name: None


def unescape_backslashes(text: str) -> str:
    """docutils replaces backslashes with null characters. Deal with this in
    a fairly inane way that matches how backslashes seem to be used in our
    corpus."""
    return (
        text.replace("\x00<", "<")
        .replace("\x00>", ">")
        .replace('\x00"', '"')
        .replace("\x00", "\\")
    )


def parse_explicit_title(text: str) -> Tuple[str, Optional[str]]:
    match = PAT_EXPLICIT_TITLE.match(text)

    if match:
        return unescape_backslashes(match["target"]), unescape_backslashes(
            match["label"]
        )

    return (unescape_backslashes(text), None)


def strip_parameters(target: str) -> str:
    """Remove trailing ALGOL-style parameters from a target name;
    e.g. foo(bar, baz) -> foo."""
    match = PAT_PARAMETERS.search(target)
    if not match:
        return target

    starting_index = match.start()
    if starting_index == -1:
        return target

    return target[0:starting_index]


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


@checked
@dataclass
class CardDefinition(nodes.Node):
    """Represents a Card within a CardGroup.

    Attributes:
        id          Unique identifier for the card, to be used as an anchor tag
        headline    Card title heading
        image       Path to an image used as the body of the card
        link        URL to be linked to by the card
    """

    id: str
    headline: str
    image: str
    link: str


@checked
@dataclass
class CardGroupDefinition(nodes.Node):
    """A list of cards as specified in CardDefinition"""

    cards: List[CardDefinition]


class directive_argument(tinydocutils.nodes.General, tinydocutils.nodes.TextElement):
    pass


class target_identifier(tinydocutils.nodes.Inline, tinydocutils.nodes.TextElement):
    """Docutils node representing the title which should be used for refs to this node's
    parent target, if no explicit title is given."""

    pass


class directive(tinydocutils.nodes.General, tinydocutils.nodes.Element):
    def __init__(self, domain: str, name: str) -> None:
        super(directive, self).__init__()
        self["domain"] = domain
        self["name"] = name


class target_directive(directive):
    """Docutils node representing a named target which can be referenced by the ref_role node."""

    pass


class code(tinydocutils.nodes.General, tinydocutils.nodes.FixedTextElement):
    pass


class role(tinydocutils.nodes.Inline, tinydocutils.nodes.Element):
    """Docutils node representing a role."""

    def __init__(
        self, domain: str, name: str, lineno: int, target: Optional[str]
    ) -> None:
        super(role, self).__init__()
        self["domain"] = domain
        self["name"] = name

        if target is not None:
            self["target"] = target


class ref_role(role):
    """Docutils node representing a reference to a reStructuredText target."""

    pass


class snooty_diagnostic(tinydocutils.nodes.Element):
    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__("")
        self["diagnostic"] = diagnostic


def handle_role_null(
    typ: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: tinydocutils.states.Inliner,
    options: Dict[str, object] = {},
    content: List[object] = [],
) -> Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]]:
    """Handle unnamed roles by raising a warning."""
    target, label = parse_explicit_title(text)
    if label is not None:
        diagnostic: Diagnostic = IncorrectLinkSyntax((label, target), lineno)
    else:
        diagnostic = IncorrectMonospaceSyntax(target, lineno)

    return (
        [
            tinydocutils.nodes.literal(rawtext, text),
            snooty_diagnostic(diagnostic),
        ],
        [],
    )


class TextRoleHandler:
    """Handle roles with plain text content."""

    def __init__(self, domain: str) -> None:
        self.domain = domain

    def __call__(
        self,
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        inliner: tinydocutils.states.Inliner,
        options: Dict[str, object] = {},
        content: List[object] = [],
    ) -> Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]]:
        node = role(self.domain, typ, lineno, None)
        node.append(tinydocutils.nodes.Text(text))
        return [node], []


class ExplicitTitleRoleHandler:
    """Handle link-like roles with a target and an optional title."""

    def __init__(self, domain: str) -> None:
        self.domain = domain

    def __call__(
        self,
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        inliner: tinydocutils.states.Inliner,
        options: Dict[str, object] = {},
        content: List[object] = [],
    ) -> Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]]:
        target, label = parse_explicit_title(text)
        if label is not None:
            node = role(self.domain, typ, lineno, target)
            node.append(tinydocutils.nodes.Text(label))
        else:
            node = role(self.domain, typ, lineno, target)

        return [node], []


FORMATTING_MAP = {
    specparser.FormattingType.strong: tinydocutils.nodes.strong,
    specparser.FormattingType.emphasis: tinydocutils.nodes.emphasis,
    specparser.FormattingType.monospace: tinydocutils.nodes.literal,
}


def format_node(
    node: tinydocutils.nodes.ConcreteNode,
    formatting: AbstractSet[specparser.FormattingType],
) -> tinydocutils.nodes.ConcreteNode:
    """Format a docutils node with a set of inline formatting roles."""

    for hint in formatting:
        node = FORMATTING_MAP[hint]("", "", *([node] if node else []))

    return node


def layer_formatting(
    formatting: AbstractSet[specparser.FormattingType],
) -> Optional[tinydocutils.nodes.ConcreteNode]:
    """Create a nested sequence of formatting nodes."""
    node = None
    for hint in formatting:
        node = FORMATTING_MAP[hint]("", "", *([node] if node else []))

    return node


@dataclass
class RefRoleHandler:
    domain: str
    name: str
    prefix: Optional[str]
    target_type: specparser.TargetType
    format: AbstractSet[specparser.FormattingType]

    def __call__(
        self,
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        inliner: tinydocutils.states.Inliner,
        options: Dict[str, object] = {},
        content: List[object] = [],
    ) -> Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]]:
        target, label = parse_explicit_title(text)

        flag = ""
        if target.startswith("~") or target.startswith("!"):
            flag = target[0]
            target = target[1:]

        # Add the giza prefix/tag, if necessary
        if self.prefix and not target.startswith(self.prefix):
            target = f"{self.prefix}.{target}"

        if self.target_type == specparser.TargetType.callable:
            target = strip_parameters(target)
        elif self.target_type == specparser.TargetType.cmdline_option:
            if not label:
                label = target

            target = ".".join(target.rsplit(None, 1))

        node: tinydocutils.nodes.Element = ref_role(
            self.domain, self.name, lineno, target
        )

        label_node: Optional[tinydocutils.nodes.ConcreteNode] = None

        if label:
            label_node = tinydocutils.nodes.Text(label)
            if self.format:
                label_node = format_node(label_node, self.format)
        else:
            # Empty formatting nodes provide a skeleton into which the postprocessor
            # can inject the needed title.
            label_node = layer_formatting(self.format)

        if label_node:
            node.append(label_node)

        if flag:
            node["flag"] = flag

        return [node], []


class LinkRoleHandler:
    """Handle roles which generate a link from a template."""

    def __init__(
        self,
        url_template: str,
        ensure_trailing_slash: bool,
        format: AbstractSet[specparser.FormattingType],
    ) -> None:
        self.url_template = url_template
        self.format = format
        self.ensure_trailing_slash = ensure_trailing_slash

    def __call__(
        self,
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        inliner: tinydocutils.states.Inliner,
        options: Dict[str, object] = {},
        content: List[object] = [],
    ) -> Tuple[List[tinydocutils.nodes.Node], List[tinydocutils.nodes.Node]]:
        target, label = parse_explicit_title(text)

        if typ == "rfc" and not label:
            label = "".join(["RFC-", target])

        url = self.url_template % target
        if self.ensure_trailing_slash:
            url = self.assert_trailing_slash(url)
        if not label:
            label = target
        node: tinydocutils.nodes.ConcreteNode = tinydocutils.nodes.reference(
            label,
            label,
            internal=False,
            refuri=url,
        )

        if self.format:
            node = format_node(node, self.format)

        return [node], []

    def assert_trailing_slash(self, url: str) -> str:
        """Append trailing slash to urls while preserving hashes and query params"""
        if guess_type(url) != (None, None):
            return url
        return re.sub(r"\/?(\?|#|$)", r"/\1", url, 1)


def parse_linenos(term: str, max_val: int) -> List[Tuple[int, int]]:
    """Parse a comma-delimited list of line numbers and ranges."""
    results: List[Tuple[int, int]] = []
    if not term.strip():
        return []
    for term in term.strip().split(","):
        parts = term.split("-", 1)
        lower = int(parts[0])
        higher = int(parts[1]) if len(parts) == 2 else lower
        if lower < 0 or higher < 0:
            raise ValueError(
                f"Invalid line number specification: {term}. Expects non-negative integers."
            )
        elif lower > max_val or higher > max_val:
            raise ValueError(
                f"Invalid line number specification: {term}. Expects maximum value of {max_val}."
            )
        elif lower > higher:
            raise ValueError(
                f"Invalid line number specification: {term}. Expects {lower} < {higher}."
            )

        results.append((lower, higher))

    return results


class BaseDocutilsDirective(tinydocutils.directives.Directive):
    directive_spec: specparser.Directive
    required_arguments = 0

    def run(self) -> List[tinydocutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)

        rstobject_spec = self.directive_spec.rstobject
        constructor = target_directive if rstobject_spec else directive
        node = constructor(self.directive_spec.domain or "", self.name)
        node.document = self.state.document
        node.source, node.line = source, line
        node["options"] = self.options
        self.add_name(node)

        # Check for required options
        option_names = set(self.options.keys())
        missing_options = self.directive_spec.required_options - option_names
        if missing_options:
            missing_option_names = ", ".join(missing_options)
            pluralization = "s" if len(missing_option_names) > 1 else ""
            node.append(
                self.state.document.reporter.error(
                    f'"{self.name}" requires the following option{pluralization}: {missing_option_names}',
                    line=line,
                )
            )

        # If directive is deprecated, warn
        if self.directive_spec.deprecated == True:
            node.append(
                self.state.document.reporter.warning(
                    f'Directive "{self.name}" has been deprecated', line=line
                )
            )

        # If this is an rstobject, we need to generate a target property
        if rstobject_spec is not None:
            prefix = rstobject_spec.prefix + "." if rstobject_spec.prefix else ""

            if rstobject_spec.type == specparser.TargetType.plain:
                targets: Sequence[Tuple[str, str]] = (
                    ((prefix + self.arguments[0], self.arguments[0]),)
                    if rstobject_spec.prefix
                    else ((self.arguments[0], self.arguments[0]),)
                )
            elif rstobject_spec.type == specparser.TargetType.callable:
                stripped = strip_parameters(self.arguments[0])
                targets = ((prefix + stripped, stripped + "()"),)
            elif rstobject_spec.type == specparser.TargetType.cmdline_option:
                targets = []
                for arg_id in self.parse_options(self.arguments[0]):
                    if isinstance(arg_id, ValueError):
                        node.append(
                            self.state.document.reporter.error(str(arg_id), line=line)
                        )
                        continue
                    targets.append((prefix + arg_id, arg_id))

            # title is the node that should be presented at this point in the doctree
            title_node: tinydocutils.nodes.ConcreteNode = tinydocutils.nodes.Text(
                self.arguments[0]
            )
            if rstobject_spec.format is not None:
                title_node = format_node(title_node, rstobject_spec.format)
            node.append(directive_argument(self.arguments[0], "", title_node))

            for target_id, target_title in targets:
                identifier_node = target_identifier()
                identifier_node["ids"] = [target_id]
                identifier_node.append(tinydocutils.nodes.Text(target_title))
                node.append(identifier_node)

            # Append list of supported fields
            node["fields"] = rstobject_spec.fields
        elif self.name in {"pubdate", "updated-date"}:
            date = self.parse_date(self.arguments[0])
            if isinstance(date, ValueError):
                # Throw error and set date field to None
                err = "Expected ISO 8061 date format (YYYY-MM-DD)"
                node.append(
                    self.state.document.reporter.error(f"{err}: {str(date)}", line=line)
                )
            else:
                node["date"] = date
        else:
            assert source is not None
            self.parse_argument(node, source, line)

        # Parse the content
        self.state.nested_parse(
            self.content, self.content_offset, node, match_titles=True
        )

        return [node]

    def parse_argument(self, node: directive, source: str, line: int) -> None:
        """Parse the directive's argument.

        An argument spans from the 0th line to the first non-option line; this
        is a heuristic that is not part of docutils, since docutils requires
        each directive to define its syntax.
        """
        if not self.arguments or self.arguments[0].startswith(":"):
            return

        arg_lines = self.arguments[0].split("\n")
        if (
            len(arg_lines) > 1
            and not self.options
            and PAT_BLOCK_HAS_ARGUMENT.match(self.block_text)
        ):
            content_lines = prepare_viewlist(self.arguments[0])
            self.state.nested_parse(
                tinydocutils.statemachine.StringList(
                    content_lines, source=self.arguments[0]
                ),
                self.content_offset,
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

    def add_name(self, node: tinydocutils.nodes.Node) -> None:
        """Docutils by default will, if a "name" option is given to a directive,
        change the shape of the node. We don't want that and it muddles up higher layers.
        """
        pass

    @staticmethod
    def parse_options(option: str) -> Iterable[Union[str, ValueError]]:
        all_parts = (part.strip() for part in option.split(", "))
        for part in all_parts:
            match = PAT_OPTION.match(part)
            if match is None:
                yield ValueError(part)
                continue

            yield match.group(1)

    @staticmethod
    def parse_date(date: str) -> Union[str, ValueError]:
        match = PAT_ISO_8601.match(date)
        if match:
            return date
        else:
            return ValueError(date)


def prepare_viewlist(text: str, ignore: int = 1) -> List[str]:
    lines = tinydocutils.statemachine.string2lines(
        text, tab_width=4, convert_whitespace=True
    )

    # Remove any leading blank lines.
    while lines and not lines[0]:
        lines.pop(0)

    # make sure there is an empty line at the end
    if lines and lines[-1]:
        lines.append("")

    return lines


class BaseCardGroupDirective(BaseDocutilsDirective):
    def run(self) -> List[tinydocutils.nodes.Node]:
        parsed, diagnostic = load_yaml(None, "\n".join(self.content))
        if diagnostic is not None:
            diagnostic.start = (diagnostic.start[0] + self.lineno, diagnostic.start[1])
            return [snooty_diagnostic(diagnostic)]

        try:
            loaded = check_type(CardGroupDefinition, parsed[0])
        except LoadError as err:
            line = self.lineno + getattr(err.bad_data, "_start_line", 0) + 1
            error_node = self.state.document.reporter.error(str(err), line=line)
            return [error_node]
        except IndexError:
            loaded = CardGroupDefinition([])

        node = directive("", "card-group")
        node.document = self.state.document
        source, node.line = self.state_machine.get_source_and_line(self.lineno)
        node.source = source
        self.add_name(node)

        options: Dict[str, object] = {}
        node["options"] = options
        # Default to card type "small" if type is not specified
        options["type"] = self.options.get("type", "small")

        assert source is not None

        for child in loaded.cards:
            node.append(self.make_card_node(source, child))

        return [node]

    def make_card_node(self, source: str, child: CardDefinition) -> directive:
        """Synthesize a new-style tab node out of a legacy (YAML) tab definition."""
        line = self.lineno + child.line

        # Give the node a unique name, as "card" is used by landing page cards in docs-tutorials.
        node = directive("", "cardgroup-card")
        node.document = self.state.document
        node.source = source
        node.line = line

        options: Dict[str, object] = {}
        node["options"] = options
        options["cardid"] = child.id
        options["headline"] = child.headline
        options["image"] = child.image
        options["link"] = child.link

        return node


class BaseTabsDirective(BaseDocutilsDirective):
    def run(self) -> List[tinydocutils.nodes.Node]:
        # Support the old-style tabset definition where the tabset is embedded in the
        # directive's name.
        if "tabset" in self.options:
            tabset = self.options["tabset"]
        else:
            tabset = self.name.split("-", 1)[-1]

        if tabset in ("tabs", ""):
            tabset = None

        # Transform the old YAML-based syntax into the new pure-rst syntax.
        # This heuristic guesses whether we have the old syntax or the NEW.
        if any(line == "tabs:" for line in self.content):
            parsed, diagnostic = load_yaml(None, "\n".join(self.content))

            if diagnostic is not None:
                diagnostic.start = (
                    diagnostic.start[0] + self.lineno,
                    diagnostic.start[1],
                )
                return [snooty_diagnostic(diagnostic)]

            try:
                first_parsed = parsed[0]
            except IndexError:
                error_node = self.state.document.reporter.error(
                    "At least one tab required", line=self.lineno
                )
                return [error_node]

            try:
                loaded = check_type(LegacyTabsDefinition, first_parsed)
            except LoadError as err:
                line = self.lineno + getattr(err.bad_data, "_start_line", 0) + 1
                error_node = self.state.document.reporter.error(str(err), line=line)
                return [error_node]

            node = directive("", "tabs")
            node.document = self.state.document
            source, node.line = self.state_machine.get_source_and_line(self.lineno)
            node.source = source
            self.add_name(node)

            options: Dict[str, object] = {}
            node["options"] = options
            if loaded.hidden:
                options["hidden"] = True

            if tabset:
                options["tabset"] = tabset

            assert source is not None

            for child in loaded.tabs:
                node.append(self.make_tab_node(child.id, child.name, source, child))

            return [node]

        # these directives should not be treated like a tabs directive
        if self.name in {"tabs-pillstrip", "tabs-selector"}:
            return super().run()

        # The new syntax needs no special handling beyond a little fixing up
        # the legacy tabset system.
        if self.name != "tabs":
            self.name = "tabs"
        if tabset:
            self.options["tabset"] = tabset
        return super().run()

    def make_tab_node(
        self, tabid: str, title: Optional[str], source: str, child: LegacyTabDefinition
    ) -> directive:
        """Synthesize a new-style tab node out of a legacy (YAML) tab definition."""
        line = self.lineno + child.line

        node = directive("", "tab")
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
            tinydocutils.statemachine.StringList(content_lines, source=source),
            self.content_offset,
            node,
            match_titles=True,
        )

        return node


class BaseCodeDirective(tinydocutils.directives.Directive):
    def run(self) -> List[tinydocutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        copyable = "copyable" not in self.options or self.options["copyable"]
        linenos = "linenos" in self.options

        try:
            n_lines = len(self.content)
            emphasize_lines_options = self.options.get("emphasize-lines", "")
            assert isinstance(emphasize_lines_options, str)
            emphasize_lines = parse_linenos(emphasize_lines_options, n_lines)
        except ValueError as err:
            error_node = self.state.document.reporter.error(str(err), line=self.lineno)
            return [error_node]

        value = "\n".join(self.content)
        node = code(value, value)
        node["name"] = "code"
        if self.arguments:
            node["lang"] = self.arguments[0]
        if "caption" in self.options:
            node["caption"] = self.options["caption"]
        node["copyable"] = copyable
        node["emphasize_lines"] = emphasize_lines
        node["linenos"] = linenos
        if "source" in self.options:
            node["source"] = self.options["source"]
        node.document = self.state.document
        node.source, node.line = source, line
        return [node]


class BaseCodeIODirective(tinydocutils.directives.Directive):
    """Special handling for code input/output directives.

    These directives can either take in a filepath or raw code content. If a filepath
    is present, this should be included in the `argument` field of the AST. If raw code
    content is present, it should become the value of the child Code node.
    """

    optional_arguments = 1

    def run(self) -> List[tinydocutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        copyable = "copyable" not in self.options or self.options["copyable"]
        linenos = "linenos" in self.options

        node = directive("", self.name)
        node.document = self.state.document
        node.source, node.line = source, line
        node["options"] = self.options

        if self.arguments:
            title_node = tinydocutils.nodes.Text(self.arguments[0])
            node.append(directive_argument(self.arguments[0], "", title_node))
        else:
            try:
                n_lines = len(self.content)
                emphasize_lines_options = self.options.get("emphasize-lines", "")
                assert isinstance(emphasize_lines_options, str)
                emphasize_lines = parse_linenos(emphasize_lines_options, n_lines)
            except ValueError as err:
                error_node = self.state.document.reporter.error(
                    str(err), line=self.lineno
                )
                return [error_node]

            value = "\n".join(self.content)
            child_code = code(value, value)
            child_code["name"] = "code"
            child_code["emphasize_lines"] = emphasize_lines
            child_code["linenos"] = linenos
            child_code["copyable"] = copyable
            child_code["source"] = "test"
            if "source" in self.options:
                child_code["source"] = self.options["source"]

            child_code.document = self.state.document
            child_code.source, node.line = source, line
            node.append(child_code)

        return [node]


class BaseVersionDirective(tinydocutils.directives.Directive):
    """Special handling for version change directives.

    These directives include one required argument and an optional argument on the next line.
    We need to ensure that these are both included in the `argument` field of the AST, and that
    subsequent indented directives are included as children of the node.
    """

    required_arguments = 1
    optional_arguments = 1

    def run(self) -> List[tinydocutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        node = directive("", self.name)
        node.document = self.state.document
        node.source, node.line = source, line
        node["options"] = self.options

        if self.arguments:
            arguments = " ".join(self.arguments).split(None, 1)
            textnodes: List[tinydocutils.nodes.ConcreteNode] = []
            for argument_text in arguments:
                text, messages = self.state.inline_text(argument_text, self.lineno)
                textnodes.extend(text)
            argument = directive_argument("", "", *textnodes)
            argument.document = self.state.document
            argument.source, argument.line = source, line
            node.append(argument)

        if self.content:
            self.state.nested_parse(
                self.content, self.content_offset, node, match_titles=True
            )

        return [node]


class DeprecatedVersionDirective(BaseVersionDirective):
    """Variant of BaseVersionDirective for the deprecated directive, which does not
    require an argument."""

    required_arguments = 0
    optional_arguments = 1


class BaseTocTreeDirective(tinydocutils.directives.Directive):
    """Special handling for toctree directives.

    Produces a node that includes an `entries` property, represented as a list of objects. Each entry in entries includes:
    - slug OR url: a string representing the absolute url or path of the page to navigate to
    - [optional] title: a string representing the title to use in the TOC sidebar
    """

    final_argument_whitespace = True

    def run(self) -> List[tinydocutils.nodes.Node]:
        source, line = self.state_machine.get_source_and_line(self.lineno)
        node = directive("", self.name)
        node.document = self.state.document
        node.source, node.line = source, line
        node["options"] = self.options

        entries: List[n.TocTreeDirectiveEntry] = []
        errors: List[tinydocutils.nodes.Node] = []

        assert source is not None

        for child in self.content:
            entry, err = self.make_toc_entry(source, child)
            errors.extend(err)
            if entry:
                entries.append(entry)
        node["entries"] = entries

        return [node, *errors]

    def make_toc_entry(
        self, source: str, child: str
    ) -> Tuple[Optional[n.TocTreeDirectiveEntry], List[tinydocutils.nodes.Node]]:
        """Parse entry for either url or slug and optional title"""
        match = PAT_EXPLICIT_TITLE.match(child)
        title: Optional[str] = None
        url: Optional[str] = None
        slug: Optional[str] = None
        ref_project: Optional[str] = None
        if match:
            title, target = match["label"], match["target"]
            # pipelines denote project reference
            if target.startswith("|") and target.endswith("|"):
                ref_project = target[1:-1]
                target = None
        else:
            target = child

        if not title and (util.PAT_URI.match(target) or ref_project):
            # If entry is surrounded by <> tags, assume it is a URL and log an error.
            err = "toctree nodes with URLs or project references must include titles"
            error_node = self.state.document.reporter.error(err, line=self.lineno)
            return None, [error_node]

        parsed = urllib.parse.urlparse(target)
        if parsed.scheme:
            url = target
        else:
            slug = target
        return n.TocTreeDirectiveEntry(title, url, slug, ref_project), []


class NoTransformRstParser(tinydocutils.Parser):
    def get_transforms(self) -> List[object]:
        return []


class Visitor(Protocol):
    def __init__(
        self,
        project_config: ProjectConfig,
        docpath: PurePath,
        document: tinydocutils.nodes.document,
    ) -> None:
        ...

    def dispatch_visit(self, node: tinydocutils.nodes.Node) -> None:
        ...

    def dispatch_departure(self, node: tinydocutils.nodes.Node) -> None:
        ...

    def add_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        ...


_V = TypeVar("_V", bound=Visitor, covariant=True)


@dataclass
class Domain:
    directives: Dict[str, Type[Any]] = field(default_factory=dict)
    roles: Dict[str, RoleHandler] = field(default_factory=dict)


class Registry:
    @dataclass
    class Builder:
        domains: DefaultDict[str, Domain] = field(
            default_factory=lambda: defaultdict(Domain)
        )

        def add_directive(self, name: str, directive: Type[Any]) -> None:
            domain, name = util.split_domain(name)
            self.domains[domain].directives[name] = directive

        def add_role(self, name: str, role: RoleHandler) -> None:
            domain, name = util.split_domain(name)
            self.domains[domain].roles[name] = role

        def build(self, default_domain: Optional[str]) -> "Registry":
            return Registry(default_domain, self.domains)

    # This is effectively an LRU cache of size 1
    CURRENT_REGISTRY: Optional[Tuple[Optional[str], "Registry"]] = None

    def __init__(
        self, default_domain: Optional[str], domains: Dict[str, Domain]
    ) -> None:
        self.default_domain = default_domain
        self.domains = domains

        name_sequence: Tuple[str, ...] = DOMAIN_RESOLUTION_SEQUENCE
        if default_domain is not None:
            name_sequence = (default_domain, *name_sequence)
        self.domain_sequence = [
            self.domains[domain_name]
            for domain_name in name_sequence
            if domain_name in self.domains
        ]

    def lookup_directive(
        self,
        directive_name: str,
        document: tinydocutils.nodes.document,
    ) -> Optional[Type[tinydocutils.directives.Directive]]:
        # Remove the built-in directives we don't want
        domain_name, directive_name = util.split_domain(directive_name)
        if domain_name:
            return self.domains[domain_name].directives.get(directive_name, None)

        for domain in self.domain_sequence:
            if directive_name in domain.directives:
                return domain.directives.get(directive_name, None)

        return None

    def lookup_role(
        self, role_name: str, lineno: int, reporter: tinydocutils.nodes.Reporter
    ) -> Tuple[Optional[RoleHandler], List[tinydocutils.nodes.system_message]]:
        domain_name, role_name = util.split_domain(role_name)
        if domain_name:
            return self.domains[domain_name].roles.get(role_name, None), []

        for domain in self.domain_sequence:
            if role_name in domain.roles:
                return domain.roles.get(role_name, None), []

        return None, []

    def activate(self) -> None:
        """Unfortunately, the docutils API uses global state for dispatching directives
        and roles. Bind the docutils dispatchers to this registry."""
        tinydocutils.directives.directive = self.lookup_directive
        tinydocutils.roles.role = self.lookup_role

    @classmethod
    def get(cls, default_domain: Optional[str]) -> "Registry":
        if (
            cls.CURRENT_REGISTRY is not None
            and cls.CURRENT_REGISTRY[0] == default_domain
        ):
            return cls.CURRENT_REGISTRY[1]

        registry = register_spec_with_docutils(specparser.Spec.get(), default_domain)
        cls.CURRENT_REGISTRY = (default_domain, registry)
        return registry


SPECIAL_DIRECTIVE_HANDLERS: Dict[str, Type[tinydocutils.directives.Directive]] = {
    "code-block": BaseCodeDirective,
    "code": BaseCodeDirective,
    "input": BaseCodeIODirective,
    "output": BaseCodeIODirective,
    "sourcecode": BaseCodeDirective,
    "versionadded": BaseVersionDirective,
    "versionchanged": BaseVersionDirective,
    "deprecated": DeprecatedVersionDirective,
    "card-group": BaseCardGroupDirective,
    "toctree": BaseTocTreeDirective,
}


def make_docutils_directive_handler(
    directive: specparser.Directive,
    base_class: Type[tinydocutils.directives.Directive],
    name: str,
    options: Dict[str, object],
) -> Type[tinydocutils.directives.Directive]:
    optional_args = 0
    required_args = 0

    argument_type = directive.argument_type
    if argument_type:
        if (
            isinstance(argument_type, specparser.DirectiveOption)
            and argument_type.required
        ):
            required_args = 1
        else:
            optional_args = 1

    class DocutilsDirective(base_class):  # type: ignore
        directive_spec = directive
        has_content = bool(directive.content_type)
        optional_arguments = optional_args
        required_arguments = required_args
        final_argument_whitespace = True
        option_spec = options

    new_name = "".join(e for e in name.title() if e.isalnum() or e == "_") + "Directive"
    DocutilsDirective.__name__ = DocutilsDirective.__qualname__ = new_name
    return DocutilsDirective


def register_spec_with_docutils(
    spec: specparser.Spec, default_domain: Optional[str]
) -> Registry:
    """Register all of the definitions in the spec with docutils, overwriting the previous
    call to this function. This function should only be called once in the
    process lifecycle."""

    builder = Registry.Builder()
    directives = list(spec.directive.items())
    roles = list(spec.role.items())

    # Define rstobjects
    for name, rst_object in spec.rstobject.items():
        directive = rst_object.create_directive()
        directives.append((name, directive))
        role = rst_object.create_role()
        roles.append((name, role))

    for name, directive in directives:
        # Skip abstract base directives
        if name.startswith("_"):
            continue

        options: Dict[str, object] = {
            option_name: spec.get_validator(option)
            for option_name, option in directive.options.items()
        }

        base_class: Any = BaseDocutilsDirective

        # Tabs have special handling because of the need to support legacy syntax
        if name == "tabs":
            base_class = BaseTabsDirective
        elif name in SPECIAL_DIRECTIVE_HANDLERS:
            base_class = SPECIAL_DIRECTIVE_HANDLERS[name]

        DocutilsDirective = make_docutils_directive_handler(
            directive, base_class, name, options
        )
        builder.add_directive(name, DocutilsDirective)

    # reference tabs directive declaration as first step in registering tabs-* with docutils
    tabs_directive = spec.directive["tabs"]

    # Define tabsets
    for name in spec.tabs:
        tabs_base_class: Any = BaseTabsDirective
        tabs_name = "tabs-" + name

        # copy and modify the tabs directive to update its name to match the deprecated tabs-* naming convention
        modified_tabs_directive = dataclasses.replace(tabs_directive, name=tabs_name)

        tabs_options: Dict[str, object] = {
            option_name: spec.get_validator(option)
            for option_name, option in tabs_directive.options.items()
        }

        DocutilsDirective = make_docutils_directive_handler(
            modified_tabs_directive, tabs_base_class, "tabs", tabs_options
        )

        builder.add_directive(tabs_name, DocutilsDirective)

    # Docutils builtins
    builder.add_directive("unicode", tinydocutils.directives.Unicode)
    builder.add_directive("replace", tinydocutils.directives.Replace)

    # Define roles
    builder.add_role("", handle_role_null)
    for name, role_spec in roles:
        handler: Optional[RoleHandlerType] = None
        domain = role_spec.domain or ""
        if not role_spec.type or role_spec.type == specparser.PrimitiveRoleType.text:
            handler = TextRoleHandler(domain)
        elif isinstance(role_spec.type, specparser.LinkRoleType):
            handler = LinkRoleHandler(
                role_spec.type.link,
                role_spec.type.ensure_trailing_slash == True,
                role_spec.type.format,
            )
        elif isinstance(role_spec.type, specparser.RefRoleType):
            handler = RefRoleHandler(
                role_spec.type.domain or domain,
                role_spec.type.name,
                role_spec.type.tag,
                role_spec.rstobject.type
                if role_spec.rstobject
                else specparser.TargetType.plain,
                role_spec.type.format,
            )
        elif role_spec.type == specparser.PrimitiveRoleType.explicit_title:
            handler = ExplicitTitleRoleHandler(domain)

        if not handler:
            raise ValueError('Unknown role type "{}"'.format(role_spec.type))

        builder.add_role(name, handler)

    return builder.build(default_domain)


class Parser(Generic[_V]):
    __slots__ = ("project_config", "visitor_class")

    def __init__(self, project_config: ProjectConfig, visitor_class: Type[_V]) -> None:
        self.project_config = project_config
        self.visitor_class = visitor_class

    def parse(self, path: n.FileId, text: Optional[str]) -> Tuple[_V, str]:
        Registry.get(self.project_config.default_domain).activate()

        diagnostics: List[Diagnostic] = []
        text, diagnostics = self.project_config.read(path, text)

        parser = NoTransformRstParser()
        settings = tinydocutils.frontend.OptionParser(
            components=(tinydocutils.Parser,)
        ).get_default_values()
        settings.report_level = 10000
        settings.halt_level = 10000
        document = tinydocutils.nodes.new_document(str(path), settings)

        parser.parse(text, document)

        assert isinstance(path, n.FileId)
        visitor = self.visitor_class(self.project_config, path, document)
        visitor.add_diagnostics(diagnostics)
        document.walkabout(visitor)
        return visitor, text

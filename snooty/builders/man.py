import io
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Iterable, List, Union, cast

from .. import n
from ..page import Page
from ..types import FileId

logger = logging.getLogger(__name__)


def troff_escape(value: str) -> str:
    """Escape values that troff may interpret."""
    value = value.replace(r"\\", r"\e")
    replace_pairs = [
        ("-", r"\-"),
        (r"'", r"\(aq"),
        ("´", r"\'"),
        ("`", r"\(ga"),
    ]

    for (in_char, out_markup) in replace_pairs:
        value = value.replace(in_char, out_markup)

    # prevent interpretation of "." at line start
    if value.startswith("."):
        return r"\&" + value

    return value


@dataclass
class ManNode:
    """An intermediate representation node that acts as a middle step
    between the Snooty AST and a troff document."""

    class ElementType(Enum):
        MANPAGE = auto()
        SECTION = auto()
        PARAGRAPH = auto()
        URL = auto()
        STRONG = auto()
        EMPHASIS = auto()
        LIST = auto()
        LIST_ITEM = auto()
        TEXT = auto()
        INDENT = auto()
        PREFORMATTED = auto()

    element: ElementType
    children: Union[str, List["ManNode"]]
    attributes: Dict[str, str] = field(default_factory=dict)

    def to_troff(self) -> str:
        """Transform this node into a troff document string."""
        handler = TroffNodeHandler()

        def handle_node(node: "ManNode") -> None:
            """Call relevant handlers in TroffNodeHandler for a given node."""
            handler.handle_start(node)
            if isinstance(node.children, str):
                assert node.element in {
                    self.ElementType.TEXT,
                    self.ElementType.PREFORMATTED,
                }
                handler.handle_text(node.children)
            else:
                for child in node.children:
                    handle_node(child)
            handler.handle_end(node)

        handle_node(self)
        return handler.output.getvalue()


class Formatting(Enum):
    BOLD = auto()
    EMPHASIS = auto()


class TroffNodeHandler:
    def __init__(self) -> None:
        self.text_buffer = io.StringIO()
        self.output = io.StringIO()
        self.formatting_stack: List[Formatting] = []
        self.list_stack: List[str] = []
        self.section_depth = 0

        self.need_paragraph_splitter = False
        self.trailing_newline = True

    def macro(self, name: str, arg: str = "") -> None:
        """Flush any pending text, and write out a troff macro expression."""
        self.flush()
        if not self.trailing_newline:
            self.output.write("\n")
        self.output.write(f".{name}{' ' + arg if arg else ''}\n")
        self.trailing_newline = True

    def write_raw(self, raw: str) -> None:
        if not raw:
            return

        self.output.write(raw)
        self.trailing_newline = raw.endswith("\n")

    def flush(self) -> None:
        self.write_raw(self.text_buffer.getvalue())
        self.text_buffer = io.StringIO()

    def handle_start(self, node: ManNode) -> None:
        if node.element in {
            ManNode.ElementType.PARAGRAPH,
            ManNode.ElementType.PREFORMATTED,
        }:
            if self.need_paragraph_splitter:
                if self.list_stack:
                    self.macro("IP")
                else:
                    self.macro("PP")

        if node.element is ManNode.ElementType.MANPAGE:
            self.macro("TH", f"{node.attributes['name']} {node.attributes['section']}")
        elif node.element is ManNode.ElementType.SECTION:
            self.section_depth += 1
            macro_name = "SH" if self.section_depth <= 2 else "SS"
            self.macro(macro_name, node.attributes["name"].upper())
        elif node.element is ManNode.ElementType.URL:
            # GNU groff has a .UR/.UE macro set for urls. They work a little
            # oddly and don't seem to do anything on some platforms, so don't use that.
            pass
        elif node.element is ManNode.ElementType.STRONG:
            self.push_formatting(Formatting.BOLD)
        elif node.element is ManNode.ElementType.EMPHASIS:
            self.push_formatting(Formatting.EMPHASIS)
        elif node.element is ManNode.ElementType.LIST:
            self.list_stack.append(node.attributes["type"])
            self.macro("RS")
        elif node.element is ManNode.ElementType.LIST_ITEM:
            assert self.list_stack
            self.need_paragraph_splitter = False
            self.macro("IP", f"\\(bu {len(self.list_stack) * 2}")
        elif node.element is ManNode.ElementType.INDENT:
            self.macro("RS")
        elif node.element is ManNode.ElementType.PREFORMATTED:
            self.macro("EX")

    def handle_end(self, node: ManNode) -> None:
        self.flush()

        if node.element in {
            ManNode.ElementType.PARAGRAPH,
            ManNode.ElementType.PREFORMATTED,
        }:
            self.need_paragraph_splitter = True

        if node.element is ManNode.ElementType.MANPAGE:
            pass
        elif node.element is ManNode.ElementType.SECTION:
            self.section_depth -= 1
        elif node.element is ManNode.ElementType.URL:
            self.handle_text(f" ({node.attributes['href']})")
        elif node.element is ManNode.ElementType.STRONG:
            self.pop_formatting()
        elif node.element is ManNode.ElementType.EMPHASIS:
            self.pop_formatting()
        elif node.element is ManNode.ElementType.LIST:
            self.list_stack.pop()
            self.macro("RE")
        elif node.element is ManNode.ElementType.LIST_ITEM:
            pass
        elif node.element is ManNode.ElementType.INDENT:
            self.macro("RE")
        elif node.element is ManNode.ElementType.PREFORMATTED:
            self.macro("EE")

    def handle_text(self, text: str) -> None:
        self.text_buffer.write(troff_escape(text))

    def push_formatting(self, formatting: Formatting) -> None:
        if not self.formatting_stack or formatting is not self.formatting_stack[-1]:
            if formatting is Formatting.BOLD:
                self.write_raw("\\fB")
            elif formatting is Formatting.EMPHASIS:
                self.write_raw("\\fI")

        self.formatting_stack.append(formatting)

    def pop_formatting(self) -> None:
        self.formatting_stack.pop()
        if len(self.formatting_stack) > 1:
            a = self.formatting_stack[-1]
            if a is Formatting.BOLD:
                self.write_raw("\\fB")
            elif a is Formatting.EMPHASIS:
                self.write_raw("\\fI")
        else:
            self.write_raw("\\f1")


class SnootyToTroffTree:
    """Transforms snooty AST nodes to an intermediate representation of ManNodes."""

    def handle(self, node: n.Node) -> List[ManNode]:
        try:
            handler = getattr(self, f"handle_{type(node).__name__}")
        except AttributeError:
            logger.error("INTERNAL: Unknown node type: %s", type(node).__name__)
            return []

        return cast(List[ManNode], handler(node))

    def children(self, nodes: Iterable[n.Node]) -> List[ManNode]:
        list_of_lists = [self.handle(child) for child in nodes]
        return [item for sublist in list_of_lists for item in sublist]

    def handle_Code(self, node: n.Code) -> List[ManNode]:
        return [
            ManNode(
                ManNode.ElementType.PREFORMATTED,
                "\n".join("  " + line for line in node.value.split("\n")),
            )
        ]

    def handle_Section(self, node: n.Section) -> List[ManNode]:
        heading = next(
            (child for child in node.children if isinstance(child, n.Heading)), None
        )
        assert heading is not None, "Section without heading"
        return [
            ManNode(
                ManNode.ElementType.SECTION,
                self.children(node.children),
                {"name": heading.get_text()},
            )
        ]

    def handle_Paragraph(self, node: n.Paragraph) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.PARAGRAPH, self.children(node.children))]

    def handle_Footnote(self, node: n.Footnote) -> List[ManNode]:
        return []

    def handle_FootnoteReference(self, node: n.FootnoteReference) -> List[ManNode]:
        return self.children(node.children)

    def handle_SubstitutionDefinition(
        self, node: n.SubstitutionDefinition
    ) -> List[ManNode]:
        return []

    def handle_SubstitutionReference(
        self, node: n.SubstitutionReference
    ) -> List[ManNode]:
        return self.children(node.children)

    def handle_BlockSubstitutionReference(
        self, node: n.BlockSubstitutionReference
    ) -> List[ManNode]:
        return self.children(node.children)

    def handle_Root(self, node: n.Root) -> List[ManNode]:
        return self.children(node.children)

    def handle_Heading(self, node: n.Heading) -> List[ManNode]:
        return []

    def handle_DefinitionListItem(self, node: n.DefinitionListItem) -> List[ManNode]:
        return [
            ManNode(
                ManNode.ElementType.PARAGRAPH,
                [
                    ManNode(ManNode.ElementType.STRONG, self.children(node.term)),
                    ManNode(ManNode.ElementType.INDENT, self.children(node.children)),
                ],
            )
        ]

    def handle_DefinitionList(self, node: n.DefinitionList) -> List[ManNode]:
        return self.children(node.children)

    def handle_ListNodeItem(self, node: n.ListNodeItem) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.LIST_ITEM, self.children(node.children))]

    def handle_ListNode(self, node: n.ListNode) -> List[ManNode]:
        return [
            ManNode(
                ManNode.ElementType.LIST,
                self.children(node.children),
                {
                    "type": "unordered"
                    if node.enumtype == n.ListEnumType.unordered
                    else "ordered"
                },
            )
        ]

    def handle_Line(self, node: n.Line) -> List[ManNode]:
        return []

    def handle_LineBlock(self, node: n.LineBlock) -> List[ManNode]:
        return []

    def handle_Directive(self, node: n.Directive) -> List[ManNode]:
        return self.children(node.children)

    def handle_TocTreeDirectiveEntry(
        self, node: n.TocTreeDirectiveEntry
    ) -> List[ManNode]:
        return []

    def handle_TocTreeDirective(self, node: n.TocTreeDirective) -> List[ManNode]:
        return []

    def handle_DirectiveArgument(self, node: n.DirectiveArgument) -> List[ManNode]:
        return []

    def handle_Target(self, node: n.Target) -> List[ManNode]:
        # Skip anything without a description
        if not node.children or all(
            (
                isinstance(child, (n.DirectiveArgument, n.TargetIdentifier))
                for child in node.children
            )
        ):
            return []

        names: List[ManNode] = []
        for identifier in node.get_child_of_type(n.TargetIdentifier):
            names.append(
                ManNode(
                    ManNode.ElementType.STRONG,
                    [ManNode(ManNode.ElementType.TEXT, identifier.get_text())],
                )
            )
            names.append(ManNode(ManNode.ElementType.TEXT, ", "))

        if names[-1].element is ManNode.ElementType.TEXT:
            names.pop()

        return [
            ManNode(
                ManNode.ElementType.PARAGRAPH,
                names
                + [
                    ManNode(ManNode.ElementType.INDENT, self.children(node.children)),
                ],
            )
        ]

    def handle_TargetIdentifier(self, node: n.TargetIdentifier) -> List[ManNode]:
        return []

    def handle_InlineTarget(self, node: n.InlineTarget) -> List[ManNode]:
        return []

    def handle_Reference(self, node: n.Reference) -> List[ManNode]:
        return [
            ManNode(
                ManNode.ElementType.URL,
                self.children(node.children),
                {"href": node.refuri},
            )
        ]

    def handle_NamedReference(self, node: n.NamedReference) -> List[ManNode]:
        return []

    def handle_Role(self, node: n.Role) -> List[ManNode]:
        return self.children(node.children)

    def handle_RefRole(self, node: n.RefRole) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.STRONG, self.children(node.children))]

    def handle_Text(self, node: n.Text) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.TEXT, node.value)]

    def handle_Literal(self, node: n.Literal) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.STRONG, self.children(node.children))]

    def handle_Emphasis(self, node: n.Emphasis) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.EMPHASIS, self.children(node.children))]

    def handle_Field(self, node: n.Field) -> List[ManNode]:
        return []

    def handle_FieldList(self, node: n.FieldList) -> List[ManNode]:
        return []

    def handle_Strong(self, node: n.Strong) -> List[ManNode]:
        return [ManNode(ManNode.ElementType.STRONG, self.children(node.children))]

    def handle_Transition(self, node: n.Transition) -> List[ManNode]:
        return []

    def handle_Table(self, node: n.Table) -> List[ManNode]:
        return []

    def handle_Comment(self, node: n.Comment) -> List[ManNode]:
        return []


def render(page: Page, name: str, title: str, section: int) -> Dict[FileId, str]:
    """Render the given page as a manpage."""
    root = ManNode(
        ManNode.ElementType.MANPAGE,
        SnootyToTroffTree().handle(page.ast),
        {"name": name, "section": str(section), "desc": title},
    )
    body = root.to_troff()

    return {FileId(f"{name}.{section}"): body}

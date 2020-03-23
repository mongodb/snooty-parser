import dataclasses
from typing import (
    Any,
    ClassVar,
    Dict,
    Tuple,
    List,
    NamedTuple,
    MutableSequence,
    Sequence,
    Optional,
    Iterator,
    Type,
    TypeVar,
    Union,
    Generic,
)
from dataclasses import dataclass


__all__ = (
    "Node",
    "InlineNode",
    "Code",
    "Parent",
    "InlineParent",
    "Heading",
    "Section",
    "Directive",
    "DirectiveArgument",
    "Paragraph",
    "TargetIdentifier",
    "Role",
    "RefRole",
    "Text",
)

SerializableType = Union[None, bool, str, int, float, Dict[str, Any], List[Any]]
SerializedNode = Dict[str, SerializableType]
_T = TypeVar("_T")


@dataclass
class Node:
    __slots__ = ("span",)
    type: ClassVar[str] = "node"
    span: Tuple[int]

    def serialize(self) -> SerializedNode:
        """Serialize this AST node into a form that can be passed to json.dumps()."""
        result: SerializedNode = {
            "type": self.type,
            "position": {"start": {"line": self.span[0]}},
        }

        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Node):
                # Serialize nodes
                result[field.name] = value.serialize()
            elif isinstance(value, (str, int, float, bool)):
                # Primitive value: include verbatim
                result[field.name] = value
            elif isinstance(value, dict):
                # We exclude empty dicts, since they're mainly used for directive options and other such things.
                if value:
                    result[field.name] = value
            elif isinstance(value, (list, tuple)):
                # This is a bit unsafe, but it's the most expedient option right now. If the child
                # has a serialize() method, call that; otherwise, include it as-is.
                result[field.name] = [
                    child.serialize() if hasattr(child, "serialize") else child
                    for child in value
                ]
            elif value is None:
                # Fields with None values are excluded
                continue
            else:
                raise NotImplementedError(field, value)

        del result["span"]
        return result

    def get_text(self) -> str:
        """Return pure textual content from a given AST node. Most nodes will return an empty string."""
        return ""

    @property
    def start(self) -> Tuple[int]:
        return self.span

    def verify(self) -> None:
        """Perform optional validations on this node."""
        pass


_N = TypeVar("_N", bound=Node)


@dataclass
class InlineNode(Node):
    __slots__ = ()


@dataclass
class Code(Node):
    __slots__ = ("lang", "copyable", "emphasize_lines", "value")
    type = "code"
    lang: Optional[str]
    copyable: bool
    emphasize_lines: Optional[Sequence[Tuple[int, int]]]
    value: str


@dataclass
class Parent(Node, Generic[_N]):
    __slots__ = ("children",)
    type = "parent"
    children: MutableSequence[_N]

    def get_child_of_type(self, ty: Type[_T]) -> Iterator[_T]:
        """Return the first immediate child node with a given type, or None."""
        for child in self.children:
            if isinstance(child, ty):
                yield child

    def get_text(self) -> str:
        return "".join(child.get_text() for child in self.children)

    def verify(self) -> None:
        super().verify()
        for child in self.children:
            child.verify()


@dataclass
class InlineParent(InlineNode, Parent[InlineNode]):
    __slots__ = ()

    def verify(self) -> None:
        super().verify()
        for child in self.children:
            assert isinstance(child, InlineNode), f"{child.type} is not an inline node"


@dataclass
class Section(Parent[Node]):
    __slots__ = ()
    type = "section"


@dataclass
class Paragraph(Parent[Node]):
    __slots__ = ()
    type = "paragraph"


@dataclass
class Footnote(Parent[Node]):
    __slots__ = ("id", "name")
    type = "footnote"
    id: str
    name: Optional[str]


@dataclass
class FootnoteReference(InlineParent):
    __slots__ = ("id", "refname")
    type = "footnote_reference"
    id: str
    refname: Optional[str]


@dataclass
class SubstitutionDefinition(Parent[InlineNode]):
    __slots__ = ("name",)
    type = "substitution_definition"
    name: str


@dataclass
class SubstitutionReference(InlineParent):
    __slots__ = ("name",)
    type = "substitution_reference"
    name: str


@dataclass
class Root(Parent[Node]):
    __slots__ = ("options",)
    type = "root"
    options: Dict[str, str]


@dataclass
class Heading(Parent[InlineNode]):
    __slots__ = ("id",)
    type = "heading"
    id: str


@dataclass
class DefinitionListItem(Parent[Node]):
    __slots__ = ("term",)
    type = "definitionListItem"
    term: List[InlineNode]


@dataclass
class DefinitionList(Parent[DefinitionListItem]):
    __slots__ = ()
    type = "definitionList"


@dataclass
class ListNodeItem(Parent[Node]):
    __slots__ = ()
    type = "listItem"


@dataclass
class ListNode(Parent[ListNodeItem]):
    __slots__ = ("ordered",)
    type = "list"
    ordered: bool


@dataclass
class Line(Parent[InlineNode]):
    __slots__ = ()
    type = "line"


@dataclass
class LineBlock(Parent[Line]):
    __slots__ = ()
    type = "line_block"


@dataclass
class Directive(Parent[Node]):
    __slots__ = ("domain", "name", "argument", "options")
    type = "directive"
    domain: str
    name: str
    argument: List["Text"]
    options: Dict[str, str]

    def verify(self) -> None:
        super().verify()
        for arg in self.argument:
            arg.verify()


class TocTreeDirectiveEntry(NamedTuple):
    title: Optional[str]
    url: Optional[str]
    slug: Optional[str]

    def serialize(self) -> SerializedNode:
        result: SerializedNode = {}
        if self.title:
            result["title"] = self.title
        if self.url:
            result["url"] = self.url
        if self.slug:
            result["slug"] = self.slug
        return result


@dataclass
class TocTreeDirective(Directive):
    __slots__ = ("entries",)
    entries: Sequence[TocTreeDirectiveEntry]


@dataclass
class DirectiveArgument(Parent[InlineNode]):
    __slots__ = ()
    type = "directive_argument"


@dataclass
class Target(Parent[Node]):
    __slots__ = ("domain", "name", "refuri")
    type = "target"
    domain: str
    name: str
    refuri: Optional[str]


@dataclass
class TargetIdentifier(InlineParent):
    __slots__ = ("ids",)
    type = "target_identifier"
    ids: List[str]


@dataclass
class Reference(InlineParent):
    __slots__ = ("refuri", "refname")
    type = "reference"
    refuri: str
    refname: str


@dataclass
class Role(InlineParent):
    __slots__ = ("domain", "name", "target", "flag")
    type = "role"
    domain: str
    name: str
    target: str
    flag: str


@dataclass
class RefRole(Role):
    __slots__ = ("fileid", "url")
    type = "ref_role"
    fileid: Optional[str]
    url: Optional[str]

    def verify(self) -> None:
        assert (
            self.fileid is not None or self.url is not None
        ), f"Missing required target field: {self.serialize()}"


@dataclass
class Text(InlineNode):
    __slots__ = ("value",)
    type = "text"
    value: str

    def get_text(self) -> str:
        return self.value


@dataclass
class LiteralBlock(Parent[InlineParent]):
    __slots__ = ()
    type = "FixedTextElement"


@dataclass
class Literal(InlineParent):
    __slots__ = ()
    type = "literal"


@dataclass
class Emphasis(InlineParent):
    __slots__ = ()
    type = "emphasis"


@dataclass
class Strong(InlineParent):
    __slots__ = ()
    type = "strong"


@dataclass
class Transition(Node):
    __slots__ = ()
    type = "transition"


@dataclass
class Table(Parent[Node]):
    __slots__ = ()
    type = "table"

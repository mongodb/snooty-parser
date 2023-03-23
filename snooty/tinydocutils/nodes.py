# $Id: nodes.py 7788 2015-02-16 22:10:52Z milde $
# Author: David Goodger <goodger@python.org>
# Maintainer: docutils-develop@lists.sourceforge.net
# Copyright: This module has been placed in the public domain.

"""
Docutils document tree element class library.

Classes in CamelCase are abstract base classes or auxiliary classes. The one
exception is `Text`, for a text (PCDATA) node; uppercase is used to
differentiate from element classes.  Classes in lower_case_with_underscores
are element classes, matching the XML element generic identifiers in the DTD_.

The position of each node (the level at which it can occur) is significant and
is represented by abstract base classes (`Root`, `Structural`, `Body`,
`Inline`, etc.).  Certain transformations will be easier because we can use
``isinstance(node, base_class)`` to determine the position of the node in the
hierarchy.

.. _DTD: http://docutils.sourceforge.net/docs/ref/docutils.dtd
"""

__docformat__ = "reStructuredText"

import re
import sys
import unicodedata
from typing import (
    IO,
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from . import frontend

# ==============================
#  Functional Node Base Classes
# ==============================


class Node:

    """Abstract base class of nodes in a document tree."""

    parent: "Optional[Node]" = None
    """Back-reference to the Node immediately containing this Node."""

    source: Optional[str] = None
    """Path or description of the input source which generated this Node."""

    line: Optional[int] = None
    """The line number (1-based) of the beginning of this Node in `source`."""

    _document: "Optional[document]" = None

    @property
    def document(self) -> "Optional[document]":
        """
        Return the `document` node at the root of the tree containing this Node.
        """
        if self._document:
            return self._document

        if self.parent:
            return self.parent.document

        return None

    @document.setter
    def document(self, value: "document") -> None:
        self._document = value

    def __bool__(self) -> bool:
        """
        Node instances are always true, even if they're empty.  A node is more
        than a simple container.  Its boolean "truth" does not depend on
        having one or more subnodes in the doctree.

        Use `len()` to check node length.  Use `None` to represent a boolean
        false value.
        """
        return True

    def pformat(self, indent: str = "    ", level: int = 0) -> str:
        """
        Return an indented pseudo-XML representation, for test purposes.

        Override in subclasses.
        """
        raise NotImplementedError

    def astext(self) -> str:
        """Return a string representation of this Node."""
        raise NotImplementedError

    def setup_child(self, child: "Node") -> None:
        child.parent = self
        if self.document:
            child.document = self.document
            if child.source is None:
                child.source = self.document.current_source
            if child.line is None:
                child.line = self.document.current_line

    def walk(self, visitor: Any) -> bool:
        """
        Traverse a tree of `Node` objects, calling the
        `dispatch_visit()` method of `visitor` when entering each
        node.  (The `walkabout()` method is similar, except it also
        calls the `dispatch_departure()` method before exiting each
        node.)

        This tree traversal supports limited in-place tree
        modifications.  Replacing one node with one or more nodes is
        OK, as is removing an element.  However, if the node removed
        or replaced occurs after the current node, the old node will
        still be traversed, and any new nodes will not.

        Within ``visit`` methods (and ``depart`` methods for
        `walkabout()`), `TreePruningException` subclasses may be raised
        (`SkipChildren`, `SkipSiblings`, `SkipNode`, `SkipDeparture`).

        Parameter `visitor`: A `NodeVisitor` object, containing a
        ``visit`` implementation for each `Node` subclass encountered.

        Return true if we should stop the traversal.
        """
        stop = False
        try:
            try:
                visitor.dispatch_visit(self)
            except (SkipChildren, SkipNode):
                return stop
            except SkipDeparture:  # not applicable; ignore
                pass

            assert isinstance(self, Element)
            children = self.children

            try:
                for child in children[:]:
                    if child.walk(visitor):
                        stop = True
                        break
            except SkipSiblings:
                pass
        except StopTraversal:
            stop = True
        return stop

    def walkabout(self, visitor: Any) -> bool:
        """
        Perform a tree traversal similarly to `Node.walk()` (which
        see), except also call the `dispatch_departure()` method
        before exiting each node.

        Parameter `visitor`: A `NodeVisitor` object, containing a
        ``visit`` and ``depart`` implementation for each `Node`
        subclass encountered.

        Return true if we should stop the traversal.
        """
        call_depart = True
        stop = False
        try:
            try:
                visitor.dispatch_visit(self)
            except SkipNode:
                return stop
            except SkipDeparture:
                call_depart = False

            assert isinstance(self, (Element, Text))
            children = self.children

            try:
                for child in children[:]:
                    if child.walkabout(visitor):
                        stop = True
                        break
            except SkipSiblings:
                pass
        except SkipChildren:
            pass
        except StopTraversal:
            stop = True
        if call_depart:
            visitor.dispatch_departure(self)
        return stop

    def _fast_traverse(self, cls: type) -> Iterator["Node"]:
        """Return iterator that only supports instance checks."""
        if isinstance(self, cls):
            yield self
        if isinstance(self, Element):
            for child in self.children:
                for subnode in child._fast_traverse(cls):
                    yield subnode

    def _all_traverse(self) -> "Iterator[Node]":
        """Return iterator that doesn't check for a condition."""
        yield self
        if isinstance(self, Element):
            for child in self.children:
                for subnode in child._all_traverse():
                    yield subnode

    def traverse(
        self,
        condition: Optional[type] = None,
        include_self: bool = True,
    ) -> "Iterator[Node]":
        """Return iterator over nodes following `self`. See `traverse()`."""
        # Check for special argument combinations that allow using an
        # optimized version of traverse()
        if include_self:
            if condition is None:
                for subnode in self._all_traverse():
                    yield subnode
                return
            elif isinstance(condition, type):
                for subnode in self._fast_traverse(condition):
                    yield subnode
                return

    def get_line(self) -> int:
        """Return the first line number we can find in node's ancestry."""

        def line_of_node(node: "Node") -> Optional[int]:
            """Sometimes you need node['line']. Sometimes you need node.line.
            Sometimes you want to just run away and herd yaks."""
            if isinstance(node, Element) and "line" in node:
                return cast(int, node["line"])

            return node.line

        node = self

        while line_of_node(node) is None:
            if node.parent is None:
                # This is probably a document node
                return 0
            node = node.parent

        return cast(int, line_of_node(node)) - 1


# definition moved here from `utils` to avoid circular import dependency
def unescape(text: str, restore_backslashes: bool = False) -> str:
    """
    Return a string with nulls removed or restored to backslashes.
    Backslash-escaped spaces are also removed.
    """
    if restore_backslashes:
        return text.replace("\x00", "\\")
    else:
        for sep in ["\x00 ", "\x00\n", "\x00"]:
            text = "".join(text.split(sep))
        return text


class Text(Node):

    """
    Instances are terminal nodes (leaves) containing text only; no child
    nodes or attributes.  Initialize by passing a string to the constructor.
    Access the text itself with the `astext` method.
    """

    tagname = "#text"

    children: "Sequence[ConcreteNode]" = ()
    """Text nodes have no children, and cannot have children."""

    def __init__(self, value: str, rawsource: str = "") -> None:
        self.value = value
        self.rawsource = rawsource
        """The raw text from which this element was constructed."""

    def shortrepr(self, maxlen: int = 18) -> str:
        data: str = self.value
        if len(data) > maxlen:
            data = data[: maxlen - 4] + " ..."
        return "<%s: %r>" % (self.tagname, str(data))

    def __repr__(self) -> str:
        return self.shortrepr(maxlen=68)

    def astext(self) -> str:
        return unescape(self.value)

    def pformat(self, indent: str = "    ", level: int = 0) -> str:
        indent = indent * level
        lines = [indent + line for line in self.astext().splitlines()]
        if not lines:
            return ""
        return "\n".join(lines) + "\n"


class Element(Node):

    """
    `Element` is the superclass to all specific elements.

    Elements contain attributes and child nodes.  Elements emulate
    dictionaries for attributes, indexing by attribute name (a string).  To
    set the attribute 'att' to 'value', do::

        element['att'] = 'value'

    There are two special attributes: 'ids' and 'names'.  Both are
    lists of unique identifiers, and names serve as human interfaces
    to IDs.  Names are case- and whitespace-normalized (see the
    fully_normalize_name() function), and IDs conform to the regular
    expression ``[a-z](-?[a-z0-9]+)*`` (see the make_id() function).

    Elements also emulate lists for child nodes (element nodes and/or text
    nodes), indexing by integer.  To get the first child node, use::

        element[0]
    """

    basic_attributes = ("ids", "classes", "names", "dupnames")
    """List attributes which are defined for every Element-derived class
    instance and can be safely transferred to a different node."""

    local_attributes = ("backrefs",)
    """A list of class-specific attributes that should not be copied with the
    standard attributes when replacing a node.

    NOTE: Derived classes should override this value to prevent any of its
    attributes being copied by adding to the value in its parent class."""

    list_attributes = basic_attributes + local_attributes
    """List attributes, automatically initialized to empty lists for
    all nodes."""

    child_text_separator = "\n\n"
    """Separator for child nodes, used by `astext()` method."""

    def __init__(
        self, rawsource: str = "", *children: "ConcreteNode", **attributes: Any
    ) -> None:
        self.rawsource = rawsource
        """The raw text from which this element was constructed.

        NOTE: some elements do not set this value (default '').
        """

        self.children: List[ConcreteNode] = []
        """List of child nodes (elements and/or `Text`)."""

        self.extend(children)  # maintain parent info

        self.attributes: Dict[str, Any] = {}
        """Dictionary of attribute {name: value}."""

        # Initialize list attributes.
        for att in self.list_attributes:
            self.attributes[att] = []

        for att, value in attributes.items():
            att = att.lower()
            if att in self.list_attributes:
                # mutable list; make a copy for this node
                self.attributes[att] = value[:]
            else:
                self.attributes[att] = value

        self.tagname = self.__class__.__name__

    def __repr__(self) -> str:
        data = ""
        for c in self.children:
            data += c.shortrepr()
            if len(data) > 60:
                data = data[:56] + " ..."
                break
        if self["names"]:
            return '<%s "%s": %s>' % (
                self.__class__.__name__,
                "; ".join([n for n in self["names"]]),
                data,
            )
        else:
            return "<%s: %s>" % (self.__class__.__name__, data)

    def shortrepr(self) -> str:
        if self["names"]:
            return '<%s "%s"...>' % (
                self.__class__.__name__,
                "; ".join([n for n in self["names"]]),
            )
        else:
            return "<%s...>" % self.tagname

    def __str__(self) -> str:
        if self.children:
            return "%s%s%s" % (
                self.starttag(),
                "".join([str(c) for c in self.children]),
                self.endtag(),
            )
        else:
            return self.emptytag()

    def starttag(self, quoteattr: Optional[Callable[[str], str]] = None) -> str:
        # the optional arg is used by the docutils_xml writer
        if quoteattr is None:
            quoteattr = pseudo_quoteattr

        parts = [self.tagname]

        for name, value in self.attlist():
            if value is None:  # boolean attribute
                parts.append('%s="True"' % name)
                continue
            if isinstance(value, list):
                values = [serial_escape("%s" % (v,)) for v in value]
                value = " ".join(values)
            else:
                value = str(value)
            value = quoteattr(value)
            parts.append("%s=%s" % (name, value))
        return "<%s>" % " ".join(parts)

    def endtag(self) -> str:
        return "</%s>" % self.tagname

    def emptytag(self) -> str:
        assert self.tagname
        return "<%s/>" % " ".join(
            [self.tagname] + ['%s="%s"' % (n, v) for n, v in self.attlist()]
        )

    def __len__(self) -> int:
        return len(self.children)

    def __contains__(self, key: object) -> bool:
        # Test for both, children and attributes with operator ``in``.
        if isinstance(key, str):
            return key in self.attributes
        return key in self.children

    def __getitem__(self, key: Union[str, int, slice]) -> Any:
        if isinstance(key, str):
            return self.attributes[key]
        elif isinstance(key, int):
            return self.children[key]
        elif isinstance(key, slice):
            assert key.step in (None, 1), "cannot handle slice with stride"
            return self.children[key.start : key.stop]
        else:
            raise TypeError(
                "element index must be an integer, a slice, or "
                "an attribute name string"
            )

    def __setitem__(self, key: Union[str, int, slice], item: Any) -> None:
        if isinstance(key, str):
            self.attributes[str(key)] = item
        elif isinstance(key, int):
            self.setup_child(item)
            self.children[key] = item
        elif isinstance(key, slice):
            assert key.step in (None, 1), "cannot handle slice with stride"
            for node in item:
                self.setup_child(node)
            self.children[key.start : key.stop] = item
        else:
            raise TypeError(
                "element index must be an integer, a slice, or "
                "an attribute name string"
            )

    def __delitem__(self, key: Union[str, int, slice]) -> None:
        if isinstance(key, str):
            del self.attributes[key]
        elif isinstance(key, int):
            del self.children[key]
        elif isinstance(key, slice):
            assert key.step in (None, 1), "cannot handle slice with stride"
            del self.children[key.start : key.stop]
        else:
            raise TypeError(
                "element index must be an integer, a simple "
                "slice, or an attribute name string"
            )

    def __iter__(self) -> Iterator[Union[Text, "Element"]]:
        return iter(self.children)

    def astext(self) -> str:
        return self.child_text_separator.join(
            [child.astext() for child in self.children]
        )

    def non_default_attributes(self) -> Dict[str, Any]:
        atts = {}
        for key, value in self.attributes.items():
            if self.is_not_default(key):
                atts[key] = value
        return atts

    def attlist(self) -> List[Tuple[str, Any]]:
        attlist = sorted(self.non_default_attributes().items())
        return attlist

    def get(self, key: str, failobj: object = None) -> object:
        return self.attributes.get(key, failobj)

    def append(self, item: "ConcreteNode") -> None:
        if not isinstance(item, Node):
            print(item)
            assert False
        self.setup_child(item)
        self.children.append(item)

    def extend(self, item: Iterable["ConcreteNode"]) -> None:
        if not all(isinstance(child, Node) for child in item):
            print(item)
            assert False

        for node in item:
            self.append(node)

    def insert(self, index: int, item: "ConcreteNode") -> None:
        if isinstance(item, Node):
            self.setup_child(item)
            self.children.insert(index, item)
        elif item is not None:
            self[index:index] = item

    def pop(self, i: int = -1) -> "ConcreteNode":
        return self.children.pop(i)

    def remove(self, item: "ConcreteNode") -> None:
        self.children.remove(item)

    def index(self, item: "ConcreteNode") -> int:
        return self.children.index(item)

    def is_not_default(self, key: str) -> bool:
        if self[key] == [] and key in self.list_attributes:
            return False
        else:
            return True

    def replace(self, old: "ConcreteNode", new: Node) -> None:
        """Replace one child `Node` with another child or children."""
        index = self.index(old)
        if isinstance(new, Node):
            self.setup_child(new)
            self[index] = new
        elif new is not None:
            self[index : index + 1] = new

    def pformat(self, indent: str = "    ", level: int = 0) -> str:
        return "".join(
            ["%s%s\n" % (indent * level, self.starttag())]
            + [child.pformat(indent, level + 1) for child in self.children]
        )


ConcreteNode = Union[Text, Element]


class TextElement(Element):

    """
    An element which directly contains text.

    Its children are all `Text` or `Inline` subclass nodes.  You can
    check whether an element's context is inline simply by checking whether
    its immediate parent is a `TextElement` instance (including subclasses).
    This is handy for nodes like `image` that can appear both inline and as
    standalone body elements.

    If passing children to `__init__()`, make sure to set `text` to
    ``''`` or some other suitable value.
    """

    child_text_separator = ""
    """Separator for child nodes, used by `astext()` method."""

    def __init__(
        self,
        rawsource: str = "",
        text: str = "",
        *children: ConcreteNode,
        **attributes: Any
    ) -> None:
        if text != "":
            textnode = Text(text)
            Element.__init__(self, rawsource, textnode, *children, **attributes)
        else:
            Element.__init__(self, rawsource, *children, **attributes)


class FixedTextElement(TextElement):

    """An element which directly contains preformatted text."""

    def __init__(
        self,
        rawsource: str = "",
        text: str = "",
        *children: ConcreteNode,
        **attributes: Any
    ) -> None:
        TextElement.__init__(self, rawsource, text, *children, **attributes)
        self.attributes["xml:space"] = "preserve"


# ====================
#  Element Categories
# ====================


class Root:
    pass


class Titular:
    pass


class PreBibliographic:
    """Category of Node which may occur before Bibliographic Nodes."""


class Structural:
    pass


class Body:
    pass


class General(Body):
    pass


class Inline:
    pass


# ==============
#  Root Element
# ==============


class document(Root, Structural, Element):

    """
    The document root element.

    Do not instantiate this class directly; use
    `docutils.utils.new_document()` instead.
    """

    def __init__(
        self, settings: frontend.OptionParser, reporter: "Reporter", source: str
    ) -> None:
        Element.__init__(self, source=source)

        self.current_source: Optional[str] = None
        """Path to or description of the input source being processed."""

        self.current_line: Optional[int] = None
        """Line number (1-based) of `current_source`."""

        self.settings = settings
        """Runtime settings data record."""

        self.reporter = reporter
        """System message generator."""

        self.indirect_targets: List[target] = []
        """List of indirect target nodes."""

        self.refnames: Dict[str, List[Node]] = {}
        """Mapping of names to lists of referencing nodes."""

        self.nameids: Dict[str, Optional[str]] = {}
        """Mapping of names to unique id's."""

        self.nametypes: Dict[str, bool] = {}
        """Mapping of names to hyperlink type (boolean: True => explicit,
        False => implicit."""

        self.ids: Dict[str, Element] = {}
        """Mapping of ids to nodes."""

        self.footnote_refs: Dict[str, List[footnote_reference]] = {}
        """Mapping of footnote labels to lists of footnote_reference nodes."""

        self.citation_refs: Dict[str, List[citation_reference]] = {}
        """Mapping of citation labels to lists of citation_reference nodes."""

        self.autofootnotes: List[footnote] = []
        """List of auto-numbered footnote nodes."""

        self.autofootnote_refs: List[footnote_reference] = []
        """List of auto-numbered footnote_reference nodes."""

        self.symbol_footnotes: List[footnote] = []
        """List of symbol footnote nodes."""

        self.symbol_footnote_refs: List[footnote_reference] = []
        """List of symbol footnote_reference nodes."""

        self.footnotes: List[footnote] = []
        """List of manually-numbered footnote nodes."""

        self.citations: List[citation] = []
        """List of citation nodes."""

        self.id_start = 1
        """Initial ID number."""

        self.document = self

    def __getstate__(self) -> Dict[str, object]:
        """
        Return dict with unpicklable references removed.
        """
        state = self.__dict__.copy()
        state["reporter"] = None
        state["transformer"] = None
        return state

    def set_id(self, node: Element, msgnode: "Optional[Element]" = None) -> str:
        for id in cast(Sequence[str], node["ids"]):
            if id in self.ids and self.ids[id] is not node:
                msg = self.reporter.severe('Duplicate ID: "%s".' % id)
                if msgnode is not None:
                    msgnode.append(msg)
        if not node["ids"]:
            for name in node["names"]:
                id = self.settings.id_prefix + make_id(name)
                if id and id not in self.ids:
                    break
            else:
                id = ""
                while not id or id in self.ids:
                    id = (
                        self.settings.id_prefix
                        + self.settings.auto_id_prefix
                        + str(self.id_start)
                    )
                    self.id_start += 1
            node["ids"].append(id)
        self.ids[id] = node
        return id

    def set_name_id_map(
        self,
        node: Element,
        id: str,
        msgnode: "Optional[Element]" = None,
        explicit: bool = False,
    ) -> None:
        """
        `self.nameids` maps names to IDs, while `self.nametypes` maps names to
        booleans representing hyperlink type (True==explicit,
        False==implicit).  This method updates the mappings.

        The following state transition table shows how `self.nameids` ("ids")
        and `self.nametypes` ("types") change with new input (a call to this
        method), and what actions are performed ("implicit"-type system
        messages are INFO/1, and "explicit"-type system messages are ERROR/3):

        ====  =====  ========  ========  =======  ====  =====  =====
         Old State    Input          Action        New State   Notes
        -----------  --------  -----------------  -----------  -----
        ids   types  new type  sys.msg.  dupname  ids   types
        ====  =====  ========  ========  =======  ====  =====  =====
        -     -      explicit  -         -        new   True
        -     -      implicit  -         -        new   False
        None  False  explicit  -         -        new   True
        old   False  explicit  implicit  old      new   True
        None  True   explicit  explicit  new      None  True
        old   True   explicit  explicit  new,old  None  True   [#]_
        None  False  implicit  implicit  new      None  False
        old   False  implicit  implicit  new,old  None  False
        None  True   implicit  implicit  new      None  True
        old   True   implicit  implicit  new      old   True
        ====  =====  ========  ========  =======  ====  =====  =====

        .. [#] Do not clear the name-to-id map or invalidate the old target if
           both old and new targets are external and refer to identical URIs.
           The new target is invalidated regardless.
        """
        for name in node["names"]:
            if name in self.nameids:
                self.set_duplicate_name_id(node, id, name, msgnode, explicit)
            else:
                self.nameids[name] = id
                self.nametypes[name] = explicit

    def set_duplicate_name_id(
        self,
        node: Element,
        id: str,
        name: str,
        msgnode: "Optional[Element]",
        explicit: bool,
    ) -> None:
        old_id = self.nameids[name]
        old_explicit = self.nametypes[name]
        self.nametypes[name] = old_explicit or explicit
        if explicit:
            if old_explicit:
                level = 2
                if old_id is not None:
                    old_node = self.ids[old_id]
                    if "refuri" in node:
                        refuri = node["refuri"]
                        if (
                            old_node["names"]
                            and "refuri" in old_node
                            and old_node["refuri"] == refuri
                        ):
                            level = 1  # just inform if refuri's identical
                    if level > 1:
                        dupname(old_node, name)
                        self.nameids[name] = None
                msg = self.reporter.make_system_message(
                    level,
                    'Duplicate explicit target name: "%s".' % name,
                    backrefs=[id],
                    base_node=node,
                )
                if msgnode is not None:
                    msgnode.append(msg)
                dupname(node, name)
            else:
                self.nameids[name] = id
                if old_id is not None:
                    old_node = self.ids[old_id]
                    dupname(old_node, name)
        else:
            if old_id is not None and not old_explicit:
                self.nameids[name] = None
                old_node = self.ids[old_id]
                dupname(old_node, name)
            dupname(node, name)
        if not explicit or (not old_explicit and old_id is not None):
            msg = self.reporter.info(
                'Duplicate implicit target name: "%s".' % name,
                backrefs=[id],
                base_node=node,
            )
            if msgnode is not None:
                msgnode.append(msg)

    # "note" here is an imperative verb: "take note of".
    def note_implicit_target(
        self, target: "Element", msgnode: "Optional[Element]" = None
    ) -> None:
        id = self.set_id(target, msgnode)
        self.set_name_id_map(target, id, msgnode, explicit=False)

    def note_explicit_target(
        self, target: "Element", msgnode: "Optional[Element]" = None
    ) -> None:
        id = self.set_id(target, msgnode)
        self.set_name_id_map(target, id, msgnode, explicit=True)

    def note_refname(self, node: Element) -> None:
        self.refnames.setdefault(node["refname"], []).append(node)

    def note_indirect_target(self, target: "target") -> None:
        self.indirect_targets.append(target)
        if target["names"]:
            self.note_refname(target)

    def note_anonymous_target(self, target: "target") -> None:
        self.set_id(target)

    def note_autofootnote(self, footnote: "footnote") -> None:
        self.set_id(footnote)
        self.autofootnotes.append(footnote)

    def note_autofootnote_ref(self, ref: "footnote_reference") -> None:
        self.set_id(ref)
        self.autofootnote_refs.append(ref)

    def note_symbol_footnote(self, footnote: "footnote") -> None:
        self.set_id(footnote)
        self.symbol_footnotes.append(footnote)

    def note_symbol_footnote_ref(self, ref: "footnote_reference") -> None:
        self.set_id(ref)
        self.symbol_footnote_refs.append(ref)

    def note_footnote(self, footnote: "footnote") -> None:
        self.set_id(footnote)
        self.footnotes.append(footnote)

    def note_footnote_ref(self, ref: "footnote_reference") -> None:
        self.set_id(ref)
        self.footnote_refs.setdefault(ref["refname"], []).append(ref)
        self.note_refname(ref)

    def note_citation(self, citation: "citation") -> None:
        self.citations.append(citation)

    def note_citation_ref(self, ref: "citation_reference") -> None:
        self.set_id(ref)
        self.citation_refs.setdefault(ref["refname"], []).append(ref)
        self.note_refname(ref)

    def note_substitution_ref(
        self, subref: "substitution_reference", refname: str
    ) -> None:
        subref["refname"] = whitespace_normalize_name(refname)

    def note_source(self, source: Optional[str], offset: Optional[int]) -> None:
        self.current_source = source
        if offset is None:
            self.current_line = offset
        else:
            self.current_line = offset + 1


# ================
#  Title Elements
# ================


class title(Titular, PreBibliographic, TextElement):
    pass


# =====================
#  Structural Elements
# =====================


class section(Structural, Element):
    pass


class transition(Structural, Element):
    pass


# ===============
#  Body Elements
# ===============


class paragraph(General, TextElement):
    pass


class bullet_list(Element):
    pass


class enumerated_list(Element):
    pass


class list_item(Element):
    pass


class definition_list(Element):
    pass


class definition_list_item(Element):
    pass


class term(TextElement):
    pass


class classifier(TextElement):
    pass


class definition(Element):
    pass


class field_list(Element):
    pass


class field(Element):
    pass


class field_name(TextElement):
    pass


class field_body(Element):
    pass


class option(Element):

    child_text_separator = ""


class option_argument(TextElement):
    def astext(self) -> str:
        return cast(str, self.get("delimiter", " ")) + TextElement.astext(self)


class option_group(Element):

    child_text_separator = ", "


class option_list(Element):
    pass


class option_list_item(Element):

    child_text_separator = "  "


class option_string(TextElement):
    pass


class description(Element):
    pass


class literal_block(General, FixedTextElement):
    pass


class doctest_block(General, FixedTextElement):
    pass


class line_block(General, Element):
    def lines(self) -> Iterable["line"]:
        for child in self.children:
            assert isinstance(child, line)
            yield child


class line(TextElement):

    indent: int = 0


class block_quote(General, Element):
    pass


class error(Element):
    pass


class note(Element):
    pass


class hint(Element):
    pass


class warning(Element):
    pass


class comment(FixedTextElement):
    pass


class substitution_definition(TextElement):
    pass


class target(Inline, TextElement):
    pass


class footnote(General, Element):
    pass


class citation(General, Element):
    pass


class label(TextElement):
    pass


class table(General, Element):
    pass


class caption(TextElement):
    pass


class entry(Element):
    pass


class system_message(PreBibliographic, Element):

    """
    System message element.

    Do not instantiate this class directly; use
    ``document.reporter.info/warning/error/severe()`` instead.
    """

    def __init__(
        self, message: Optional[str] = None, *children: ConcreteNode, **attributes: Any
    ) -> None:
        if message:
            p = paragraph("", message)
            children = (p,) + children
        try:
            Element.__init__(self, "", *children, **attributes)
        except:
            print("system_message: children=%r" % (children,))
            raise

    def astext(self) -> str:
        line = self.get("line", "")
        return "%s:%s: (%s/%s) %s" % (
            self["source"],
            line,
            self["type"],
            self["level"],
            Element.astext(self),
        )


# =================
#  Inline Elements
# =================


class emphasis(Inline, TextElement):
    pass


class strong(Inline, TextElement):
    pass


class literal(Inline, TextElement):
    pass


class reference(Inline, General, TextElement):
    pass


class footnote_reference(Inline, TextElement):
    pass


class citation_reference(Inline, TextElement):
    pass


class substitution_reference(Inline, TextElement):
    pass


# ========================================
#  Auxiliary Classes, Functions, and Data
# ========================================


class NodeVisitor:

    """
    "Visitor" pattern [GoF95]_ abstract superclass implementation for
    document tree traversals.

    Each node class has corresponding methods, doing nothing by
    default; override individual methods for specific and useful
    behaviour.  The `dispatch_visit()` method is called by
    `Node.walk()` upon entering a node.  `Node.walkabout()` also calls
    the `dispatch_departure()` method before exiting a node.

    The dispatch methods call "``visit_`` + node class name" or
    "``depart_`` + node class name", resp.

    This is a base class for visitors whose ``visit_...`` & ``depart_...``
    methods should be implemented for *all* node types encountered (such as
    for `docutils.writers.Writer` subclasses).  Unimplemented methods will
    raise exceptions.

    For sparse traversals, where only certain node types are of interest,
    subclass `SparseNodeVisitor` instead.  When (mostly or entirely) uniform
    processing is desired, subclass `GenericNodeVisitor`.

    .. [GoF95] Gamma, Helm, Johnson, Vlissides. *Design Patterns: Elements of
       Reusable Object-Oriented Software*. Addison-Wesley, Reading, MA, USA,
       1995.
    """

    def __init__(self, document: document) -> None:
        self.document = document

    def dispatch_visit(self, node: ConcreteNode) -> None:
        """
        Call self."``visit_`` + node class name" with `node` as
        parameter.  If the ``visit_...`` method does not exist, call
        self.unknown_visit.
        """
        node_name = node.__class__.__name__
        method = getattr(self, "visit_" + node_name)
        self.document.reporter.debug(
            "docutils.nodes.NodeVisitor.dispatch_visit calling %s for %s"
            % (method.__name__, node_name)
        )
        method(node)

    def dispatch_departure(self, node: ConcreteNode) -> None:
        """
        Call self."``depart_`` + node class name" with `node` as
        parameter.  If the ``depart_...`` method does not exist, call
        self.unknown_departure.
        """
        node_name = node.__class__.__name__
        method = getattr(self, "depart_" + node_name)
        self.document.reporter.debug(
            "docutils.nodes.NodeVisitor.dispatch_departure calling %s for %s"
            % (method.__name__, node_name)
        )
        method(node)


class TreePruningException(Exception):

    """
    Base class for `NodeVisitor`-related tree pruning exceptions.

    Raise subclasses from within ``visit_...`` or ``depart_...`` methods
    called from `Node.walk()` and `Node.walkabout()` tree traversals to prune
    the tree traversed.
    """

    pass


class SkipChildren(TreePruningException):

    """
    Do not visit any children of the current node.  The current node's
    siblings and ``depart_...`` method are not affected.
    """

    pass


class SkipSiblings(TreePruningException):

    """
    Do not visit any more siblings (to the right) of the current node.  The
    current node's children and its ``depart_...`` method are not affected.
    """

    pass


class SkipNode(TreePruningException):

    """
    Do not visit the current node's children, and do not call the current
    node's ``depart_...`` method.
    """

    pass


class SkipDeparture(TreePruningException):

    """
    Do not call the current node's ``depart_...`` method.  The current node's
    children and siblings are not affected.
    """

    pass


class StopTraversal(TreePruningException):

    """
    Stop the traversal alltogether.  The current node's ``depart_...`` method
    is not affected.  The parent nodes ``depart_...`` methods are also called
    as usual.  No other nodes are visited.  This is an alternative to
    NodeFound that does not cause exception handling to trickle up to the
    caller.
    """

    pass


def make_id(string: str) -> str:
    """
    Convert `string` into an identifier and return it.

    Docutils identifiers will conform to the regular expression
    ``[a-z](-?[a-z0-9]+)*``.  For CSS compatibility, identifiers (the "class"
    and "id" attributes) should have no underscores, colons, or periods.
    Hyphens may be used.

    - The `HTML 4.01 spec`_ defines identifiers based on SGML tokens:

          ID and NAME tokens must begin with a letter ([A-Za-z]) and may be
          followed by any number of letters, digits ([0-9]), hyphens ("-"),
          underscores ("_"), colons (":"), and periods (".").

    - However the `CSS1 spec`_ defines identifiers based on the "name" token,
      a tighter interpretation ("flex" tokenizer notation; "latin1" and
      "escape" 8-bit characters have been replaced with entities)::

          unicode     \\[0-9a-f]{1,4}
          latin1      [&iexcl;-&yuml;]
          escape      {unicode}|\\[ -~&iexcl;-&yuml;]
          nmchar      [-a-z0-9]|{latin1}|{escape}
          name        {nmchar}+

    The CSS1 "nmchar" rule does not include underscores ("_"), colons (":"),
    or periods ("."), therefore "class" and "id" attributes should not contain
    these characters. They should be replaced with hyphens ("-"). Combined
    with HTML's requirements (the first character must be a letter; no
    "unicode", "latin1", or "escape" characters), this results in the
    ``[a-z](-?[a-z0-9]+)*`` pattern.

    .. _HTML 4.01 spec: http://www.w3.org/TR/html401
    .. _CSS1 spec: http://www.w3.org/TR/REC-CSS1
    """
    id = string.lower()
    id = id.translate(_non_id_translate_digraphs)
    id = id.translate(_non_id_translate)
    # get rid of non-ascii characters.
    # 'ascii' lowercase to prevent problems with turkish locale.
    id = unicodedata.normalize("NFKD", id).encode("ascii", "ignore").decode("ascii")
    # shrink runs of whitespace and replace by hyphen
    id = _non_id_chars.sub("-", " ".join(id.split()))
    id = _non_id_at_ends.sub("", id)
    return id


_non_id_chars = re.compile("[^a-z0-9]+")
_non_id_at_ends = re.compile("^[-0-9]+|-+$")
_non_id_translate = {
    0x00F8: "o",  # o with stroke
    0x0111: "d",  # d with stroke
    0x0127: "h",  # h with stroke
    0x0131: "i",  # dotless i
    0x0142: "l",  # l with stroke
    0x0167: "t",  # t with stroke
    0x0180: "b",  # b with stroke
    0x0183: "b",  # b with topbar
    0x0188: "c",  # c with hook
    0x018C: "d",  # d with topbar
    0x0192: "f",  # f with hook
    0x0199: "k",  # k with hook
    0x019A: "l",  # l with bar
    0x019E: "n",  # n with long right leg
    0x01A5: "p",  # p with hook
    0x01AB: "t",  # t with palatal hook
    0x01AD: "t",  # t with hook
    0x01B4: "y",  # y with hook
    0x01B6: "z",  # z with stroke
    0x01E5: "g",  # g with stroke
    0x0225: "z",  # z with hook
    0x0234: "l",  # l with curl
    0x0235: "n",  # n with curl
    0x0236: "t",  # t with curl
    0x0237: "j",  # dotless j
    0x023C: "c",  # c with stroke
    0x023F: "s",  # s with swash tail
    0x0240: "z",  # z with swash tail
    0x0247: "e",  # e with stroke
    0x0249: "j",  # j with stroke
    0x024B: "q",  # q with hook tail
    0x024D: "r",  # r with stroke
    0x024F: "y",  # y with stroke
}
_non_id_translate_digraphs = {
    0x00DF: "sz",  # ligature sz
    0x00E6: "ae",  # ae
    0x0153: "oe",  # ligature oe
    0x0238: "db",  # db digraph
    0x0239: "qp",  # qp digraph
}


def dupname(node: Element, name: str) -> None:
    node["dupnames"].append(name)
    node["names"].remove(name)


def whitespace_normalize_name(name: str) -> str:
    """Return a whitespace-normalized name."""
    return " ".join(name.split())


fully_normalize_name = whitespace_normalize_name


def serial_escape(value: str) -> str:
    """Escape string values that are elements of a list, for serialization."""
    return value.replace("\\", r"\\").replace(" ", r"\ ")


def pseudo_quoteattr(value: str) -> str:
    """Quote attributes for pseudo-xml"""
    return '"%s"' % value


def get_source_line(node: Node) -> Tuple[Optional[str], Optional[int]]:
    """
    Return the "source" and "line" attributes from the `node` given or from
    its closest ancestor.
    """
    cursor: Optional[Node] = node
    while cursor:
        if cursor.source or cursor.line:
            return cursor.source, cursor.line
        cursor = cursor.parent
    return None, None


class SystemMessage(Exception):
    def __init__(self, system_message: system_message, level: int) -> None:
        Exception.__init__(self, system_message.astext())
        self.level = level


class ErrorOutput:
    def __init__(self, stream: Optional[IO[str]] = None) -> None:
        self.stream = stream or sys.stderr

    def write(self, message: str) -> None:
        self.stream.write(message)


class Reporter:

    """
    Info/warning/error reporter and ``system_message`` element generator.

    Five levels of system messages are defined, along with corresponding
    methods: `debug()`, `info()`, `warning()`, `error()`, and `severe()`.

    There is typically one Reporter object per process.  A Reporter object is
    instantiated with thresholds for reporting (generating warnings) and
    halting processing (raising exceptions), a switch to turn debug output on
    or off, and an I/O stream for warnings.  These are stored as instance
    attributes.

    When a system message is generated, its level is compared to the stored
    thresholds, and a warning or error is generated as appropriate.  Debug
    messages are produced if the stored debug switch is on, independently of
    other thresholds.  Message output is sent to the stored warning stream if
    not set to ''.

    The Reporter class also employs a modified form of the "Observer" pattern
    [GoF95]_ to track system messages generated.  The `attach_observer` method
    should be called before parsing, with a bound method or function which
    accepts system messages.  The observer can be removed with
    `detach_observer`, and another added in its place.

    .. [GoF95] Gamma, Helm, Johnson, Vlissides. *Design Patterns: Elements of
       Reusable Object-Oriented Software*. Addison-Wesley, Reading, MA, USA,
       1995.
    """

    levels = ("DEBUG", "INFO", "WARNING", "ERROR", "SEVERE")
    """List of names for system message levels, indexed by level."""

    # system message level constants:
    (DEBUG_LEVEL, INFO_LEVEL, WARNING_LEVEL, ERROR_LEVEL, SEVERE_LEVEL) = range(5)

    def __init__(
        self,
        source: str,
        report_level: int,
        halt_level: int,
        stream: Optional[Union[IO[str], ErrorOutput]] = None,
        debug: bool = False,
    ) -> None:
        """
        :Parameters:
            - `source`: The path to or description of the source data.
            - `report_level`: The level at or above which warning output will
              be sent to `stream`.
            - `halt_level`: The level at or above which `SystemMessage`
              exceptions will be raised, halting execution.
            - `debug`: Show debug (level=0) system messages?
            - `stream`: Where warning output is sent.  Can be file-like (has a
              ``.write`` method), a string (file name, opened for writing),
              '' (empty string) or `False` (for discarding all stream messages)
              or `None` (implies `sys.stderr`; default).
        """

        self.source = source
        """The path to or description of the source data."""

        self.debug_flag = debug
        """Show debug (level=0) system messages?"""

        self.report_level = report_level
        """The level at or above which warning output will be sent
        to `self.stream`."""

        self.halt_level = halt_level
        """The level at or above which `SystemMessage` exceptions
        will be raised, halting execution."""

        if not isinstance(stream, ErrorOutput):
            stream = ErrorOutput(stream)

        self.stream = stream
        """Where warning output is sent."""

        self.observers: List[Callable[[object], None]] = []
        """List of bound methods or functions to call with each system_message
        created."""

        self.max_level = -1
        """The highest level system message generated so far."""

        self.get_source_and_line: Optional[
            Callable[[Optional[int]], Tuple[str, int]]
        ] = None

    def attach_observer(self, observer: Callable[[object], None]) -> None:
        """
        The `observer` parameter is a function or bound method which takes one
        argument, a `nodes.system_message` instance.
        """
        self.observers.append(observer)

    def detach_observer(self, observer: Callable[[object], None]) -> None:
        self.observers.remove(observer)

    def notify_observers(self, message: object) -> None:
        for observer in self.observers:
            observer(message)

    def make_system_message(
        self, level: int, message: str, *children: ConcreteNode, **kwargs: object
    ) -> system_message:
        """
        Return a system_message object.

        Raise an exception or generate a warning if appropriate.
        """
        attributes = kwargs.copy()
        if "base_node" in kwargs:
            base_node = kwargs["base_node"]
            assert isinstance(base_node, Node)
            source, line = get_source_line(base_node)
            del attributes["base_node"]
            if source is not None:
                attributes.setdefault("source", source)
            if line is not None:
                attributes.setdefault("line", line)
                # assert source is not None, "node has line- but no source-argument"
        if not "source" in attributes:  # 'line' is absolute line number
            try:  # look up (source, line-in-source)
                assert self.get_source_and_line is not None
                source, line = self.get_source_and_line(
                    cast(int, attributes.get("line"))
                )
            except AttributeError:
                source, line = None, None
            if source is not None:
                attributes["source"] = source
            if line is not None:
                attributes["line"] = line
        # assert attributes['line'] is not None, (message, kwargs)
        # assert attributes['source'] is not None, (message, kwargs)
        attributes.setdefault("source", self.source)

        msg = system_message(
            message, level=level, type=self.levels[level], *children, **attributes
        )
        if self.stream and (
            level >= self.report_level
            or self.debug_flag
            and level == self.DEBUG_LEVEL
            or level >= self.halt_level
        ):
            self.stream.write(msg.astext() + "\n")
        if level >= self.halt_level:
            raise SystemMessage(msg, level)
        if level > self.DEBUG_LEVEL or self.debug_flag:
            self.notify_observers(msg)
        self.max_level = max(level, self.max_level)
        return msg

    def debug(
        self, message: str, *args: Any, **kwargs: Any
    ) -> Optional[system_message]:
        """
        Level-0, "DEBUG": an internal reporting issue. Typically, there is no
        effect on the processing. Level-0 system messages are handled
        separately from the others.
        """
        if self.debug_flag:
            return self.make_system_message(self.DEBUG_LEVEL, message, *args, **kwargs)

        return None

    def info(self, message: str, *args: Any, **kwargs: Any) -> system_message:
        """
        Level-1, "INFO": a minor issue that can be ignored. Typically there is
        no effect on processing, and level-1 system messages are not reported.
        """
        return self.make_system_message(self.INFO_LEVEL, message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> system_message:
        """
        Level-2, "WARNING": an issue that should be addressed. If ignored,
        there may be unpredictable problems with the output.
        """
        return self.make_system_message(self.WARNING_LEVEL, message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> system_message:
        """
        Level-3, "ERROR": an error that should be addressed. If ignored, the
        output will contain errors.
        """
        return self.make_system_message(self.ERROR_LEVEL, message, *args, **kwargs)

    def severe(self, message: str, *args: Any, **kwargs: Any) -> system_message:
        """
        Level-4, "SEVERE": a severe error that must be addressed. If ignored,
        the output will contain severe errors. Typically level-4 system
        messages are turned into exceptions which halt processing.
        """
        return self.make_system_message(self.SEVERE_LEVEL, message, *args, **kwargs)


def new_reporter(source_path: str, settings: frontend.OptionParser) -> Reporter:
    """
    Return a new Reporter object.

    :Parameters:
        `source` : string
            The path to or description of the source text of the document.
        `settings` : optparse.Values object
            Runtime settings.
    """
    reporter = Reporter(
        source_path,
        settings.report_level,
        settings.halt_level,
        stream=settings.warning_stream,
        debug=settings.debug,
    )
    return reporter


def new_document(
    source_path: str, settings: Optional[frontend.OptionParser] = None
) -> document:
    """
    Return a new empty document object.

    :Parameters:
        `source_path` : string
            The path to or description of the source text of the document.
        `settings` : optparse.Values object
            Runtime settings.  If none are provided, a default core set will
            be used.  If you will use the document object with any Docutils
            components, you must provide their default settings as well.  For
            example, if parsing rST, at least provide the rst-parser settings,
            obtainable as follows::

                settings = docutils.frontend.OptionParser(
                    components=(docutils.parsers.rst.Parser,)
                    ).get_default_values()
    """
    if settings is None:
        settings = frontend.OptionParser().get_default_values()
    reporter = new_reporter(source_path, settings)
    doc = document(settings, reporter, source=source_path)
    doc.note_source(source_path, -1)
    return doc

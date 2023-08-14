# $Id: __init__.py 8595 2020-12-15 23:06:58Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
This package contains directive implementation modules.
"""

__docformat__ = "reStructuredText"

import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Type, Union

from . import nodes, statemachine, states
from .utils import escape2null, split_escaped_whitespace, unescape


def flag(argument: Optional[str]) -> None:
    """
    Check for a valid flag option (no argument) and return ``None``.
    (Directive option conversion function.)

    Raise ``ValueError`` if an argument is found.
    """
    if argument and argument.strip():
        raise ValueError('no argument is allowed; "%s" supplied' % argument)
    else:
        return None


def path(argument: Optional[str]) -> str:
    """
    Return the path argument unwrapped (with newlines removed).
    (Directive option conversion function.)

    Raise ``ValueError`` if no argument is found.
    """
    if argument is None:
        raise ValueError("argument required but none supplied")
    else:
        path = "".join([s.strip() for s in argument.splitlines()])
        return path


def uri(argument: Optional[str]) -> str:
    """
    Return the URI argument with unescaped whitespace removed.
    (Directive option conversion function.)

    Raise ``ValueError`` if no argument is found.
    """
    if argument is None:
        raise ValueError("argument required but none supplied")
    else:
        parts = split_escaped_whitespace(escape2null(argument))
        uri = " ".join("".join(unescape(part).split()) for part in parts)
        return uri


def nonnegative_int(argument: str) -> int:
    """
    Check for a nonnegative integer argument; raise ``ValueError`` if not.
    (Directive option conversion function.)
    """
    value = int(argument)
    if value < 0:
        raise ValueError("negative value; must be positive or zero")
    return value


length_units = ["em", "ex", "px", "in", "cm", "mm", "pt", "pc"]


def get_measure(argument: str, units: Iterable[str]) -> str:
    """
    Check for a positive argument of one of the units and return a
    normalized string of the form "<value><unit>" (without space in
    between).
    (Directive option conversion function.)

    To be called from directive option conversion functions.
    """
    match = re.match(r"^([0-9.]+) *(%s)$" % "|".join(units), argument)
    try:
        if not match:
            raise ValueError()

        float(match.group(1))
    except ValueError:
        raise ValueError(
            "not a positive measure of one of the following units:\n%s"
            % " ".join(['"%s"' % i for i in units])
        )
    return match.group(1) + match.group(2)


def length_or_percentage_or_unitless(argument: str, default: str = "") -> str:
    """
    Return normalized string of a length or percentage unit.
    (Directive option conversion function.)

    Add <default> if there is no unit. Raise ValueError if the argument is not
    a positive measure of one of the valid CSS units (or without unit).

    >>> length_or_percentage_or_unitless('3 pt')
    '3pt'
    >>> length_or_percentage_or_unitless('3%', 'em')
    '3%'
    >>> length_or_percentage_or_unitless('3')
    '3'
    >>> length_or_percentage_or_unitless('3', 'px')
    '3px'
    """
    try:
        return get_measure(argument, length_units + ["%"])
    except ValueError:
        try:
            return get_measure(argument, [""]) + default
        except ValueError:
            # raise ValueError with list of valid units:
            return get_measure(argument, length_units + ["%"])


unicode_pattern = re.compile(
    r"(?:0x|x|\\x|U\+?|\\u)([0-9a-f]+)$|&#x([0-9a-f]+);$", re.IGNORECASE
)


def unicode_code(code: str) -> str:
    r"""
    Convert a Unicode character code to a Unicode character.
    (Directive option conversion function.)

    Codes may be decimal numbers, hexadecimal numbers (prefixed by ``0x``,
    ``x``, ``\x``, ``U+``, ``u``, or ``\u``; e.g. ``U+262E``), or XML-style
    numeric character entities (e.g. ``&#x262E;``).  Other text remains as-is.

    Raise ValueError for illegal Unicode code values.
    """
    try:
        if code.isdigit():  # decimal number
            return chr(int(code))
        else:
            match = unicode_pattern.match(code)
            if match:  # hex number
                value = match.group(1) or match.group(2)
                return chr(int(value, 16))
            else:  # other text
                return code
    except OverflowError as detail:
        raise ValueError("code too large (%s)" % detail)


def choice(argument: str, values: Sequence[str]) -> str:
    """
    Directive option utility function, supplied to enable options whose
    argument must be a member of a finite set of possible values (must be
    lower case).  A custom conversion function must be written to use it.  For
    example::

        from docutils.parsers.rst import directives

        def yesno(argument):
            return directives.choice(argument, ('yes', 'no'))

    Raise ``ValueError`` if no argument is found or if the argument's value is
    not valid (not an entry in the supplied list).
    """
    try:
        value = argument.lower().strip()
    except AttributeError:
        raise ValueError(
            "must supply an argument; choose from %s" % format_values(values)
        )
    if value in values:
        return value
    else:
        raise ValueError(
            '"%s" unknown; choose from %s' % (argument, format_values(values))
        )


def format_values(values: Sequence[str]) -> str:
    return '%s, or "%s"' % (", ".join(['"%s"' % s for s in values[:-1]]), values[-1])


class DirectiveError(Exception):

    """
    Store a message and a system message level.

    To be thrown from inside directive code.

    Do not instantiate directly -- use `Directive.directive_error()`
    instead!
    """

    def __init__(self, level: int, message: str) -> None:
        """Set error `message` and `level`"""
        Exception.__init__(self)
        self.level = level
        self.msg = message


class Directive:

    """
    Base class for reStructuredText directives.

    The following attributes may be set by subclasses.  They are
    interpreted by the directive parser (which runs the directive
    class):

    - `required_arguments`: The number of required arguments (default:
      0).

    - `optional_arguments`: The number of optional arguments (default:
      0).

    - `final_argument_whitespace`: A boolean, indicating if the final
      argument may contain whitespace (default: False).

    - `option_spec`: A dictionary, mapping known option names to
      conversion functions such as `int` or `float` (default: {}, no
      options).  Several conversion functions are defined in the
      directives/__init__.py module.

      Option conversion functions take a single parameter, the option
      argument (a string or ``None``), validate it and/or convert it
      to the appropriate form.  Conversion functions may raise
      `ValueError` and `TypeError` exceptions.

    - `has_content`: A boolean; True if content is allowed.  Client
      code must handle the case where content is required but not
      supplied (an empty content list will be supplied).

    Arguments are normally single whitespace-separated words.  The
    final argument may contain whitespace and/or newlines if
    `final_argument_whitespace` is True.

    If the form of the arguments is more complex, specify only one
    argument (either required or optional) and set
    `final_argument_whitespace` to True; the client code must do any
    context-sensitive parsing.

    When a directive implementation is being run, the directive class
    is instantiated, and the `run()` method is executed.  During
    instantiation, the following instance variables are set:

    - ``name`` is the directive type or name (string).

    - ``arguments`` is the list of positional arguments (strings).

    - ``options`` is a dictionary mapping option names (strings) to
      values (type depends on option conversion functions; see
      `option_spec` above).

    - ``content`` is a list of strings, the directive content line by line.

    - ``lineno`` is the absolute line number of the first line
      of the directive.

    - ``content_offset`` is the line offset of the first line of the content from
      the beginning of the current input.  Used when initiating a nested parse.

    - ``block_text`` is a string containing the entire directive.

    - ``state`` is the state which called the directive function.

    - ``state_machine`` is the state machine which controls the state which called
      the directive function.

    Directive functions return a list of nodes which will be inserted
    into the document tree at the point where the directive was
    encountered.  This can be an empty list if there is nothing to
    insert.

    For ordinary directives, the list must contain body elements or
    structural elements.  Some directives are intended specifically
    for substitution definitions, and must return a list of `Text`
    nodes and/or inline elements (suitable for inline insertion, in
    place of the substitution reference).  Such directives must verify
    substitution definition context, typically using code like this::

        if not isinstance(state, states.SubstitutionDef):
            error = state_machine.reporter.error(
                'Invalid context: the "%s" directive can only be used '
                'within a substitution definition.' % (name),
                nodes.literal_block(block_text, block_text), line=lineno)
            return [error]
    """

    # There is a "Creating reStructuredText Directives" how-to at
    # <http://docutils.sf.net/docs/howto/rst-directives.html>.  If you
    # update this docstring, please update the how-to as well.

    required_arguments: int = 0
    """Number of required directive arguments."""

    optional_arguments: int = 0
    """Number of optional arguments after the required arguments."""

    final_argument_whitespace: bool = False
    """May the final argument contain whitespace?"""

    option_spec: Optional[Dict[str, Callable[[Optional[str]], object]]] = None
    """Mapping of option names to validator functions."""

    has_content: bool = False
    """May the directive have content?"""

    def __init__(
        self,
        name: str,
        arguments: List[str],
        options: Dict[str, object],
        content: statemachine.StringList,
        lineno: int,
        content_offset: int,
        block_text: str,
        state: "states.RSTState",
        state_machine: statemachine.StateMachine,
    ) -> None:
        self.name = name
        self.arguments = arguments
        self.options = options
        self.content = content
        self.lineno = lineno
        self.content_offset = content_offset
        self.block_text = block_text
        self.state = state
        self.state_machine = state_machine

    def run(self) -> Sequence[nodes.Node]:
        raise NotImplementedError("Must override run() is subclass.")

    # Directive errors:

    def directive_error(self, level: int, message: str) -> DirectiveError:
        """
        Return a DirectiveError suitable for being thrown as an exception.

        Call "raise self.directive_error(level, message)" from within
        a directive implementation to return one single system message
        at level `level`, which automatically gets the directive block
        and the line number added.

        Preferably use the `debug`, `info`, `warning`, `error`, or `severe`
        wrapper methods, e.g. ``self.error(message)`` to generate an
        ERROR-level directive error.
        """
        return DirectiveError(level, message)

    def debug(self, message: str) -> DirectiveError:
        return self.directive_error(0, message)

    def info(self, message: str) -> DirectiveError:
        return self.directive_error(1, message)

    def warning(self, message: str) -> DirectiveError:
        return self.directive_error(2, message)

    def error(self, message: str) -> DirectiveError:
        return self.directive_error(3, message)

    def severe(self, message: str) -> DirectiveError:
        return self.directive_error(4, message)

    # Convenience methods:

    def assert_has_content(self) -> None:
        """
        Throw an ERROR-level DirectiveError if the directive doesn't
        have contents.
        """
        if not self.content:
            raise self.error(
                'Content block expected for the "%s" directive; '
                "none found." % self.name
            )


class Replace(Directive):
    has_content = True

    def run(self) -> Sequence[nodes.Node]:
        if not isinstance(self.state, states.SubstitutionDef):
            raise self.error(
                'Invalid context: the "%s" directive can only be used within '
                "a substitution definition." % self.name
            )
        self.assert_has_content()
        text = "\n".join(self.content)
        element = nodes.Element(text)
        self.state.nested_parse(self.content, self.content_offset, element)
        # element might contain [paragraph] + system_message(s)
        node = None
        messages: List[Union[nodes.Text, nodes.Element]] = []
        for elem in element:
            if not node and isinstance(elem, nodes.paragraph):
                node = elem
            elif isinstance(elem, nodes.system_message):
                elem["backrefs"] = []
                messages.append(elem)
            else:
                raise self.error(
                    'Error in "%s" directive: may contain a single paragraph '
                    "only." % (self.name)
                )
        if node:
            return messages + node.children
        return messages


class Unicode(Directive):
    r"""
    Convert Unicode character codes (numbers) to characters.  Codes may be
    decimal numbers, hexadecimal numbers (prefixed by ``0x``, ``x``, ``\x``,
    ``U+``, ``u``, or ``\u``; e.g. ``U+262E``), or XML-style numeric character
    entities (e.g. ``&#x262E;``).  Text following ".." is a comment and is
    ignored.  Spaces are ignored, and any other text remains as-is.
    """

    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = True
    option_spec = {"trim": flag, "ltrim": flag, "rtrim": flag}

    comment_pattern = re.compile(r"( |\n|^)\.\. ")

    def run(self) -> Sequence[nodes.Node]:
        if not isinstance(self.state, states.SubstitutionDef):
            raise self.error(
                'Invalid context: the "%s" directive can only be used within '
                "a substitution definition." % self.name
            )
        assert isinstance(self.state_machine, states.RSTStateMachine)
        substitution_definition = self.state_machine.node
        if "trim" in self.options:
            substitution_definition.attributes["ltrim"] = 1
            substitution_definition.attributes["rtrim"] = 1
        if "ltrim" in self.options:
            substitution_definition.attributes["ltrim"] = 1
        if "rtrim" in self.options:
            substitution_definition.attributes["rtrim"] = 1
        codes = self.comment_pattern.split(self.arguments[0])[0].split()
        element = nodes.Element()
        for code in codes:
            try:
                decoded = unicode_code(code)
            except ValueError as error:
                raise self.error("Invalid character code: %s\n%s" % (code, error))
            element.append(nodes.Text(decoded))
        return element.children


def directive(
    directive_name: str,
    document: nodes.document,
) -> Optional[Type[Directive]]:
    raise NotImplementedError("No context activated")

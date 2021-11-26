# $Id: __init__.py 8595 2020-12-15 23:06:58Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
This package contains directive implementation modules.
"""

__docformat__ = "reStructuredText"

import codecs
import re
from typing import Optional


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


def unchanged_required(argument: Optional[str]) -> str:
    """
    Return the argument text, unchanged.
    (Directive option conversion function.)

    Raise ``ValueError`` if no argument is found.
    """
    if argument is None:
        raise ValueError("argument required but none supplied")
    else:
        return argument  # unchanged!


def unchanged(argument: Optional[str]) -> str:
    """
    Return the argument text, unchanged.
    (Directive option conversion function.)

    No argument implies empty string ("").
    """
    if argument is None:
        return ""
    else:
        return argument  # unchanged!


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


def nonnegative_int(argument: Optional[str]) -> str:
    """
    Check for a nonnegative integer argument; raise ``ValueError`` if not.
    (Directive option conversion function.)
    """
    value = int(argument)
    if value < 0:
        raise ValueError("negative value; must be positive or zero")
    return value


def percentage(argument: Optional[str]) -> str:
    """
    Check for an integer percentage value with optional percent sign.
    (Directive option conversion function.)
    """
    try:
        argument = argument.rstrip(" %")
    except AttributeError:
        pass
    return nonnegative_int(argument)


length_units = ["em", "ex", "px", "in", "cm", "mm", "pt", "pc"]


def get_measure(argument, units):
    """
    Check for a positive argument of one of the units and return a
    normalized string of the form "<value><unit>" (without space in
    between).
    (Directive option conversion function.)

    To be called from directive option conversion functions.
    """
    match = re.match(r"^([0-9.]+) *(%s)$" % "|".join(units), argument)
    try:
        float(match.group(1))
    except (AttributeError, ValueError):
        raise ValueError(
            "not a positive measure of one of the following units:\n%s"
            % " ".join(['"%s"' % i for i in units])
        )
    return match.group(1) + match.group(2)


def length_or_unitless(argument):
    return get_measure(argument, length_units + [""])


def length_or_percentage_or_unitless(argument, default=""):
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


def class_option(argument):
    """
    Convert the argument into a list of ID-compatible strings and return it.
    (Directive option conversion function.)

    Raise ``ValueError`` if no argument is found.
    """
    if argument is None:
        raise ValueError("argument required but none supplied")
    names = argument.split()
    class_names = []
    for name in names:
        class_name = nodes.make_id(name)
        if not class_name:
            raise ValueError('cannot make "%s" into a class name' % name)
        class_names.append(class_name)
    return class_names


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


def single_char_or_unicode(argument: str) -> str:
    """
    A single character is returned as-is.  Unicode characters codes are
    converted as in `unicode_code`.  (Directive option conversion function.)
    """
    char = unicode_code(argument)
    if len(char) > 1:
        raise ValueError(
            "%r invalid; must be a single character or " "a Unicode code" % char
        )
    return char


def single_char_or_whitespace_or_unicode(argument):
    """
    As with `single_char_or_unicode`, but "tab" and "space" are also supported.
    (Directive option conversion function.)
    """
    if argument == "tab":
        char = "\t"
    elif argument == "space":
        char = " "
    else:
        char = single_char_or_unicode(argument)
    return char


def positive_int(argument):
    """
    Converts the argument into an integer.  Raises ValueError for negative,
    zero, or non-integer values.  (Directive option conversion function.)
    """
    value = int(argument)
    if value < 1:
        raise ValueError("negative or zero value; must be positive")
    return value


def positive_int_list(argument):
    """
    Converts a space- or comma-separated list of values into a Python list
    of integers.
    (Directive option conversion function.)

    Raises ValueError for non-positive-integer values.
    """
    if "," in argument:
        entries = argument.split(",")
    else:
        entries = argument.split()
    return [positive_int(entry) for entry in entries]


def encoding(argument):
    """
    Verfies the encoding argument by lookup.
    (Directive option conversion function.)

    Raises ValueError for unknown encodings.
    """
    try:
        codecs.lookup(argument)
    except LookupError:
        raise ValueError('unknown encoding: "%s"' % argument)
    return argument


def choice(argument, values):
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


def format_values(values):
    return '%s, or "%s"' % (", ".join(['"%s"' % s for s in values[:-1]]), values[-1])


def value_or(values, other):
    """
    Directive option conversion function.

    The argument can be any of `values` or `argument_type`.
    """

    def auto_or_other(argument):
        if argument in values:
            return argument
        else:
            return other(argument)

    return auto_or_other


def parser_name(argument):
    """
    Return a docutils parser whose name matches the argument.
    (Directive option conversion function.)

    Return `None`, if the argument evaluates to `False`.
    """
    if not argument:
        return None
    try:
        return parsers.get_parser_class(argument)
    except ImportError:
        raise ValueError('Unknown parser name "%s".' % argument)

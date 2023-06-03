# coding: utf-8
# $Id: __init__.py 8672 2021-04-07 12:10:06Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
Miscellaneous utilities for the documentation utilities.
"""

__docformat__ = "reStructuredText"

import itertools
import sys
import unicodedata
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from . import nodes


class DataError(Exception):
    pass


class ExtensionOptionError(DataError):
    pass


class BadOptionDataError(ExtensionOptionError):
    pass


class DuplicateOptionError(ExtensionOptionError):
    pass


class BadOptionError(ExtensionOptionError):
    pass


def extract_extension_options(
    field_list: nodes.field_list,
    options_spec: Mapping[str, Callable[[Optional[str]], object]],
) -> Dict[str, object]:
    """
    Return a dictionary mapping extension option names to converted values.

    :Parameters:
        - `field_list`: A flat field list without field arguments, where each
          field body consists of a single paragraph only.
        - `options_spec`: Dictionary mapping known option names to a
          conversion function such as `int` or `float`.

    :Exceptions:
        - `KeyError` for unknown option names.
        - `ValueError` for invalid option values (raised by the conversion
           function).
        - `TypeError` for invalid option value types (raised by conversion
           function).
        - `DuplicateOptionError` for duplicate options.
        - `BadOptionError` for invalid fields.
        - `BadOptionDataError` for invalid option data (missing name,
          missing data, bad quotes, etc.).
    """
    option_list = extract_options(field_list)
    option_dict = assemble_option_dict(option_list, options_spec)
    return option_dict


def extract_options(
    field_list: nodes.field_list,
) -> Sequence[Tuple[str, Optional[str]]]:
    """
    Return a list of option (name, value) pairs from field names & bodies.

    :Parameter:
        `field_list`: A flat field list, where each field name is a single
        word and each field body consists of a single paragraph only.

    :Exceptions:
        - `BadOptionError` for invalid fields.
        - `BadOptionDataError` for invalid option data (missing name,
          missing data, bad quotes, etc.).
    """
    option_list = []
    for field in field_list:
        assert isinstance(field, nodes.field)
        if len(field[0].astext().split()) != 1:
            raise BadOptionError(
                "extension option field name may not contain multiple words"
            )
        name = str(field[0].astext().lower())
        body = field[1]
        if len(body) == 0:
            data = None
        elif (
            len(body) > 1
            or not isinstance(body[0], nodes.paragraph)
            or len(body[0]) != 1
            or not isinstance(body[0][0], nodes.Text)
        ):
            raise BadOptionDataError(
                "extension option field body may contain\n"
                'a single paragraph only (option "%s")' % name
            )
        else:
            data = body[0][0].astext()
        option_list.append((name, data))
    return option_list


def assemble_option_dict(
    option_list: Iterable[Tuple[str, Optional[str]]],
    options_spec: Mapping[str, Callable[[Optional[str]], object]],
) -> Dict[str, object]:
    """
    Return a mapping of option names to values.

    :Parameters:
        - `option_list`: A list of (name, value) pairs (the output of
          `extract_options()`).
        - `options_spec`: Dictionary mapping known option names to a
          conversion function such as `int` or `float`.

    :Exceptions:
        - `KeyError` for unknown option names.
        - `DuplicateOptionError` for duplicate options.
        - `ValueError` for invalid option values (raised by conversion
           function).
        - `TypeError` for invalid option value types (raised by conversion
           function).
    """
    options = {}
    for name, value in option_list:
        convertor = options_spec[name]  # raises KeyError if unknown
        if convertor is None:
            raise KeyError(name)  # or if explicitly disabled
        if name in options:
            raise DuplicateOptionError('duplicate option "%s"' % name)
        try:
            options[name] = convertor(value)
        except (ValueError, TypeError) as detail:
            raise detail.__class__(
                '(option: "%s"; value: %r)\n%s' % (name, value, " ".join(detail.args))
            )
    return options


def escape2null(text: str) -> str:
    """Return a string with escape-backslashes converted to nulls."""
    parts = []
    start = 0
    while True:
        found = text.find("\\", start)
        if found == -1:
            parts.append(text[start:])
            return "".join(parts)
        parts.append(text[start:found])
        parts.append("\x00" + text[found + 1 : found + 2])
        start = found + 2  # skip character after escape


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


def split_escaped_whitespace(text: str) -> Sequence[str]:
    """
    Split `text` on escaped whitespace (null+space or null+newline).
    Return a list of strings.
    """
    strings = text.split("\x00 ")
    # flatten list of lists of strings to list of strings:
    return list(itertools.chain(*[string.split("\x00\n") for string in strings]))


def find_combining_chars(text: str) -> Sequence[int]:
    """Return indices of all combining chars in  Unicode string `text`.

    >>> from docutils.utils import find_combining_chars
    >>> find_combining_chars(u'A t̆ab̆lĕ')
    [3, 6, 9]

    """
    return [i for i, c in enumerate(text) if unicodedata.combining(c)]


east_asian_widths = {
    "W": 2,  # Wide
    "F": 2,  # Full-width (wide)
    "Na": 1,  # Narrow
    "H": 1,  # Half-width (narrow)
    "N": 1,  # Neutral (not East Asian, treated as narrow)
    "A": 1,
}  # Ambiguous (s/b wide in East Asian context,
# narrow otherwise, but that doesn't work)
"""Mapping of result codes from `unicodedata.east_asian_widt()` to character
column widths."""


def column_width(text: str) -> int:
    """Return the column width of text.

    Correct ``len(text)`` for wide East Asian and combining Unicode chars.
    """
    if isinstance(text, str) and sys.version_info < (3, 0):
        return len(text)
    width = sum([east_asian_widths[unicodedata.east_asian_width(c)] for c in text])
    # correction for combining chars:
    width -= len(find_combining_chars(text))
    return width


class PunctuationChars:
    """Docutils character category patterns.

    Patterns for the implementation of the `inline markup recognition rules`_
    in the reStructuredText parser `docutils.parsers.rst.states.py` based
    on Unicode character categories.
    The patterns are used inside ``[ ]`` in regular expressions.

    Rule (5) requires determination of matching open/close pairs. However, the
    pairing of open/close quotes is ambiguous due to  different typographic
    conventions in different languages. The ``quote_pairs`` function tests
    whether two characters form an open/close pair.

    The patterns are generated by
    ``docutils/tools/dev/generate_punctuation_chars.py`` to  prevent dependence
    on the Python version and avoid the time-consuming generation with every
    Docutils run. See there for motives and implementation details.

    The category of some characters changed with the development of the
    Unicode standard. The current lists are generated with the help of the
    "unicodedata" module of Python 2.7.13 (based on Unicode version 5.2.0).

    .. _inline markup recognition rules:
        http://docutils.sf.net/docs/ref/rst/restructuredtext.html#inline-markup-recognition-rules
    """

    openers = (
        "\"'(<\\[{\u0f3a\u0f3c\u169b\u2045\u207d\u208d\u2329\u2768"
        "\u276a\u276c\u276e\u2770\u2772\u2774\u27c5\u27e6\u27e8\u27ea"
        "\u27ec\u27ee\u2983\u2985\u2987\u2989\u298b\u298d\u298f\u2991"
        "\u2993\u2995\u2997\u29d8\u29da\u29fc\u2e22\u2e24\u2e26\u2e28"
        "\u3008\u300a\u300c\u300e\u3010\u3014\u3016\u3018\u301a\u301d"
        "\u301d\ufd3e\ufe17\ufe35\ufe37\ufe39\ufe3b\ufe3d\ufe3f\ufe41"
        "\ufe43\ufe47\ufe59\ufe5b\ufe5d\uff08\uff3b\uff5b\uff5f\uff62"
        "\xab\u2018\u201c\u2039\u2e02\u2e04\u2e09\u2e0c\u2e1c\u2e20"
        "\u201a\u201e\xbb\u2019\u201d\u203a\u2e03\u2e05\u2e0a\u2e0d"
        "\u2e1d\u2e21\u201b\u201f"
    )
    closers = (
        "\"')>\\]}\u0f3b\u0f3d\u169c\u2046\u207e\u208e\u232a\u2769"
        "\u276b\u276d\u276f\u2771\u2773\u2775\u27c6\u27e7\u27e9\u27eb"
        "\u27ed\u27ef\u2984\u2986\u2988\u298a\u298c\u298e\u2990\u2992"
        "\u2994\u2996\u2998\u29d9\u29db\u29fd\u2e23\u2e25\u2e27\u2e29"
        "\u3009\u300b\u300d\u300f\u3011\u3015\u3017\u3019\u301b\u301e"
        "\u301f\ufd3f\ufe18\ufe36\ufe38\ufe3a\ufe3c\ufe3e\ufe40\ufe42"
        "\ufe44\ufe48\ufe5a\ufe5c\ufe5e\uff09\uff3d\uff5d\uff60\uff63"
        "\xbb\u2019\u201d\u203a\u2e03\u2e05\u2e0a\u2e0d\u2e1d\u2e21"
        "\u201b\u201f\xab\u2018\u201c\u2039\u2e02\u2e04\u2e09\u2e0c"
        "\u2e1c\u2e20\u201a\u201e"
    )
    delimiters = (
        "\\-/:\u058a\xa1\xb7\xbf\u037e\u0387\u055a-\u055f\u0589"
        "\u05be\u05c0\u05c3\u05c6\u05f3\u05f4\u0609\u060a\u060c"
        "\u060d\u061b\u061e\u061f\u066a-\u066d\u06d4\u0700-\u070d"
        "\u07f7-\u07f9\u0830-\u083e\u0964\u0965\u0970\u0df4\u0e4f"
        "\u0e5a\u0e5b\u0f04-\u0f12\u0f85\u0fd0-\u0fd4\u104a-\u104f"
        "\u10fb\u1361-\u1368\u1400\u166d\u166e\u16eb-\u16ed\u1735"
        "\u1736\u17d4-\u17d6\u17d8-\u17da\u1800-\u180a\u1944\u1945"
        "\u19de\u19df\u1a1e\u1a1f\u1aa0-\u1aa6\u1aa8-\u1aad\u1b5a-"
        "\u1b60\u1c3b-\u1c3f\u1c7e\u1c7f\u1cd3\u2010-\u2017\u2020-"
        "\u2027\u2030-\u2038\u203b-\u203e\u2041-\u2043\u2047-"
        "\u2051\u2053\u2055-\u205e\u2cf9-\u2cfc\u2cfe\u2cff\u2e00"
        "\u2e01\u2e06-\u2e08\u2e0b\u2e0e-\u2e1b\u2e1e\u2e1f\u2e2a-"
        "\u2e2e\u2e30\u2e31\u3001-\u3003\u301c\u3030\u303d\u30a0"
        "\u30fb\ua4fe\ua4ff\ua60d-\ua60f\ua673\ua67e\ua6f2-\ua6f7"
        "\ua874-\ua877\ua8ce\ua8cf\ua8f8-\ua8fa\ua92e\ua92f\ua95f"
        "\ua9c1-\ua9cd\ua9de\ua9df\uaa5c-\uaa5f\uaade\uaadf\uabeb"
        "\ufe10-\ufe16\ufe19\ufe30-\ufe32\ufe45\ufe46\ufe49-\ufe4c"
        "\ufe50-\ufe52\ufe54-\ufe58\ufe5f-\ufe61\ufe63\ufe68\ufe6a"
        "\ufe6b\uff01-\uff03\uff05-\uff07\uff0a\uff0c-\uff0f\uff1a"
        "\uff1b\uff1f\uff20\uff3c\uff61\uff64\uff65"
    )
    if sys.maxunicode >= 0x10FFFF:  # "wide" build
        delimiters += (
            "\U00010100\U00010101\U0001039f\U000103d0\U00010857"
            "\U0001091f\U0001093f\U00010a50-\U00010a58\U00010a7f"
            "\U00010b39-\U00010b3f\U000110bb\U000110bc\U000110be-"
            "\U000110c1\U00012470-\U00012473"
        )
    closing_delimiters = "\\\\.,;!?"

    # Matching open/close quotes
    # --------------------------

    quote_pairs = {  # open char: matching closing characters # usage example
        "\xbb": "\xbb",  # » » Swedish
        "\u2018": "\u201a",  # ‘ ‚ Albanian/Greek/Turkish
        "\u2019": "\u2019",  # ’ ’ Swedish
        "\u201a": "\u2018\u2019",  # ‚ ‘ German ‚ ’ Polish
        "\u201c": "\u201e",  # “ „ Albanian/Greek/Turkish
        "\u201e": "\u201c\u201d",  # „ “ German „ ” Polish
        "\u201d": "\u201d",  # ” ” Swedish
        "\u203a": "\u203a",  # › › Swedish
    }
    """Additional open/close quote pairs."""

    @classmethod
    def match_chars(cls, c1: str, c2: str) -> bool:
        """Test whether `c1` and `c2` are a matching open/close character pair.

        Matching open/close pairs are at the same position in
        `punctuation_chars.openers` and `punctuation_chars.closers`.
        The pairing of open/close quotes is ambiguous due to  different
        typographic conventions in different languages,
        so we test for additional matches stored in `quote_pairs`.
        """
        try:
            i = cls.openers.index(c1)
        except ValueError:  # c1 not in openers
            return False
        return c2 == cls.closers[i] or c2 in cls.quote_pairs.get(c1, "")

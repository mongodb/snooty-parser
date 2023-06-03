"""Incredibly abbreviated roman numeral lookup functions from the range I..XX."""

from typing import Sequence

ROMAN_NUMERALS: Sequence[str] = (
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VII",
    "IX",
    "X",
    "XI",
    "XII",
    "XIII",
    "XIV",
    "XV",
    "XVI",
    "XVII",
    "XVIII",
    "XIX",
    "XX",
)


def to_roman(n: int) -> str:
    if n < 1 or n > len(ROMAN_NUMERALS):
        raise ValueError(f"{n} not in range 0 < n < {len(ROMAN_NUMERALS)}")

    return ROMAN_NUMERALS[n - 1]


def from_roman(s: str) -> int:
    try:
        return ROMAN_NUMERALS.index(s) + 1
    except ValueError:
        raise ValueError(f"'{s}' is not a known roman numeral")

#!/usr/bin/env python3
import datetime
import re
import sys
from typing import List, NoReturn, Optional, Tuple

FILENAME = sys.argv[1]
VERSION_PAT = re.compile(
    r"^## \[(?P<version>v\d+\.\d+\.\d+)\] - (?P<date>\d+\-\d+\-\d+)$"
)
HEADING_PATTERN = re.compile(r"\n\n?#+[^\n]+\n\n?")
H3_SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
H3_SECTION_STRING = ", ".join(H3_SECTIONS)


class InputError(Exception):
    pass


def fail(lineno: int, message: str) -> NoReturn:
    """Print a message about an input line to stderr, and exit."""
    print(f"{FILENAME}:{lineno}: {message}", file=sys.stderr)
    raise InputError(lineno)


def lint_changelog(data: str) -> None:
    """Verify a changelog string."""
    heading_structure: List[Tuple[int, int]] = []
    last_h3: Optional[str] = None
    consecutive_blank_lines = 0

    for i, line in enumerate(data.split("\n"), start=1):
        # No more than two consecutive blank lines
        if not line.strip():
            consecutive_blank_lines += 1
            if consecutive_blank_lines == 2:
                fail(i, "Too many consecutive blank lines")
            continue
        consecutive_blank_lines = 0

        # Check headings
        if line.startswith("#"):
            heading_structure.append((i, line.count("#")))

        if line.startswith("# "):
            if line != "# Changelog":
                fail(i, "Bad heading")
            if i != 1:
                fail(i, "First line should be '# Changelog'")
        elif line.startswith("## "):
            last_h3 = None
            if line == "## [Unreleased]":
                continue
            match = VERSION_PAT.match(line)
            if not match:
                fail(
                    i,
                    "Bad version name: should either be '## [Unreleased]', or follow '## [MAJOR.MINOR.PATCH] - YYYY-MM-DD'",
                )
            date_string = match["date"]
            try:
                datetime.datetime.fromisoformat(date_string)
            except ValueError as err:
                fail(i, f"Error parsing release date '{date_string}': {err}")
        elif line.startswith("### "):
            section_name = line[4:]
            if section_name in H3_SECTIONS:
                if last_h3 and last_h3 >= section_name:
                    fail(i, f"Sections out of order; must go {H3_SECTION_STRING}")
            else:
                fail(i, f"Must be one of {H3_SECTION_STRING}")
            last_h3 = section_name
        elif line.startswith("#"):
            fail(i, f"Bad heading on line {i}")

    # Check heading structure
    for depth, next_depth in zip(heading_structure, heading_structure[1:]):
        if abs(depth[1] - next_depth[1]) > 1:
            fail(next_depth[0], "Incorrect section structure")

    # Ensure that headings are surrounded by newlines
    for match in HEADING_PATTERN.finditer(data):
        match_text = match.group(0)
        if not match_text.startswith("\n\n"):
            lineno = data[: match.start() + 1].count("\n") + 1
            fail(lineno, "Headings must be preceded by a blank line")
        if not match_text.endswith("\n\n"):
            lineno = data[: match.end() - 1].count("\n") + 1
            fail(lineno, "Headings must be succeeded by a blank line")


def main() -> None:
    with open(sys.argv[1]) as f:
        data = f.read()

    try:
        lint_changelog(data)
    except InputError:
        sys.exit(1)


if __name__ == "__main__":
    main()

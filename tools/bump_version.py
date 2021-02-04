#!/usr/bin/env python3
import datetime
import re
import sys
from pathlib import Path
from typing import Match

CHANGELOG_PATH = Path("CHANGELOG.md")
INCOMING_VERISON_PAT = re.compile(r"\d+\.\d+\.\d+")
PAT = re.compile(r'"(\d+\.\d+\.\S+)"')
CHANGELOG_UNRELEASED_PAT = re.compile(
    r"\n## \[Unreleased\](?P<unreleased>.*)(?=\n## )", re.DOTALL
)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two semver-style version strings, returning -1 if v1 < v2; +1
    if v1 > v2; or 0 if the two version strings are equal."""
    parts1 = v1.split(".")
    parts2 = v2.split(".")

    # Zero-fill the parts to the same length
    length_difference = abs(len(parts1) - len(parts2))
    if length_difference > 0:
        if len(parts1) < len(parts2):
            parts1.extend(["0"] * length_difference)
        elif len(parts2) < len(parts1):
            parts2.extend(["0"] * length_difference)

    # Compare each part
    for part1, part2 in zip((int(x) for x in parts1), (int(x) for x in parts2)):
        if part1 < part2:
            return -1
        elif part1 > part2:
            return 1

    return 0


def release_changelog(version: str, text: str) -> str:
    """Update a ChangeLog string matching the "Keep a Changelog" format so that
    anything in the [Unreleased] section is added to a new version section."""
    date_string = datetime.datetime.now().strftime("%Y-%m-%d")

    def replace(match: Match[str]) -> str:
        unreleased_block = match["unreleased"].strip()
        return f"\n## [Unreleased]\n\n## [v{version}] - {date_string}\n\n{unreleased_block}\n"

    result = CHANGELOG_UNRELEASED_PAT.sub(replace, text)
    if not result:
        raise ValueError("Could not find [Unreleased] section to release")

    return result


def main() -> None:
    version_to_bump_to = sys.argv[1] if sys.argv[1] != "dev" else None
    if version_to_bump_to is not None:
        if not INCOMING_VERISON_PAT.match(version_to_bump_to):
            print(
                f'Invalid incoming version string "{version_to_bump_to}"; expected e.g. "0.1.2"',
                file=sys.stderr,
            )
            sys.exit(1)

    def replace(match: Match[str]) -> str:
        nonlocal version_to_bump_to
        current_version = match[1]
        if version_to_bump_to is not None:
            if compare_versions(version_to_bump_to, current_version) <= 0:
                print(
                    f"Cannot bump to an earlier version number: {version_to_bump_to} <= {current_version}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            version_to_bump_to = current_version + ".dev"

        return f'"{version_to_bump_to}"'

    with Path("snooty/__init__.py").open("r+") as f:
        data = f.read()
        data, n_replaced = PAT.subn(replace, data)
        if n_replaced != 1:
            print(
                "Error bumping version: expected 1 version string in __init__.py",
                file=sys.stderr,
            )
            sys.exit(1)
        f.seek(0)
        f.truncate(0)
        f.write(data)

    if version_to_bump_to is not None and ".dev" not in version_to_bump_to:
        try:
            new_changelog = release_changelog(
                version_to_bump_to, CHANGELOG_PATH.read_text()
            )
        except ValueError as err:
            print(str(err), file=sys.stderr)
            sys.exit(1)
        CHANGELOG_PATH.write_text(new_changelog)


if __name__ == "__main__":
    main()

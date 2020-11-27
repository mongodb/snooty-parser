import datetime

from bump_version import compare_versions, release_changelog

DATE_STRING = datetime.datetime.now().strftime("%Y-%m-%d")


def test_compare_versions() -> None:
    assert compare_versions("0.2.0", "0.1.4") == 1
    assert compare_versions("0.1.1", "0.1.2") == -1
    assert compare_versions("0.1.1", "0.1") == 1
    assert compare_versions("0.1.0", "0.1") == 0


def test_release_changelog() -> None:
    TEST_INPUT1 = """# Changelog

## [Unreleased]

### Added

- Add support for the ### following reStructuredText constructs:

### Changed

- Directive "flag" options have a true value in the AST instead of null (DOCSP-6383).

## [v0.1.12] - 2019-07-25

### Added

- No longer create spurious diagnostics about including apiargs artifacts and `hash.rst`."""

    assert (
        release_changelog("0.1.13", TEST_INPUT1)
        == f"""# Changelog

## [Unreleased]

## [v0.1.13] - {DATE_STRING}

### Added

- Add support for the ### following reStructuredText constructs:

### Changed

- Directive "flag" options have a true value in the AST instead of null (DOCSP-6383).

## [v0.1.12] - 2019-07-25

### Added

- No longer create spurious diagnostics about including apiargs artifacts and `hash.rst`."""
    )

from lint_changelog import InputError, lint_changelog


def test_opening_line() -> None:
    try:
        lint_changelog("\n# Changelog")
    except InputError as err:
        assert err.args[0] == 2
    else:
        assert False

    try:
        lint_changelog("# Changeog")
    except InputError as err:
        assert err.args[0] == 1
    else:
        assert False


def test_bad_unreleased() -> None:
    try:
        lint_changelog(
            """# Changelog

## [Unreleased

### Added

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 3
    else:
        assert False


def test_bad_date() -> None:
    try:
        lint_changelog(
            """# Changelog

## [v0.1.1] - 2019-10-50

### Added

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 3
    else:
        assert False


def test_out_of_order() -> None:
    try:
        lint_changelog(
            """# Changelog

## [Unreleased]

### Fixed

- Support for reStructuredText footnotes (DOCSP-6620).

### Added

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 9
    else:
        assert False


def test_incorrect_structure() -> None:
    try:
        lint_changelog(
            """# Changelog

### Added

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 3
    else:
        assert False

    try:
        lint_changelog(
            """# Changelog

## [Unreleased]

### Aded

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 5
    else:
        assert False

    try:
        lint_changelog(
            """# Changelog

##[Unreleased]

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 3
    else:
        assert False


def test_incorrect_newline() -> None:
    try:
        lint_changelog(
            """# Changelog

## [Unreleased]
- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 3
    else:
        assert False

    try:
        lint_changelog(
            """# Changelog
## [Unreleased]

- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 2
    else:
        assert False

    try:
        lint_changelog(
            """# Changelog

## [Unreleased]


- Support for reStructuredText footnotes (DOCSP-6620).
"""
        )
    except InputError as err:
        assert err.args[0] == 5
    else:
        assert False

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.1.9] - 2019-07-08

### Added

- Add `textDocument/resolve` RPC endpoint to return the source file path of an artifact relative to the project's root (DOCSP-5967).

### Fixed

- Don't throw exception if saving an asset to the server fails (DOCSP-5998).
- The language server can now be gracefully shutdown using a context manager,
  for use in tests.

### Changed

- Diagnostic messages when failing to open a static asset are more succinct.
- Warn about YAML files with duplicated refs (DOCSP-5704).

## [v0.1.8] - 2019-06-27

### Added

- Add support for the following roles:

  - `api`
  - `aws`
  - `gettingstarted`
  - `master`
  - `docsgithub`
  - `guides`
  - `mms-docs`
  - `mms-home`
  - `mongo-spark`
  - `source`
  - `opsmgr`
  - `charts-v0.10`
  - `charts-v0.9`

### Fixed

- The full `dns` package is included in binary builds, letting them connect to the database.

### Changed

- Avoid unnecessarily reprocessing figures and literal includes.
- Automatically rebuild files if their dependent assets change.
- Heading nodes now have an attached ID.

## [v0.1.7] - 2019-05-21

### Added

- Add support for the following directives:

  - `image`
  - `tabs-pillstrip`
  - `tabs-cloud-providers`
  - `website`
  - `cloudmgr`
  - `stitch`
  - `charts`
  - `compass`
  - `driver`
  - `meta`
  - `topic`

### Fixed

- `raw` directive contents are now ignored.
- Bundle `docutils.parsers.rst.directives.misc` in binary release to avoid runtime errors when using `unicode`.

### Changed

- Avoid processing giza substitutions in base nodes to avoid superfluous diagnostics.

## [v0.1.6] - 2019-05-16

### Added

- The `literalinclude` directive.
- AST nodes for substitutions.

### Changed

- Only match PAT_EXPLICIT_TILE if needed by role.

  Roles are now categorized in one of three ways:
  - `text` roles only provide a label field in the AST.
  - `explicit_title` roles provide a target field in the AST, as well as
    optionally a label field.
  - `link` roles do not emit a role node at all; instead, they emit a
    reference with the refuri already set.

### Fixed

- Multiline directive arguments.
- Include guide "languages" in legacy guide syntax.
- `:dedent:` on `literalinclude` directives with empty lines.
- Child giza nodes should not always have their parent's ref.
- Extracts should be created with the category `extracts`, not `extract`.

## [v0.1.5] - 2019-03-28

### Added

- Support additional directives and roles

## [v0.1.4] - 2019-03-28

### Added

- Bundle Python hash function implementations temporarily.
- Add support for additional MongoDB rst constructs.

## [v0.1.3] - 2019-03-27

### Added

- Substitute constants from language-server.
- Report bad project config.
- Force encodings to utf-8.

## [v0.1.2] - 2019-03-27

### Added

- Bundle OpenSSL with the macOS binary release.

## [v0.1.1] - 2019-03-22

### Added

- Bundle Python with the binary release.

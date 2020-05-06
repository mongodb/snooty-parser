# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.4.6] - 2020-05-06

### Added

- Support for the glossery directive (DOP-888).
- Optional support for logging diagnostics as JSON objects (DOP-969).

### Changed

- The optional patch ID is now written to the metadata document.

## [v0.4.5] - 2020-04-29

### Fixed

- Support for links in step file headings (DOP-1015).
- Incorrect AST output with hyperlink references (DOP-1056).

## [v0.4.4] - 2020-04-21

### Added

- Support for deprecated versions (DOP-908).

### Fixed

- Definition list AST format.
- The code block `linenos` option is now correctly placed in the AST node.

## [v0.4.3] - 2020-04-15

### Added

- Added `spec` role.
- Added support for various roles & directive options.
- Added support for passing a patch ID into the build identifier (DOP-948).
- The `std:doc` role now emits `RefRole` nodes rather than `Role`, and titles are now
  resolved in the parser (DOP-954).

### Changed

- Diagnostic refactoring (DOP-878).
- The `doc` role is now in the `std` domain.

## [v0.4.2] - 2020-04-03

### Added

- Various roles.

### Changed

- C# driver extlinks now point to 2.10.
- Scala driver extlinks now point to 2.9.

## [v0.4.1] - 2020-04-02

### Added

- Various roles and directive options.

### Changed

- Prefer canonical target names in the AST: e.g. `mongod.-v` over `-v` (DOP-881).

### Fixed

- Skip incomplete target nodes, resolving a crash. (DOP-891).

## [v0.4.0] - 2020-03-23

### Added

- Program & Option handling (DOCSP-8449).
- Enforce ISO 8061 dates (DOCSPLAT-825).
- Support multiple authors.
- Various roles & directives.

### Changed

- The AST is now constructed with a formally specified object-oriented structure.

## [v0.3.6] - 2020-03-03

### Fixed

- Fix `ref_role` nodes with an explicit title.

## [v0.3.5] - 2020-03-03

### Added

- Populate substitution nodes in postprocess layer (DOCSPLAT-114).
- Support for option and program rstobjects (DOCSP-8449).

### Fixed

- Fix devhub image handling (DOCSPLAT-861).

## [v0.3.4] - 2020-02-27

### Removed

- DevHub series directive.

## [v0.3.2] - 2020-02-24

### Fixed

- Devhub directive resolution and behavior.

## [v0.3.1] - 2020-02-14

### Added

- Directives for DevHub (DOCSP-8848).
- Tab sets for Realm (DOCSP-8787).

## [v0.3.0] - 2020-02-09

### Added

- Support for defining a project's title (DOCSP-7988).
- Support for defining a project's default domain (DOCSP-8723).
- Support for DevHub template directives (DOCSP-8723).
- Support for Python 3.8 (DOCSP-7399).
- Support for injecting formatting into ref_role nodes (DOCSP-7569).

### Changed

- Incomplete targets are now an error: for example,
  ```
  `universal link <ios-universal-links_>`_
  ```

### Fixed

- Directives may now have a "name" option, suppressing the docutils
  special-case behavior.
- Fix crashing around snooty.toml (DOCSP-8389).

## [v0.2.0] - 2020-01-23

### Added

- Target/Ref validation & resolution (DOCSP-5776, DOCSP-6657).

- Commit IDs may now be passed into the parser (DOCSP-8277).

### Changed

- Domains are now included in AST nodes when relevant.

## [v0.1.16] - 2019-12-20

### Added

- Support for defining non-drawer TOC nodes via `toc_landing_pages` array in snooty.toml (DOCSP-7573).

### Fixed

- Inconsistent YAML output filenames leading to broken page previews (DOCSP-8084).

## [v0.1.15] - 2019-12-05

### Added

- The following extlink roles:

  - `fb-dev-docs`
  - `fcm`
  - `google-dev`
  - `google-android-ref`
  - `github`
  - `github-dev`
  - `electricimp`
  - `twilio`
  - `mdn`
  - `aws-go`
  - `aws-iam`
  - `aws-reference`
  - `reactjs`
  - `jwt-io`

- More semantic analysis postprocessing infrastructure (DOCSP-7574).

- A new release process (DOCSP-7800).

### Fixed

- Don't crash if opening an empty project.

## [v0.1.14] - 2019-11-19

### Added

- Added infrastructure to support editor preview.

- Added infrastructure to support TOC generation.

- Added diagnostic for merge conflict markers.

- Parse published-branches.yaml and persist data to a metadata collection (DOCSP-7193).

### Fixed

- Parsing of extract filenames that include periods (DOCSP-6904).

- Miscellaneous reStructuredText support improvements.

- Properly report snooty.toml errors.

## [v0.1.13] - 2019-09-23

### Added

- Support for reStructuredText footnotes (DOCSP-6620).

- Support for project-wide reStructuredText substitutions (DOCSP-6442).

- Support for downloading and ingesting intersphinx inventories (DOCSP-5776).

- Validation for links under the `doc` role (DOCSP-6190).

- Support for the following reStructuredText constructs:

  - `datalakeconf` rstobject
  - `caption` option to `toctree`
  - `includehidden` option to `toctree`
  - `backlinks` option to `contents` is an enum
  - `gcp` and `azure` extlinks
  - `only` directive
  - `tab` directive accepts a `tabid` option (DOCSP-6493)
  - `list-table` directive accepts an argument (DOCSP-6554)
  - `card-group` directive (DOCSP-6447)

### Changed

- The original filename of static assets is now saved in the `filename` field of the
  `snooty.assets` collection, replacing the `type` field (DOCSP-6849).
- Directive "flag" options have a true value in the AST instead of null (DOCSP-6383).
- The "only" directive is now deprecated in favor of "cond".

### Fixed

- Parsing of the `versionadded`, `versionchanged`, and `deprecated` directives (DOCSP-6504).

## [v0.1.12] - 2019-07-25

### Added

- Add support for the following reStructuredText constructs:

  - `todo`
  - `deprecated`
  - `see`
  - `describe`
  - `glossary`
  - `rubric`
  - `envvar`

- Add support for the following extlinks:

  - `go-api`
  - `ecosystem`
  - `products`
  - `wtdocs`

### Changed

- Undefined source constants are now replaced with a zero-width space (\u200b),
  preventing them from creating a syntax error.

### Fixed

- No longer create spurious diagnostics about including apiargs artifacts and `hash.rst`.

## [v0.1.11] - 2019-07-23

### Added

- Add support for the following directives (DOCSP-6210):

  - `tabs-top`
  - `tabs-stitch-auth-provid`
  - `tabs-deployments`
  - `tabs-stitch-sdks`
  - `tabs-stitch-interfaces`
  - `blockquote`
  - `caution`

- Add support for the `wikipedia` role.

### Fixed

- All YAML parsing errors are caught, rather than just scanning errors (DOCSP-6251).
- Opening a project with missing static assets no longer triggers an unhandled exception (DOCSP-6267).

## [v0.1.10] - 2019-07-11

### Added

- `code` directive alias for `code-block`.

### Fixed

- Language server URIs now map correctly into local FileIds, and vice versa.

## [v0.1.9] - 2019-07-08

### Added

- Add `textDocument/resolve` RPC endpoint to return the source file path of an artifact relative to the project's root (DOCSP-5967).

### Changed

- Diagnostic messages when failing to open a static asset are more succinct.
- Warn about YAML files with duplicated refs (DOCSP-5704).

### Fixed

- Don't throw exception if saving an asset to the server fails (DOCSP-5998).
- The language server can now be gracefully shutdown using a context manager,
  for use in tests.

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

### Changed

- Avoid unnecessarily reprocessing figures and literal includes.
- Automatically rebuild files if their dependent assets change.
- Heading nodes now have an attached ID.

### Fixed

- The full `dns` package is included in binary builds, letting them connect to the database.

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

### Changed

- Avoid processing giza substitutions in base nodes to avoid superfluous diagnostics.

### Fixed

- `raw` directive contents are now ignored.
- Bundle `docutils.parsers.rst.directives.misc` in binary release to avoid runtime errors when using `unicode`.

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

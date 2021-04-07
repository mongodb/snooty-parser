# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.9.6] - 2021-04-07

### Changed

- Temporarily un-deprecate directive.class (DOP-2088).
- Remove button class option (#298).
- Identify headings for 'On this page' box (DOP-2045, #297).

## [v0.9.5] - 2021-03-10

### Fixed

- step-fix: Add an argument to landing steps (#295)
- DOP-1883: update URL of kotlin SDK to avoid redirect chain (#296)

## [v0.9.4] - 2021-03-03

### Fixed

- Links to Realm SDKs should not require a trailing slash (DOP-2022).

## [v0.9.3] - 2021-02-24

### Added

- Product landing page directives (DOP-1970).

### Changed

- Update OpenAPI directive to allow parsing through the frontend (DOP-1896).
- Apply trailing slashes to inter-docs roles (DOP-1966).

### Fixed

- Don't crash on failed intersphinx fetch: raise diagnostic (#287).
- Modify the toctree handling so that index.txt can add itself to the toctree with RecursionError (DOP-1931).
- Don't crash if invoked in a child directory of a project.

## [v0.9.2] - 2021-02-03

### Fixed

- Tarball bundles now contain members with 644 permissions.

## [v0.9.1] - 2021-02-03

### Added

- Permit tarballing of manpages (DOP-1816).

### Changed

- Reorder drivers tabs (DOP-1958).

### Removed

- The `:xml:` role, which was never implemented, is now removed from rstspec.toml.

## [v0.9.0] - 2021-01-28

### Added

- Allow "reusable" references (DOP-1857).

### Changed

- `rstspec.toml` updates.

## [v0.8.5] - 2021-01-14

### Added

- Support for the `~` tag on roles to cut off all but the last `.`-delimited segment (DOP-1806).

### Fixed

- Fix altering giza substitutions in inheriting nodes (DOP-1875).

## [v0.8.4] - 2021-01-06

### Fixed

- Don't crash upon building a manpage containing comments ([DOP-1874](https://jira.mongodb.com/browse/DOP-1874)).

## [v0.8.3] - 2021-01-06

### Added

- Build manpages ([DOP-1584](https://jira.mongodb.com/browse/DOP-1584))
- Support for include options and subsets in postprocessor ([DOP-323](https://jira.mongodb.com/browse/DOP-323))
- Update driver, compass, ecosystem, and Realm SDK roles to point to correct URLs ([DOP-1777](https://jira.mongodb.com/browse/DOP-1777))

### Fixed

- Handling of invalid tabs (parser no longer crashes, uses correct diagnostic levels)

## [v0.8.2] - 2020-12-02

### Added

- Support for figure border flag ([DOP-1579](https://jira.mongodb.com/browse/DOP-1579))
- Experimental support for installation on Windows

### Fixed

- Handling of :copyable: flag for code blocks ([DOP-1750](https://jira.mongodb.com/browse/DOP-1750))
- Handling of duplicate header / label naming ([DOP-1326](https://jira.mongodb.com/browse/DOP-1326))
- Installation behavior with new pip resolver

## [v0.8.1] - 2020-11-18

### Added

- Add `kafka-21-javadoc` role for kafka links.

### Changed

- Add suffixes to heading IDs to ensure uniqueness (DOP-1734).
- Don't rely on docutils header IDs, fixing e.g. headings with IDs like `id1` (DOP-1566).
- Don't include binary name unless requested in `:option:` links (DOP-1675).
- Update Realm tabsets (contributed by Nick Larew).

### Fixed

- Support for subcommands (DOP-1703).

## [v0.8.0] - 2020-11-10

### Added

- `dotnet-sdk`, `xamarin`, and `git-scm` extlink roles (DOCSP-13010).
- Blockquote suggestion when unexpected indentation is encountered.
- `created_at` field in the database to facilitate document expiration (DOP-1318).

### Changed

- Remove LiteralBlock node.
- Static assets are now stored in the database with both filename and hash identifier,
  making it easier for the frontend to properly create all needed images (DOP-1643).

## [v0.7.0] - 2020-10-22

### Added

- `caption` option for code blocks (DOP-1604).
- `mws` directive (DOP-1575).
- Tabs are now defined in rstspec.toml, and validated and sorted by the parser (DOP-1450).

### Changed

- Language pills are now provided in the document root node (DOP-1526).

### Fixed

- Double tabs-pillstrip bug (DOP-1526).
- Preserve source fileid through includes (DOP-1018).

## [v0.6.3] - 2020-10-14

### Changed

- Extlinks should use the target name for label if no label set, *not* the raw uri (DOP-1581).
- RFC link labels now match legacy (DOP-1581).
- Render role content when target is not found (DOP-1601).
- Bump `node` extlink version (DOCSP-12335).

### Fixed

- Correctly inherit YAML ref names (DOP-1595).
- Improve callable target handling.
- Support required arguments, and apply to rstobjects (DOP-1589).
- Support targets with escaped angle brackets (DOP-1586).

## [v0.6.2] - 2020-09-30

### Added

- A `dbtools` role for linking to database tools docs.
- New Realm rstobjects and extlinks (DOCSP-12508).
- A simple "did you mean" feature for some kinds of typos (DOP-1570).

### Changed

- Ambiguous references are now automatically resolved when it is reasonable to do so (DOP-1434).
- Permit version admonitions to have no argument (DOP-1523).
- Incorrect external link syntax now yields an error (DOP-1569).

### Fixed

- Incorrectly monospaced text no longer inserts the warning text into the document (DOP-1511).
- Intersphinx inventory entries now have the correct fragment identifiers (DOP-1574).

## [v0.6.1] - 2020-09-23

### Added

- Highlighting roles (`highlight-red`, `highlight-yellow`, `highlight-green`, `highlight-blue`).

### Fixed

- Linking to non-lowercase labels (DOP-1534).

## [v0.6.0] - 2020-09-16

### Changed

- HTML IDs are now explicit in the AST (DOP-1279).
- Target matching is now case-sensitive (DOP-1277).
- Internal changes to TOC metadata (DOP-981).
- Un-deprecate the `red` role (DOP-1489).

## [v0.5.9] - 2020-09-14

### Fixed

- Assets are now saved to the correct collection.

## [v0.5.8] - 2020-09-09

### Added

- add bic-v2.10 role to link to v2.10 bi-connector docs (DOP-1458).
- Ambiguous target candidates are now listed.

### Changed

- Batch writes to the database, significantly improving commit performance (DOP-1359).

### Fixed

- Support alternative no-title ref_role syntax (DOP-1429).
- Don't suppress missing option/toc include file messages.
- Sort glossary entires case-insensitively (DOP-1428).

## [v0.5.7] - 2020-09-08

### Added

- Support for the `prefix` field in `published-branches.yaml`.

## [v0.5.6] - 2020-08-26

### Added

- OpenAPI support (DOP-1356).
- A `charts-onprem` role (DOP-1342).

### Changed

- Internal error messages are now a little more helpful (DOP-1354).
- Several directive options are no longer required (DEVHUB-206).

### Fixed

- Fixed crashes with empty list-tables, and with some obscure markup (DOP-1354, DOP-1394).

## [v0.5.5] - 2020-08-13

### Added

- Language Server Protocol Diagnostics now include a `source` field of "snooty", so that users can
  quickly filter for snooty-related diagnostics in vscode.

### Fixed

- Upgraded PyInstaller to fix broken binaries.

## [v0.5.4] - 2020-08-12

### Added

- Support for directive fields (DOP-1295).
- Validation of required directive options (DOP-1306).
- Additional performance logging, and the `SNOOTY_PERF_SUMMARY` environment variable (DOP-1349).
- Various roles and directives.

### Fixed

- The list-table directive no longer generates incorrect warnings (DOP-1269).
- Substitutions may now be used in directive arguments (DOP-1230).

## [v0.5.3] - 2020-07-29

### Changed

- To prepare for updating the version of the parser used by the VSCode extension,
  the postprocessor has been temporarily disabled in the language server.

### Deprecated

- The following directives are deprecated: `admonition`, `danger`, `caution`, and `topic` (DOP-1243).

## [v0.5.2] - 2020-07-15

### Fixed

- Directive arguments were not being properly migrated in the AST.

## [v0.5.1] - 2020-07-15

### Added

- Support labels beginning with numbers that contain underscores (DOP-1188)
- Support for extlinks used by Atlas docs (DOP-1233)

## [v0.5.0] - 2020-07-08

### Added

- fail_on_diagnostics toml flag (DOP-1132)
- Support additional ordered list labels (DOP-1129)
- Support ordered list "start" attribute (DOP-1210)
- Logging of the parser's version at startup (DOP-1213).
- Snooty parser yields glossary IDs that match the IDs generated by legacy tooling (DOP-1171)

### Changed

- Improve string-handling in spec-parser (DOP-1148).

## [v0.4.11] - 2020-06-22

### Fixed

- Python 3.7 support.

## [v0.4.10] - 2020-06-17

### Changed

- Populate literal include nodes (DOP-876).

### Fixed

- RefRole nodes no longer render with the prefix if no title is found (DOP-1073).

## [v0.4.9] - 2020-06-05

### Added

- Columns option to card-group.

## [v0.4.8] - 2020-05-27

### Added

- Homepage directives (DOP-1120).

### Changed

- The `rfc` role is now an extlink and actually creates a reference (DOP-1128).

### Fixed

- Invalid YAML in tabs and card groups no longer triggers a crash (DOP-1135).

## [v0.4.7] - 2020-05-13

### Changed

- Error code 2 is now returned if there are error diagnostics, leaving error code 1 for crashes (DOP-922).

### Fixed

- Generated intersphinx inventories are now compatible with older versions of Sphinx (DOP-1094).
- Snooty no longer crashes when generating or loading an intersphinx inventory with invalid target names (DOP-1079).
- Diagnostic levels are now dealt with more carefully.

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

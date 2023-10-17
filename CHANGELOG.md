# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.15.0] - 2023-10-17

### Added

- DOP-4070: Automatically find a viable cache file from a given URL prefix

### Changed

- Use cx_freeze instead of pyinstaller to reduce flakiness of release process

## [v0.14.10] - 2023-09-28

- DOP-4043: allow specifying multiple facet values in a single facet directive option

## [v0.14.9] - 2023-09-16

### Added

- DOP-3991: Add landing:explore directive (#532)
- DOP-3987: Add landing:introduction directive (#521)
- DOP-3988: Add landing:products directive (#517)
- DOP-3992: Add landing:more-ways directive (#518)
- DOP-3855: Adding LeafyGreen icon role support (#512)

### Changed

- DOP-3993: Allow card group to link data for IA entry (#522)

## [v0.14.8] - 2023-09-07

### Fixed

- Include `taxonomy.toml` in the binary bundles.

## [v0.14.7] - 2023-09-07

### Changed

- All internal paths are now relative to the project source tree, not absolute, allowing cache
  files to be portable between computers and working directories (DOP-3966)
- Facet processing shoud be more reliable with regards to caches (DOP-3878)

### Fixed

- Ensure that YAML parsing diagnostics are reliably raised (DOP-4008)

## [v0.14.6] - 2023-08-25

### Changed

- Split out Realm Kotlin SDK role to sync and base URLs (#506)
- Hotfixes to provide empty list by default for validated_facets and fix diagnostics

## [v0.14.5] - 2023-08-24

### Added

- Implement concrete Facet type (DOP-3921, #500, #507).
- Support passing options like --rstspec to the create-cache command.
- Add cache tests (DOP-3946, #508).

### Changed

- Update dependencies (#502).
- Add perl programming language to taxonomy.
- Unpluralize taxonomy (#503).

## [v0.14.4] - 2023-08-10

### Added

- First stage of parse caching (DOP-3741).
- Cascading facets (DOP-3836, #494).

### Changed

- Taxonomy format changed (DOP-3875, #495, #501).

## [v0.14.3] - 2023-07-27

## [v0.14.2] - 2023-06-28

### Added

- Groundwork for page facets (DOP-3688, #476).

### Changed

- Linux AMD64 builds are now powered by [Pyston](http://pyston.org/), providing a healthy roughly 20% performance bump over
  CPython 3.11 (DOP-3746).

### Fixed

- Fix an incorrect assertion and a potential runtime exception that could be triggered by unusual reStructuredText (DOP-3753).

## [v0.14.1] - 2023-05-25

### Added

- Add support and validation for the `openapi-changelog` directive (DOP-3660, DOP-3661, DOP-3663).

### Fixed

- Correctly emit the `static_assets` field in each page's AST (DOP-3729).

## [v0.14.0] - 2023-04-06

## [v0.13.18] - 2023-03-02

## [v0.13.17] - 2023-02-13

- Switch from flit to poetry by @i80and in https://github.com/mongodb/snooty-parser/pull/427
- DOP-3487: Deprecate cssclass directive by @i80and in https://github.com/mongodb/snooty-parser/pull/443
- DOP-3211:  ref label by @mmeigs in https://github.com/mongodb/snooty-parser/pull/444
- Cleanup: use a type for associated products rather than Dict[str, object] by @i80and in https://github.com/mongodb/snooty-parser/pull/446
- Make bump_version.py also bump the version in pyproject.toml by @i80and in https://github.com/mongodb/snooty-parser/pull/445

## [v0.13.16] - 2023-01-25

### Changed

- Numerous version bumps for project dependencies.
- Page.query_fields removed (unused).
- Devhub specific codepaths removed.

### Fixed

- Copyable option now checks for non-falsey values instead of "True".

## [v0.13.15] - 2023-01-12

### Added

- Default children and default slug for associated toc node (#438) by @seungpark in #438.

### Changed

- Revert "Change OpenAPI metadata source to be spec string (DOP-3353)" by @rayangler in #436.

## [v0.13.14] - 2022-11-30

### Added

- Support for external ToC nodes as part of the embedded versions project (DOP-3200).

### Changed

- Binary releases are now built from Github Actions with Python 3.11 (DOP-3298).

### Fixed

- Each `.txt` page now gets a separate context for named references, rather than having a single
  global namespace with undefined filesystem-dependent semantics.

## [v0.13.13] - 2022-11-16

* Update GitHub actions by @i80and in https://github.com/mongodb/snooty-parser/pull/424
* DOP-3159: README overhaul by @seungpark in https://github.com/mongodb/snooty-parser/pull/425
* DOP-3307: Generate metadata for OpenAPI content pages by @rayangler in https://github.com/mongodb/snooty-parser/pull/426
* DOP-3353: Change OpenAPI metadata source to be spec string by @rayangler in https://github.com/mongodb/snooty-parser/pull/428

## [v0.13.12] - 2022-10-19

### Fixed

- Tigthen up the schema for the `constants` field in snooty.toml. It was excessively
  permissive and failed to warn about an authoring mistake, causing issues 8 months
  later (DOP-3320).

## [v0.13.11] - 2022-10-05

### Added

- Spelling suggestions for reference roles (#416).
- Associated products metadata (DOP-3197, #420).

## [v0.13.10] - 2022-09-16

### Added

- (DOCSP-23944) Adds Atlas CLI custom role to rstspec.toml (#419)
- realm-languages: Add Dart + re-order
- DOP-1166: include all icon roles. parse icon classname from role + target (#417)

### Fixed

- Fix some icon issues

## [v0.13.9] - 2022-08-24

### Added

- Add validation for icon role (DOP-1166) (#414)

### Fixed

- Fix invalid list-table structure error message

## [v0.13.8] - 2022-08-11

### Added

- List tables are now validated to have correct structure (DOP-3107)

## [v0.13.7] - 2022-07-28

### Changed

- Include branch name in manifest file (DOP-2986)

## [v0.13.6] - 2022-06-22

### Added

-  Added new link roles and mongosyncstate rstobject (#401, #402, #403, #404)
-  Rename "Realm" to "App Services" in tabsets (#405)
-  Validate relative URLs in card directives (DOP-3064, #408)

### Fixed

-  Fix upsert logic and added manifest testing (#400).
-  Expand tildes in paths input on the command line (DOP-3078, #409)
-  Properly handle rst source files with invalid UTF-8 (DOP-3068, #410)

## [v0.13.5] - 2022-05-19

### Added

- Literalinclude support for input/output directives (DOP-2952, #398).

### Fixed

- Correctly handle field lists existing within a list (DOP-2975).

## [v0.13.4] - 2022-05-05

### Added

- Support adding arbitrary data to `snooty.toml` files via the `data_fields` key in rstspec.toml (DOP-2657, #396).

## [v0.13.3] - 2022-04-07

### Added

- Add `source` option to `code-block` directives and the Code node (DOP-2743, #389).

## [v0.13.2] - 2022-03-21

- An `eol` boolean option in `snooty.toml` (DOP-2771, #390).
- Subdomain consolidation `rstspec.toml` changes (DOP-2808).

## [v0.13.1] - 2022-03-02

- Rename "Android SDK" tab to "Java SDK" (#388).
- Add `kotlin` and `flutter` SDKs to the `realm-sdks` tabset (#388).
- Improve `io-code-block` example snippets (DOP-2742, #387).

## [v0.13.0] - 2022-02-24

- Removed published branches logic from parser; version information
  will henceforth be sourced from Atlas (DOP-2243, #330)

## [v0.12.6] - 2022-02-24

### Added

- An `visible` option to the `output` directive (DOP-2760, #385).
- A `video` directive for embedding videos (DOP-2754, #384).

## [v0.12.5] - 2022-02-08

### Added

- Implement input, output, and io-code-block directives (DOP-2651, #375).
- Add an `icon` option to the `cta-banner` directive (DOP-2719, #382).

## [v0.12.4] - 2022-02-02

### Fixed

- Typo in the deploy environment configuration (DOP-2712, #383).

## [v0.12.3] - 2022-02-01

### Added

- An option to specify the location of an rstspec file to use (DOP-2649).
- A new set of deploy environments.

## [v0.12.2] - 2022-01-27

### Added

- The `mongodb:cta-banner` directive (DOP-2600, #380).

## [v0.12.1] - 2022-01-25

### Fixed

- Using the `include` directive with no argument no longer cause a build hang (DOP-2696, #376, #377).

## [v0.12.0] - 2022-01-19

### Changed

- `step` and `procedure` directives can now be styled and are used to help generate steps from YAML (DOP-2504).

## [v0.11.13] - 2022-01-12

### Fixed

- Substitutions containing multiple substitution elements no longer yields multiple paragraphs (DOP-2620).

## [v0.11.12] - 2022-01-06

### Added

- The `tocicon` page option allows writers to attach an icon to a page in the site nav (DOP-2320, #367).

## [v0.11.11] - 2022-01-05

### Added

- Flutter link roles (#373).
- Roles for different versions of WT docs (DOCS-14997).
- Chapters are now given an appropriate HTML5 id (DOP-2505).

### Fixed

- Handle escaped double-quotes (DOP-2638).
- Temporary workaround for PHP role intersphinx issues (DOP-2636).
- Properly report diagnostics on YAML parsing and unmarshaling errors (DOP-2637).

## [v0.11.10] - 2021-12-17

## [v0.11.9] - 2021-12-15

### Changed

- The language server has had significant work to increase concurrency and reduce jank,
  and now runs the postprocessor (DOP-2546, #358) bringing diagnostic parity with builds.

  More work is planned, but this is a significant step forward, years in the making!

- OpenAPI specs may now be fetched from realm (DOP-2533, #360) with the `:uses-realm:` option
  on the `openapi` directive.

- The `iOS SDK` Realm SDK tab has been retitled to `Swift SDK` courtesy of Chris Bush (#364).

### Fixed

- HTTP cache now avoids re-sending requests for an hour (#363)

## [v0.11.8] - 2021-12-01

### Fixed

- Do not crash if a literalinclude cannot be parsed as UTF-8 (DOP-2613).
- Correctly handle docutils output when a ref role contains backslashes (DOP-2611).

## [v0.11.7] - 2021-11-17

### Added

- Add `v5.0` and `v5.1` extlinks for the server manual (#354, #356)
- Support for the literalinclude `lineno-start` option (DOP-2562 #355)
- Support for chapter `image` and `icon` options (DOP-2446 #351, DOP-2447 #357)

## [v0.11.6] - 2021-11-03

### Added

- External link roles for the k8s migration (DOP-2556).
- `rust-async` and `rust-sync` driver tabs.
- Directives and metadata for upcoming guides work.

### Changed

- Docutils 0.18 is explicitly unsupported for the moment.

## [v0.11.5] - 2021-10-06

### Changed

- DOP-2332: tab drivers Mongo Shell -> MongoDB Shell

## [v0.11.4] - 2021-09-17

### Added

- The `replacement` and `sharedinclude` directives to support shared content work (DOP-2377, DOP-2376).

### Changed

- Symbolic links are now followed while scanning for content, as long as they do not go above snooty.toml in the filesystem hierarchy (DOP-2415, DOP-2430).

### Fixed

- Source constants no longer fail to recursively evaluate.

## [v0.11.3] - 2021-08-25

### Added

- Add version 5.0 to mongo-web-shell directive (DOP-2356)

## [v0.11.2] - 2021-08-04

### Added

- Quiz widget! (DOP-2319 #333 DOP-2354, DOP-2354 #334)

## [v0.11.1] - 2021-08-04

### Added

- `java-docs-4.3` extlink (#337)

## [v0.11.0] - 2021-07-14

### Added

- Directive for banner support (DOP-1573, #308)

## [v0.10.4] - 2021-07-07

### Fixed

- Correctly report line numbers within directive contents (DOP-2300).

## [v0.10.3] - 2021-06-30

### Fixed

- Correctly generate intersphinx inventory entries for targets defined on the root page (DOP-2292, #326)
- Report invalid extlink definitions on startup

## [v0.10.2] - 2021-06-24

### Fixed

- Restore hlist and blockquote directives.

## [v0.10.1] - 2021-06-24

### Fixed

- Fix typo in Kotlin SDK extlink.

## [v0.10.0] - 2021-06-24

### Changed

- Remove landing domain and guides content (DOP-2215, #314)
- YAML-generated steps now use the name `step-yaml` and `steps-yaml`
  to disambugate from the new steps component (DOP-2249, #320)
- Update Kotlin SDK extlinks.

### Fixed

- The `:limit:` role no longer renders in monospace (DOP-1735, #319)

## [v0.9.9] - 2021-06-07

### Added

- Add versioned node api directives (DOP-2223, #317).
- Add card-tag refrole (DOP-2174, #313).

### Changed

- Optimized the postprocessor (#316).

### Fixed

- Remove \x00 characters from text nodes (DOP-2196, #315).

## [v0.9.8] - 2021-05-11

### Added

- Add layout option to landing cards (DOP-2117, #311).

### Fixed

- Respect the `SYSTEM_PYTHON` makefile variable when creating the virtual environment.

## [v0.9.7] - 2021-05-06

### Added

- Add IA Support (DOP-2055)
- Add extra-compact card-group style (DOP-1836)
- Add role to link to manual v4.4 (#307)
- Validate children within tabs directives (DOP-1878)
- Update Realm .NET SDK API role to latest release (#306)

### Fixed

- Fix handling of sphinx-generated intersphinx inventories
  for pymongo, motor, and the php library docs. (DOP-1810)

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

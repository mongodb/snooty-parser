# Snooty Parser

## Organization

The snooty parser has the following key parts:

* Frontends
  * `main.py`
  * `language_server.py`
* Parser
  * `parser.py`
  * `rstparser.py`
  * `gizaparser/`
* Types & Tools
  * `flutter.py`
  * `types.py`
  * `util.py`

### Frontends

Snooty *frontends* instantiate a parser and use it to interact with
reStructuredText and YAML files, and to create output artifacts and
report diagnostics.

These frontends instantiate a `parser.Project` object.

#### `main.py`

`main.py` defines the main command-line Snooty interface.

#### `language_server.py`

`language_server.py` defines a
[Language Server](https://microsoft.github.io/language-server-protocol/specification)
for use with IDEs such as Visual Studio Code.

### Parser

The `parser.Project` class is the main frontend-agnostic interface to
Snooty. It reads a `snooty.toml` file to configure the project, and
parses each file with `rstparser.Parser`.

`rstparser.Parser` is responsible for transforming input reStructuredText artifacts
(.rst & .txt) into our JSON AST format. It instantiates a visitor object
(unnecessarily parameterized; it's always `parser.JSONVisitor`); creates
a docutils parser; passes the markup into it; and uses the visitor to
create the AST. The parent `parser.Project` then calls the configured
callbacks to notify the frontend of the parsed page.

The parser transforms Giza-style YAML files using the `gizaparser`
package. This uses the `flutter` library to deserialize the YAML files
into Python classes, and check types to ensure there are no errors.

#### `parser.py`

#### `rstparser.py`

`docutils`-interfacing components of the parser.

#### `gizaparser/`

Each module in this package contains the infrastructure to parse a category
of Giza YAML file. The `gizaparser.nodes` module contains generally-applicable
helper classes.

### Types & Tools

#### `flutter.py`

#### `types.py`

#### `util.py`

## Developing Snooty

Run the following to install the necessary tools:

```shell
python3 -m pip install flit virtualenv
```

Use [Flit](https://flit.readthedocs.io/en/latest/) to install Snooty. The module will be symlinked (via `-s`) to allow for testing changes without reinstalling the module.

```shell
flit install -s
```

### Running tests

To run tests for a specific file:

```shell
. .venv/bin/activate
pytest snooty/test_<file>.py
```

### Code Coverage

Install [Coverage](https://coverage.readthedocs.io/en/v4.5.x/). After running tests via `make format test`, run:

```shell
coverage html
```

This will generate an HTML representation of code coverage throughout the repo that can be viewed in the browser.

### Release Process

To release snooty, do the following:

* Make sure you are on the `master` branch.

* Ensure that the "Unreleased" section of CHANGELOG.md is up-to-date.

* Run `make cut-release BUMP_TO_VERSION="<new_version>"`, and make
  note of the release name that is printed at the end.

  The new version number should follow [semantic versioning](https://semver.org):
  `MAJOR.MINOR.PATCH`. For example, `make cut-release BUMP_TO_VERSION="0.1.2"`.
  Refer to `snooty/__init__.py` for the current version number.

* Ensure that everything looks okay, and that the binary generated in `dist/` works correctly.

* Run:

  ```shell
  git push --follow-tags
  ```

* Go to <https://github.com/mongodb/snooty-parser>, then go to the _releases_ tab,
  and click _Draft a new release_.

* Enter the `v<version>` to reference the tag which was just created, and enter the
  release name that was printed by the `make cut-release` target. Copy the appropriate
  section from CHANGELOG.md into the release description. Upload the release zip file
  in the `dist` directory, and check the _This is a pre-release_ checkbox.

If there is an error, use `git reset --hard <previous_commit_hash>` to revert any
commits that might have been made, and `git tag --delete v<version>` to remove the
tag if it was created.

## Problem Areas

* Transforming docutils nodes into our AST (parser.JSONVisitor) is
  currently a wretched mess.
* Flutter is currently a fork to add support for line numbers. We need to
  figure out a cleaner way of doing this so we can merge it into the
  upstream codebase.

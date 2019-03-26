# Organization

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

## Frontends

Snooty *frontends* instantiate a parser and use it to interact with
reStructuredText and YAML files, and to create output artifacts and
report diagnostics.

These frontends instantiate a `parser.Project` object.

### `main.py`

`main.py` defines the main command-line Snooty interface.

### `language_server.py`

`language_server.py` defines a
[Language Server](https://microsoft.github.io/language-server-protocol/specification)
for use with IDEs such as Visual Studio Code.

## Parser

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

### `parser.py`



### `rstparser.py`

`docutils`-interfacing components of the parser.

### `gizaparser/`

Each module in this package contains the infrastructure to parse a category
of Giza YAML file. The `gizaparser.nodes` module contains generally-applicable
helper classes.

## Types & Tools
### `flutter.py`
### `types.py`
### `util.py`


# Problem Areas

* Transforming docutils nodes into our AST (parser.JSONVisitor) is
  currently a wretched mess.
* Flutter is currently a fork to add support for line numbers. We need to
  figure out a cleaner way of doing this so we can merge it into the
  upstream codebase.

[//]: # (webhook testing words)

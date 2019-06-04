from pathlib import Path
from . import rstparser
from .util import ast_to_testing_string
from .types import Diagnostic, ProjectConfig
from .parser import parse_rst, JSONVisitor


def test_tabs() -> None:
    root = Path("test_data")
    tabs_path = Path(root).joinpath(Path("test_tabs.rst"))
    project_config = ProjectConfig(root, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, tabs_path, None)
    page.finish(diagnostics)

    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<directive name="tabs" hidden="True"><directive name="tab"><text>bionic</text>',
            "<paragraph><text>Bionic content</text></paragraph></directive>",
            '<directive name="tab"><text>xenial</text><paragraph><text>',
            "Xenial content</text></paragraph></directive>",
            '<directive name="tab"><text>trusty</text><paragraph><text>',
            "Trusty content</text></paragraph></directive></directive>",
            '<directive name="tabs" tabset="platforms"><directive name="tab"><text>windows</text>',
            "<paragraph><text>Windows content</text></paragraph></directive></directive>",
            '<directive name="tabs" hidden="true"><directive name="tab">',
            "<text>trusty</text><paragraph><text>",
            "Trusty content</text></paragraph></directive>",
            '<directive name="tab"><text>xenial</text><paragraph><text>',
            "Xenial content</text></paragraph></directive></directive>",
            "</root>",
        )
    )

    assert (
        len(diagnostics) == 1
        and diagnostics[0].message.startswith("Unexpected field")
        and diagnostics[0].start[0] == 44
    )


def test_codeblock() -> None:
    root = Path("test_data")
    tabs_path = Path(root).joinpath(Path("test.rst"))
    project_config = ProjectConfig(root, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test a simple code-block
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: sh

   foo bar
     indented
   end""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<code lang="sh" copyable="True">foo bar\n  indented\nend</code>' "</root>",
        )
    )

    # Test parsing of emphasize-lines
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: sh
   :copyable: false
   :emphasize-lines: 1, 2-3

   foo
   bar
   baz""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<code lang="sh" emphasize_lines="[(1, 1), (2, 3)]">foo\nbar\nbaz</code>'
            "</root>",
        )
    )

    # Test handling of out-of-range lines
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: sh
   :emphasize-lines: 10

   foo""",
    )
    page.finish(diagnostics)
    assert diagnostics[0].severity == Diagnostic.Level.warning


def test_literalinclude() -> None:
    root = Path("test_data")
    path = Path(root).joinpath(Path("test.rst"))
    project_config = ProjectConfig(root, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test a simple code-block
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /driver-examples/pythonexample.py
   :dedent:
   :start-after: Start Example 3
   :end-before: End Example 3
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<code lang="py">db.inventory.insert_many([\n',
            '    {"item": "journal",\n',
            '     "qty": 25,\n',
            '     "tags": ["blank", "red"],\n',
            '     "size": {"h": 14, "w": 21, "uom": "cm"}},\n\n',
            '    {"item": "mat",\n',
            '     "qty": 85,\n',
            '     "tags": ["gray"],\n',
            '     "size": {"h": 27.9, "w": 35.5, "uom": "cm"}},\n\n',
            '    {"item": "mousepad",\n',
            '     "qty": 25,\n',
            '     "tags": ["gel", "blue"],\n',
            '     "size": {"h": 19, "w": 22.85, "uom": "cm"}}])</code>',
            "</root>",
        )
    )

    # Test bad code-blocks
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /driver-examples/pythonexample.py
   :start-after: Start Example 0
   :end-before: End Example 3
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /driver-examples/pythonexample.py
   :start-after: Start Example 3
   :end-before: End Example 0
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /driver-examples/garbagnrekvjisd.py
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1


def test_admonition() -> None:
    root = Path("test_data")
    path = Path(root).joinpath(Path("test.rst"))
    project_config = ProjectConfig(root, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. note::
   * foo
   * bar
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<directive name="note">',
            "<list><listItem><paragraph><text>foo</text></paragraph></listItem>",
            "<listItem><paragraph><text>bar</text></paragraph></listItem></list>",
            "</directive>",
            "</root>",
        )
    )


def test_rst_replacement() -> None:
    root = Path("test_data")
    path = Path(root).joinpath(Path("test.rst"))
    project_config = ProjectConfig(root, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. |new version| replace:: 3.4

foo |new version| bar
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<substitution_definition name="new version">',
            "<text>3.4</text>",
            "</substitution_definition>",
            "<paragraph>",
            "<text>foo </text>",
            '<substitution_reference name="new version"></substitution_reference>',
            "<text> bar</text>",
            "</paragraph>",
            "</root>",
        )
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. |double arrow ->| unicode:: foo U+27A4 U+27A4 .. double arrow

foo |double arrow ->| bar
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            '<substitution_definition name="double arrow ->">',
            "<text>foo</text><text>➤</text><text>➤</text>",
            "</substitution_definition>",
            "<paragraph>",
            "<text>foo </text>",
            '<substitution_reference name="double arrow ->"></substitution_reference>',
            "<text> bar</text>",
            "</paragraph>",
            "</root>",
        )
    )

    # Ensure that the parser doesn't emit warnings about unresolvable substitution references
    page, diagnostics = parse_rst(parser, path, "foo |bar|")
    page.finish(diagnostics)
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            "<paragraph>",
            "<text>foo </text>",
            '<substitution_reference name="bar"></substitution_reference>',
            "</paragraph>",
            "</root>",
        )
    )


def test_roles() -> None:
    root = Path("test_data")
    path = Path(root).joinpath(Path("test.rst"))
    project_config = ProjectConfig(root, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test both forms of :manual: (an extlink), :rfc: (explicit title),
    # :binary: (rstobject), and :guilabel: (plain text)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
* :manual:`/introduction/`
* :manual:`Introduction to MongoDB </introduction/>`
* :rfc:`1149`
* :rfc:`RFC-1149 <1149>`
* :binary:`~bin.mongod`
* :binary:`mongod <~bin.mongod>`
* :guilabel:`Test <foo>`
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    print(ast_to_testing_string(page.ast))
    assert ast_to_testing_string(page.ast) == "".join(
        (
            "<root>",
            "<list>",
            "<listItem>",
            "<paragraph>",
            '<reference refuri="https://docs.mongodb.com/manual/introduction/">',
            "<text>https://docs.mongodb.com/manual/introduction/</text>"
            "</reference>"
            "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<reference refuri="https://docs.mongodb.com/manual/introduction/">',
            "<text>Introduction to MongoDB</text>" "</reference>" "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<role name="rfc" target="1149"></role>',
            "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<role name="rfc" label="',
            "{'type': 'text', 'value': 'RFC-1149', 'position': {'start': {'line': 5}}}",
            '" target="1149"></role>',
            "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<role name="binary" target="~bin.mongod"></role>',
            "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<role name="binary" label="',
            "{'type': 'text', 'value': 'mongod', 'position': {'start': {'line': 7}}}",
            '" target="~bin.mongod"></role>',
            "</paragraph>",
            "</listItem>",
            "<listItem>",
            "<paragraph>",
            '<role name="guilabel" label="',
            "{'type': 'text', 'value': 'Test <foo>', 'position': {'start': {'line': 8}}}",
            '"></role>',
            "</paragraph>",
            "</listItem>",
            "</list>",
            "</root>",
        )
    )

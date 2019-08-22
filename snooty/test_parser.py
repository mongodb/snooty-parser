from pathlib import Path
from . import rstparser
from .util_test import check_ast_testing_string
from .types import Diagnostic, ProjectConfig
from .parser import parse_rst, JSONVisitor

ROOT_PATH = Path("test_data")


def test_tabs() -> None:
    tabs_path = ROOT_PATH.joinpath(Path("test_tabs.rst"))
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, tabs_path, None)
    page.finish(diagnostics)

    check_ast_testing_string(
        page.ast,
        """<root>
        <directive name="tabs" hidden="True"><directive name="tab" tabid="bionic"><text>Ubuntu 18.04 (Bionic)</text>
        <paragraph><text>Bionic content</text></paragraph></directive>
        <directive name="tab" tabid="xenial"><text>Ubuntu 16.04 (Xenial)</text><paragraph><text>
        Xenial content</text></paragraph></directive>
        <directive name="tab" tabid="trusty"><text>Ubuntu 14.04 (Trusty)</text><paragraph><text>
        Trusty content</text></paragraph></directive></directive>
        <directive name="tabs" tabset="platforms"><directive name="tab" tabid="windows">
        <paragraph><text>Windows content</text></paragraph></directive></directive>
        <directive name="tabs" tabset="platforms"><directive name="tab" tabid="windows">
        <paragraph><text>Windows content</text></paragraph></directive></directive>
        <directive name="tabs" tabset="platforms"><directive name="tab" tabid="windows">
        <paragraph><text>Windows content</text></paragraph></directive></directive>
        <directive name="tabs" hidden="True"><directive name="tab" tabid="trusty">
        <text>Ubuntu 14.04 (Trusty)</text><paragraph><text>
        Trusty content</text></paragraph></directive>
        <directive name="tab" tabid="xenial"><text>Ubuntu 16.04 (Xenial)</text><paragraph><text>
        Xenial content</text></paragraph></directive></directive>
        </root>""",
    )

    assert (
        len(diagnostics) == 1
        and diagnostics[0].message.startswith("Unexpected field")
        and diagnostics[0].start[0] == 61
    )


def test_codeblock() -> None:
    tabs_path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "")
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
    check_ast_testing_string(
        page.ast,
        """<root>
        <code lang="sh" copyable="True">foo bar\n  indented\nend</code>
        </root>""",
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
    check_ast_testing_string(
        page.ast,
        """<root>
        <code lang="sh" emphasize_lines="[(1, 1), (2, 3)]">foo\nbar\nbaz</code>
        </root>""",
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
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
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
    check_ast_testing_string(
        page.ast,
        """<root>
<code lang="py">db.inventory.insert_many([
    {"item": "journal",
     "qty": 25,
     "tags": ["blank", "red"],
     "size": {"h": 14, "w": 21, "uom": "cm"}},\n
    {"item": "mat",
     "qty": 85,
     "tags": ["gray"],
     "size": {"h": 27.9, "w": 35.5, "uom": "cm"}},\n
    {"item": "mousepad",
     "qty": 25,
     "tags": ["gel", "blue"],
     "size": {"h": 19, "w": 22.85, "uom": "cm"}}])</code>
</root>""",
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


def test_include() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test good include
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. include:: /driver-examples/rstexample.rst
        """,
    )
    page.finish(diagnostics)
    assert diagnostics == []

    # Test generated include
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. include:: /driver-examples/steps/generated-include.rst
        """,
    )
    page.finish(diagnostics)
    assert diagnostics == []

    # Test bad include
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. include:: /driver-examples/fake-include.rst
        """,
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1


def test_admonition() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
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
    check_ast_testing_string(
        page.ast,
        """<root>
        <directive name="note">
        <list><listItem><paragraph><text>foo</text></paragraph></listItem>
        <listItem><paragraph><text>bar</text></paragraph></listItem></list>
        </directive>
        </root>""",
    )


def test_rst_replacement() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
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
    check_ast_testing_string(
        page.ast,
        """<root>
        <substitution_definition name="new version">
        <text>3.4</text>
        </substitution_definition>
        <paragraph>
        <text>foo </text>
        <substitution_reference name="new version"></substitution_reference>
        <text> bar</text>
        </paragraph>
        </root>""",
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
    check_ast_testing_string(
        page.ast,
        """<root>
        <substitution_definition name="double arrow ->">
        <text>foo</text><text>➤</text><text>➤</text>
        </substitution_definition>
        <paragraph>
        <text>foo </text>
        <substitution_reference name="double arrow ->"></substitution_reference>
        <text> bar</text>
        </paragraph>
        </root>""",
    )

    # Ensure that the parser doesn't emit warnings about unresolvable substitution references
    page, diagnostics = parse_rst(parser, path, "foo |bar|")
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root>
        <paragraph>
        <text>foo </text>
        <substitution_reference name="bar"></substitution_reference>
        </paragraph>
        </root>""",
    )


def test_roles() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
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
    check_ast_testing_string(
        page.ast,
        """<root>
            <list>
            <listItem>
            <paragraph>
            <reference refuri="https://docs.mongodb.com/manual/introduction/">
            <text>https://docs.mongodb.com/manual/introduction/</text>
            </reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://docs.mongodb.com/manual/introduction/">
            <text>Introduction to MongoDB</text></reference></paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <role name="rfc" target="1149"></role>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <role name="rfc"
                  label="{'type': 'text', 'value': 'RFC-1149', 'position': {'start': {'line': 5}}}"
                  target="1149"></role>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <role name="binary" target="~bin.mongod"></role>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <role name="binary"
                  label="{'type': 'text', 'value': 'mongod', 'position': {'start': {'line': 7}}}"
                  target="~bin.mongod"></role>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <role name="guilabel"
                  label="{'type': 'text', 'value': 'Test &lt;foo&gt;', 'position': {'start': {'line': 8}}}">
            </role>
            </paragraph>
            </listItem>
            </list>
            </root>""",
    )


def test_doc_role() -> None:
    project_root = ROOT_PATH.joinpath("test_project")
    path = project_root.joinpath(Path("source/test.rst")).resolve()
    project_config = ProjectConfig(project_root, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test bad text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
* :doc:`Testing it <fake-text>`
* :doc:`Testing this </fake-text>`
* :doc:`Testing that <./fake-text>`
* :doc:`fake-text`
* :doc:`/fake-text`
* :doc:`./fake-text`
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 6

    # Test valid text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
* :doc:`Testing this </index>`
* :doc:`Testing that <./../source/index>`
* :doc:`index`
* :doc:`/index`
* :doc:`./../source/index`
* :doc:`/index/`
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
        <root>
        <list>
        <listItem>
        <paragraph>
        <role name="doc"
              label="{'type': 'text', 'value': 'Testing this', 'position': {'start': {'line': 2}}}"
              target="/index"></role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <role name="doc"
              label="{'type': 'text', 'value': 'Testing that', 'position': {'start': {'line': 3}}}"
              target="./../source/index"></role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <role name="doc" target="index"></role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <role name="doc" target="/index"></role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <role name="doc" target="./../source/index"></role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <role name="doc" target="/index/"></role>
        </paragraph>
        </listItem>
        </list>
        </root>""",
    )


def test_accidental_indentation() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. note::

   This is

     a

   test
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    check_ast_testing_string(
        page.ast,
        """<root>
        <directive name="note">
        <paragraph><text>This is</text></paragraph>
        <paragraph><text>a</text></paragraph>
        <paragraph><text>test</text></paragraph>
        </directive>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :widths: 50 25 25
   :stub-columns: 1

    * - Windows (32- and 64-bit) # ERROR HERE
      - Windows 7 or later
      - Windows Server 2008 R2 or later

   * - macOS (64-bit)
     - 10.10 or later
     -
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1


def test_cond() -> None:
    path = ROOT_PATH.joinpath(Path("test.rst"))
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. cond:: (not man) or html

   .. note::

      A note.

.. cond:: man

   .. note::

      Another note.
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root>
        <directive name="cond">
        <text>(not man) or html</text>
        <directive name="note"><paragraph><text>A note.</text></paragraph></directive>
        </directive>
        <directive name="cond">
        <text>man</text>
        <directive name="note"><paragraph><text>Another note.</text></paragraph></directive>
        </directive>
        </root>""",
    )

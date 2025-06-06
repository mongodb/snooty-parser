from pathlib import Path

from . import rstparser, util
from .diagnostics import (
    AmbiguousLiteralInclude,
    CannotOpenFile,
    Diagnostic,
    DocUtilsParseError,
    DuplicateOptionId,
    ErrorParsingYAMLFile,
    ExpectedOption,
    ExpectedPathArg,
    ExpectedStringArg,
    IconMustBeDefined,
    IncorrectLinkSyntax,
    IncorrectMonospaceSyntax,
    InvalidChild,
    InvalidChildCount,
    InvalidDirectiveStructure,
    InvalidField,
    InvalidLiteralInclude,
    InvalidTableStructure,
    InvalidURL,
    MakeCorrectionMixin,
    MalformedGlossary,
    MalformedRelativePath,
    MissingChild,
    MissingFacet,
    MissingStructuredDataFields,
    RemovedLiteralBlockSyntax,
    TabMustBeDirective,
    UnexpectedDirectiveOrder,
    UnexpectedIndentation,
    UnexpectedNodeType,
    UnknownOptionId,
    UnknownTabID,
    UnknownTabset,
)
from .n import FileId
from .parser import InlineJSONVisitor, JSONVisitor
from .types import ProjectConfig
from .util_test import (
    ast_to_testing_string,
    check_ast_testing_string,
    make_test,
    parse_rst,
)

ROOT_PATH = Path("test_data")

# Some of the tests in this file may seem a little weird around refs: the raw parser output
# does NOT include postprocessing artifacts such as nonlocal link titles and intersphinx lookups.


def test_quiz() -> None:
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, FileId("test_quiz.rst"), None)
    page.finish(diagnostics)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test_quiz.rst">
        <directive name="quiz" domain="mongodb" quiz-id="mongoacc1" quiz-date="2021-06-21">
            <paragraph><text>With my MongoDB account, I can now access?</text></paragraph>
            <directive name="quizchoice" domain="mongodb">
                <text>MongoDB Atlas</text>
                <paragraph><text>Up to 2 lines of copy here explaining why MongoDB Atlas isn’t the right answer choice</text></paragraph>
            </directive>
            <directive name="quizchoice" domain="mongodb">
                <text>MongoDB University</text>
                <paragraph><text>Up to 2 lines of copy here explaining why MongoDB University isn’t the right answer choice</text></paragraph>
            </directive>
            <directive name="quizchoice" domain="mongodb" is-true="True">
                <text>All of the Above</text>
                <paragraph><text>Your MongoDB account gives you access to all of the above: Atlas, University, Cloud Manager, etc.</text></paragraph>
            </directive>
        </directive>
        </root>""",
    )


def test_chapter() -> None:
    """Test chapter directive"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test good chapter with image
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. chapters::

   .. chapter:: Atlas
      :description: Chapter description.
      :image: /test_parser/sample.png

      .. guide:: /test_parser/includes/sample_rst.rst
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Test good chapter without image
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. chapters::

   .. chapter:: Atlas
      :description: Chapter description.

      .. guide:: /test_parser/includes/sample_rst.rst
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Test chapter with incorrect image
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. chapters::

   .. chapter:: Atlas
      :description: Chapter description.
      :image: /fake-image.png

      .. guide:: /test_parser/includes/sample_rst.rst
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], CannotOpenFile)


def test_card() -> None:
    """Test card directive"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    SOURCE_DIR = "/test_project/source/"
    VALID_URLS = ["index", "index/"]
    INVALID_URL = [("foo", CannotOpenFile), ("index//", MalformedRelativePath)]
    CARD_CONTENT = """
.. card-group::
   :columns: 3
   :layout: carousel
   :type: drivers

   .. card::
      :headline: Develop Applications
      :cta: Test Develop Applications Relative URL Test
      :url: %s

      This card was built with a relative URL.
"""

    for url in VALID_URLS:
        page, diagnostics = parse_rst(
            parser,
            path,
            CARD_CONTENT % (SOURCE_DIR + url),
        )

        page.finish(diagnostics)
        assert len(diagnostics) == 0

    for url, error_type in INVALID_URL:
        page, diagnostics = parse_rst(
            parser,
            path,
            CARD_CONTENT % (SOURCE_DIR + url),
        )
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], error_type)


def test_tabs() -> None:
    tabs_fileid = FileId("test_tabs.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, tabs_fileid, None)
    page.finish(diagnostics)

    check_ast_testing_string(
        page.ast,
        """<root fileid="test_tabs.rst">

        <directive name="tabs" hidden="True">
            <directive name="tab" tabid="bionic">
                <text>Ubuntu 18.04 (Bionic)</text>
                <paragraph><text>Bionic content</text></paragraph>
            </directive>
            <directive name="tab" tabid="xenial">
                <text>Ubuntu 16.04 (Xenial)</text>
                <paragraph><text>Xenial content</text></paragraph>
            </directive>
            <directive name="tab" tabid="trusty">
                <text>Ubuntu 14.04 (Trusty)</text>
                <paragraph><text>Trusty content</text></paragraph>
            </directive>
        </directive>

        <directive name="tabs" tabset="platforms">
            <directive name="tab" tabid="windows">
                <text>Windows</text>
                <paragraph><text>Windows content</text></paragraph>
            </directive>
        </directive>

        <directive name="tabs" tabset="platforms">
            <directive name="tab" tabid="windows">
                <text>Windows</text>
                <paragraph><text>Windows Content</text></paragraph>
            </directive>
            <directive name="tab" tabid="macos">
                <text>macOS</text>
                <paragraph><text>macOS Content</text></paragraph>
            </directive>
            <directive name="tab" tabid="linux">
                <text>Linux</text>
                <paragraph><text>Linux Content</text></paragraph>
            </directive>
        </directive>

        <directive name="tabs" tabset="platforms">
        </directive>

        <directive name="tabs" tabset="unknown-tabset">
            <directive name="tab" tabid="linux">
                <paragraph><text>Linux Content</text></paragraph>
            </directive>
        </directive>

        <directive name="tabs" hidden="True">
            <directive name="tab" tabid="trusty">
                <text>Ubuntu 14.04 (Trusty)</text>
                <paragraph><text>Trusty content</text></paragraph>
            </directive>
            <directive name="tab" tabid="xenial">
                <text>Ubuntu 16.04 (Xenial)</text>
                <paragraph><text>Xenial content</text></paragraph>
            </directive>
        </directive>

        <directive name="tabs">
            <directive name="tab" tabid="http">
                <text>HTTP</text>
                <paragraph><text>Tab Content</text></paragraph>
            </directive>
        </directive>
        </root>""",
    )
    assert isinstance(diagnostics[0], UnknownTabID)
    assert isinstance(diagnostics[1], UnknownTabset)
    assert isinstance(diagnostics[2], DocUtilsParseError)
    assert isinstance(diagnostics[3], TabMustBeDirective)

    # Test a tab with no tabid
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        tabs_fileid,
        """
.. tabs-drivers::

   .. tab::
      :tabid: python

      Python!

   .. tab::

      Tab with no ID

   .. tab::
      :tabid: faketab

      Not a real tab!

   .. tab::
      :tabid: php

      PHP!
""",
    )
    page.finish(diagnostics)
    assert [(type(d), d.severity) for d in diagnostics] == [
        (DocUtilsParseError, Diagnostic.Level.error),
        (UnknownTabID, Diagnostic.Level.error),
    ]

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test_tabs.rst">
    <directive name="tabs" tabset="drivers">
        <directive name="tab" tabid="php">
            <text>PHP</text>
            <paragraph><text>PHP!</text></paragraph>
        </directive>
        <directive name="tab" tabid="python">
            <text>Python</text>
            <paragraph><text>Python!</text></paragraph>
        </directive>
    </directive>
</root>
    """,
    )


def test_tabsets_with_options() -> None:
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, FileId("test_tabs_options.rst"), None)
    page.finish(diagnostics)

    check_ast_testing_string(
        page.ast,
        """<root fileid="test_tabs_options.rst">
    <directive name="tabs" hidden="True" tabset="drivers">
        <directive name="tab" tabid="java-sync">
            <text>Java (Sync)</text><paragraph><text>Text</text></paragraph>
        </directive>
        <directive name="tab" tabid="nodejs">
            <text>Node.js</text><paragraph><text>More text</text></paragraph>
        </directive>
    </directive>
    </root>""",
    )
    assert len(diagnostics) == 0


def test_tabs_invalid_yaml() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. tabs-drivers::

   tabs:

     - id: java-sync

         .. code-block:: java
            :emphasize-lines: 2
            HashMap<String, BsonDocument> schemaMap = new HashMap<String, BsonDocument>();
            schemaMap.put("medicalRecords.patients", BsonDocument.parse(jsonSchema));
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], ErrorParsingYAMLFile)
    assert diagnostics[0].start[0] == 6


def test_tabs_reorder() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. tabs-drivers::

   .. tab::
      :tabid: python

      This tab should be second

   .. tab::
      :tabid: nodejs

      This tab should be first
""",
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        r"""
<root fileid="test.rst">
<directive name="tabs" tabset="drivers">
<directive name="tab" tabid="nodejs"><text>Node.js</text>
<paragraph><text>This tab should be first</text></paragraph>
</directive>
<directive name="tab" tabid="python"><text>Python</text>
<paragraph><text>This tab should be second</text></paragraph>
</directive>
</directive>
</root>
""",
    )


def test_iocodeblock() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test a io-code-block with nested input/output directives with raw code content passed in
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input::
      :language: python

      print('hello world')

   .. output::

      hello world""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="io-code-block">
        <directive name="input" language="python"><code lang="python">print('hello world')</code></directive>
        <directive name="output"><code>hello world</code></directive>
    </directive>
</root>""",
    )

    # Test a io-code-block with nested input/output directives with <path/to/file> passed in
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input:: /test_parser/includes/sample_code.py
      :language: python

   .. output:: /test_parser/includes/sample_code.py
      :language: python""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="io-code-block">
        <directive name="input" language="python"><text>/test_parser/includes/sample_code.py</text>
            <code lang="python">    # start example 1
    print("test dedent")
    # end example 1

    # start example 2
    print("hello world")
    # end example 2
            </code></directive>
        <directive name="output" language="python"><text>/test_parser/includes/sample_code.py</text>
            <code lang="python">    # start example 1
    print("test dedent")
    # end example 1

    # start example 2
    print("hello world")
    # end example 2
            </code>
    </directive></directive></root>
""",
    )

    # Test a io-code-block with language incorrectly passed in as an argument
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block:: python

   .. input::

      print('hello world')

   .. output::

      hello world""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], InvalidDirectiveStructure)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
  <directive name="io-code-block">
      <text>python</text>
      <directive name="input">
          <code>print('hello world')</code>
      </directive>
      <directive name="output">
          <code>hello world</code>
      </directive>
  </directive>
</root>""",
    )

    # Test an invalid <path/to/file> for nested input directive
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input:: /test_parser/includes/nonexistent_file.py
      :language: python

   .. output:: /test_parser/includes/sample_code.py
""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], CannotOpenFile)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst"><directive name="io-code-block"></directive></root>""",
    )

    # Test an invalid <path/to/file> for nested output directive
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input:: /test_parser/includes/sample_code.py
      :language: python

   .. output:: /test_parser/includes/nonexistent_file.py
      :language: python
""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], CannotOpenFile)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="io-code-block">
        <directive name="input" language="python"><text>/test_parser/includes/sample_code.py</text>
        <code lang="python">    # start example 1
    print("test dedent")
    # end example 1

    # start example 2
    print("hello world")
    # end example 2
</code></directive></directive></root>""",
    )

    # Test a io-code-block with a missing input directive
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. output::

      hello world""",
    )
    page.finish(diagnostics)
    assert diagnostics[0].severity == Diagnostic.Level.error
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst"><directive name="io-code-block"></directive></root>""",
    )

    # Test a io-code-block with a missing output directive
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input::
      :language: python

      print('hello world')""",
    )
    page.finish(diagnostics)
    assert diagnostics[0].severity == Diagnostic.Level.error
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
  <directive name="io-code-block">
      <directive name="input" language="python"><code lang="python">print('hello world')</code>
  </directive>
 </directive></root>""",
    )

    # Test a io-code-block with an invalid child directive
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   this is a paragraph
   that should not be here

   .. input::
      :language: python

      print('hello world')""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], InvalidDirectiveStructure)
    assert diagnostics[0].severity == Diagnostic.Level.error
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
  <directive name="io-code-block">
      <directive name="input" language="python"><code lang="python">print('hello world')</code></directive>
  </directive>
</root>""",
    )

    # Test a io-code-block with multiple valid input/output directives
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input::
      :language: python

      print('hello world')

   .. input::
      :language: python

      print('hello world')

   .. output::

      hello world""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], InvalidDirectiveStructure)
    assert diagnostics[0].severity == Diagnostic.Level.error
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
  <directive name="io-code-block">
      <directive name="input" language="python"><code lang="python">print('hello world')</code></directive>
      <directive name="output"><code>hello world</code></directive>
  </directive>
</root>""",
    )

    # Test parsing of emphasize-lines and linenos for input/output directives
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input::
      :language: python
      :linenos:
      :emphasize-lines: 1-2, 4

      print('hello world1')
      print('hello world2')
      print('hello world3')
      print('hello world4')

   .. output::
      :emphasize-lines: 3

      hello world1
      hello world2
      hello world3
      hello world4""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="io-code-block">
        <directive name="input" language="python" linenos="True" emphasize-lines="1-2, 4">
        <code lang="python" emphasize_lines="[(1, 2), (4, 4)]" linenos="True">print('hello world1')
print('hello world2')
print('hello world3')
print('hello world4')</code></directive>
        <directive name="output" emphasize-lines="3"><code emphasize_lines="[(3, 3)]">hello world1
hello world2
hello world3
hello world4</code></directive>
    </directive>
</root>""",
    )

    # Test full support of literalinclude options for input/output directives
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::

   .. input:: /test_parser/includes/sample_code.py
      :language: python
      :linenos:
      :start-after: start example 1
      :end-before: end example 2
      :dedent: 4
      :lineno-start: 2
      :category: syntax

   .. output:: /test_parser/includes/sample_code.py
      :language: python
      :linenos:
      :start-after: start example 2
      :end-before: end example 2
      :dedent: 4
      :lineno-start: 6""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    assert page.dependencies == util.FileCacheMapping(
        {
            FileId(
                "test_parser/includes/sample_code.py"
            ): "f6a999ef69965870804279b80ec4e4f2d38c617175435ac68e5558dcf1dc5be3e15cf31217b0c62024eeef2f5ef94c7b575c84b5624abba6d3b4ae5fdbfa30e6"
        }
    )

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="io-code-block">
        <directive name="input" language="python" linenos="True" start-after="start example 1" end-before="end example 2" dedent="4" lineno-start="2" category="syntax">
            <text>/test_parser/includes/sample_code.py</text>
            <code lang="python" linenos="True" lineno_start="2">print("test dedent")
# end example 1

# start example 2
print("hello world")
            </code>
        </directive>
        <directive name="output" language="python" linenos="True" start-after="start example 2" end-before="end example 2" dedent="4" lineno-start="6">
            <text>/test_parser/includes/sample_code.py</text><code lang="python" linenos="True" lineno_start="6">print("hello world")</code>
       </directive>
    </directive>
</root>""",
    )

    # Test a io-code-block with incorrect options linenos and emphasize-lines
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. io-code-block::
   :emphasize-lines: 1-2

   .. input::
      :language: python

      print('hello world1')
      print('hello world2')
      print('hello world3')

   .. output::

      hello world1
      hello world2
      hello world3""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], DocUtilsParseError)
    assert diagnostics[0].severity == Diagnostic.Level.error


def test_codeblock() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
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
        """<root fileid="test.rst">
        <code lang="sh" copyable="True">foo bar\n  indented\nend</code>
        </root>""",
    )

    # Test parsing of emphasize-lines
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: sh
   :copyable: true
   :emphasize-lines: 1, 2-3
   :linenos:

   foo
   bar
   baz""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <code lang="sh" emphasize_lines="[(1, 1), (2, 3)]" copyable="True" linenos="True">foo\nbar\nbaz</code>
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
    assert diagnostics[0].severity == Diagnostic.Level.error

    # Test absent language
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code::

   foo""",
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <code copyable="True">foo</code>
        </root>""",
    )

    # Test caption option
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: java
   :copyable: false
   :caption: Test caption

   foo""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <code lang="java" caption="Test caption">foo</code>
        </root>""",
    )

    # Test empty caption
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code:: js
   :caption:

   foo""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test source option
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: java
   :copyable: false
   :source: https://www.github.com/mongodb/snooty

   foo""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <code lang="java" source="https://www.github.com/mongodb/snooty">foo</code>
        </root>""",
    )

    # Test empty source
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: java
   :copyable: false
   :source:

   foo""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test category option
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: java
   :copyable: false
   :category: syntax

   foo""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <code lang="java" category="syntax">foo</code>
        </root>""",
    )

    # Test empty category
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. code-block:: java
   :copyable: false
   :category:

   foo""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)


def test_literalinclude() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test a simple literally-included code block
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.js
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
  <directive name="literalinclude"><text>/test_parser/includes/sample_code.js</text><code copyable="True">var str = "sample code";
var i = 0;
for (i = 0; i &lt; 10; i++) {
  str += i;
}</code>
    </directive>
    </root>""",
    )

    # Test a literally-included code block with copyable option specified
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.js
    :language: json
    :copyable: true
    :emphasize-lines: 5
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
  <directive name="literalinclude" language="json" emphasize-lines="5" copyable="True">
  <text>/test_parser/includes/sample_code.js</text>
  <code lang="json" emphasize_lines="[(5, 5)]" copyable="True">var str = "sample code";
var i = 0;
for (i = 0; i &lt; 10; i++) {
  str += i;
}</code>
    </directive>
    </root>""",
    )

    # Test a literally-included code block with fully specified options
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :caption: Sample Code
   :language: python
   :start-after: start example 1
   :end-before: end example 1
   :dedent: 4
   :linenos:
   :copyable: false
   :emphasize-lines: 1,2-4
   :lineno-start: 17
   :category: syntax
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude" caption="Sample Code" copyable="False" dedent="4" linenos="True" end-before="end example 1" language="python" start-after="start example 1" emphasize-lines="1,2-4" lineno-start="17" category="syntax">
        <text>/test_parser/includes/sample_code.py</text>
        <code emphasize_lines="[(1, 1), (2, 4)]" lang="python" caption="Sample Code" linenos="True" lineno_start="17" category="syntax">print("test dedent")</code>
        </directive>
        </root>""",
    )

    # Test failure to specify argument file
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude::
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], ExpectedPathArg)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude">
        </directive>
        </root>""",
    )

    # Test failure to locate included code file
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: includes/does_not_exist.js
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], CannotOpenFile)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude">
        <text>includes/does_not_exist.js</text>
        </directive>
        </root>""",
    )

    # Test failure to locate start-after text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :start-after: does not exist
   :end-before: end example 1
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude" start-after="does not exist" end-before="end example 1">
        <text>/test_parser/includes/sample_code.py</text>
        <code copyable="True">    # start example 1
    print("test dedent")</code>
        </directive>
        </root>""",
    )

    # Test failure to locate end-before text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :start-after: start example 1
   :end-before: does not exist
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude" start-after="start example 1" end-before="does not exist">
        <text>/test_parser/includes/sample_code.py</text>
        <code copyable="True">    print("test dedent")
    # end example 1

    # start example 2
    print("hello world")
    # end example 2
    </code></directive>
        </root>""",
    )

    # Test start-after text is below end-before text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :start-after: start example 2
   :end-before: end example 1
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude" start-after="start example 2" end-before="end example 1">
        <text>/test_parser/includes/sample_code.py</text>
        <code copyable="True"></code>
        </directive>
        </root>""",
    )

    # Test poorly specified linenos: out-of-bounds (greater than file length)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :emphasize-lines: 100
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)

    # Test poorly specified linenos: out-of-bounds (negative)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :emphasize-lines: -1
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)

    # Test poorly specified linenos: wrong order (expects 2 < 1)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :emphasize-lines: 2-1
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], InvalidLiteralInclude)

    # Test poorly specified dedent
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :dedent: True
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test poorly specified arbitrary string option
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :start-after:
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test empty caption
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :caption:
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test empty category
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_code.py
   :category:
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)

    # Test non-textual
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /compass-explain-plan-with-index-raw-json.png
        """,
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert [(type(d), "utf-8" in d.message) for d in diagnostics] == [
        (CannotOpenFile, True)
    ]

    # Test that literalinclude start-after/end-before matching doesn't incorrectly match subsets of a given line (DOP-3531)
    # This prevents incorrectly greedy matching of e.g. "sampleAggregation" when what you want is "sample"
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. literalinclude:: /test_parser/includes/sample_prefixes.c
    :start-after: begin sample
    :end-before: end sample
        """,
    )
    page.finish(diagnostics)
    assert [type(x) for x in diagnostics] == [
        AmbiguousLiteralInclude,
        AmbiguousLiteralInclude,
    ]
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="literalinclude" start-after="begin sample" end-before="end sample">
        <text>/test_parser/includes/sample_prefixes.c</text>
        <code copyable="True">sampleContent</code>
        </directive>
        </root>""",
    )


def test_include() -> None:
    path = FileId("test.rst")
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
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="include">
        <text>/driver-examples/rstexample.rst</text>
        </directive>
        </root>""",
    )

    # Test include with start-after and end-before options
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. include:: /test_parser/includes/sample_rst.rst
    :start-after: start after text
    :end-before: end before text
        """,
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="include" start-after="start after text" end-before="end before text">
        <text>/test_parser/includes/sample_rst.rst</text>
        </directive>
        </root>""",
    )


def test_admonition() -> None:
    path = FileId("test.rst")
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
        """<root fileid="test.rst">
        <directive name="note">
        <list enumtype="unordered"><listItem><paragraph><text>foo</text></paragraph></listItem>
        <listItem><paragraph><text>bar</text></paragraph></listItem></list>
        </directive>
        </root>""",
    )


def test_admonition_versionchanged() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. versionchanged:: v3.2

   Content

.. versionchanged:: v3.2
   Content

.. versionchanged:: v3.2

.. versionchanged::

   Content
""",
    )
    page.finish(diagnostics)
    assert [type(diag) for diag in diagnostics] == [DocUtilsParseError]
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="versionchanged"><text>v3.2</text>
            <paragraph><text>Content</text></paragraph>
        </directive>

        <directive name="versionchanged"><text>v3.2</text>
            <text>Content</text>
        </directive>

        <directive name="versionchanged"><text>v3.2</text></directive>
        </root>""",
    )


def test_admonition_deprecated() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. deprecated:: v3.2

   Content

.. deprecated::

   Content
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="deprecated"><text>v3.2</text>
            <paragraph><text>Content</text></paragraph>
        </directive>
        <directive name="deprecated">
            <paragraph><text>Content</text></paragraph>
        </directive>
        </root>""",
    )


def test_banner() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. banner::
    :variant: warning

    Content
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    print(page.ast)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive domain="mongodb" name="banner" variant="warning">
            <paragraph><text>Content</text></paragraph>
        </directive>
        </root>""",
    )


def test_cta_banner() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test valid cta-banner
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. cta-banner::
   :url: https://university.mongodb.com/
   :icon: University

   If you prefer learning through videos, try this lesson on `MongoDB University
   <https://university.mongodb.com/>`_
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive domain="mongodb" name="cta-banner" url="https://university.mongodb.com/" icon="University">
            <paragraph>
                <text>If you prefer learning through videos, try this lesson on </text>
                <reference refuri="https://university.mongodb.com/"><text>MongoDB University</text></reference>
                <named_reference refname="MongoDB University" refuri="https://university.mongodb.com/"></named_reference>
            </paragraph>
        </directive></root>""",
    )

    # Test cta-banner without url option specified
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. cta-banner::

   If you prefer learning through videos, try this lesson on `MongoDB University
   <https://university.mongodb.com/>`_
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], DocUtilsParseError)
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive domain="mongodb" name="cta-banner">
            <paragraph><text>If you prefer learning through videos, try this lesson on </text>
            <reference refuri="https://university.mongodb.com/"><text>MongoDB University</text></reference>
            <named_reference refname="MongoDB University" refuri="https://university.mongodb.com/"></named_reference>
            </paragraph>
        </directive></root>""",
    )


def test_rst_replacement() -> None:
    path = FileId("test.rst")
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
        """<root fileid="test.rst">
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
        """<root fileid="test.rst">
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
        """<root fileid="test.rst">
        <paragraph>
        <text>foo </text>
        <substitution_reference name="bar"></substitution_reference>
        </paragraph>
        </root>""",
    )


def test_labels() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # test label starting with a number
    page, diagnostics = parse_rst(
        parser,
        path,
        """
:ref:`100_stacked_example`

.. _100_stacked_example:
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []

    ast = page.ast
    check_ast_testing_string(
        ast,
        """
        <root fileid="test.rst">
        <paragraph>
                <ref_role domain="std" name="label" target="100_stacked_example"/>
        </paragraph>
        <target domain="std" name="label">
                <target_identifier ids="['100_stacked_example']" />
        </target>
        </root>
        """,
    )


def test_roles() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test both forms of :manual: (an extlink), :rfc: (explicit title),
    # :binary: (rstobject), and :guilabel: (plain text)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. binary:: mongod

.. readconcern:: snapshot
   :hidden:

* :manual:`/introduction/`
* :manual:`Introduction to MongoDB </introduction/>`
* :rfc:`1149`
* :rfc:`RFC-1149 <1149>`
* :issue:`TOOLS-2456`
* :issue:`this jira issue <TOOLS-2456>`
* :binary:`~bin.mongod`
* :binary:`mongod <~bin.mongod>`
* :guilabel:`Test <foo>`
* :term:`<foo>`
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        r"""<root fileid="test.rst">
            <target domain="mongodb" name="binary">
                <directive_argument><literal><text>mongod</text></literal></directive_argument>
                <target_identifier ids="['bin.mongod']"><text>mongod</text></target_identifier>
            </target>
            <target domain="mongodb" name="readconcern" hidden="True">
                <directive_argument><literal><text>snapshot</text></literal></directive_argument>
                <target_identifier ids="['readconcern.snapshot']"><text>snapshot</text></target_identifier>
            </target>
            <list enumtype="unordered">
            <listItem>
            <paragraph>
            <reference refuri="https://www.mongodb.com/docs/manual/introduction/">
            <text>/introduction/</text>
            </reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://www.mongodb.com/docs/manual/introduction/">
            <text>Introduction to MongoDB</text></reference></paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://tools.ietf.org/html/1149"><text>RFC-1149</text></reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://tools.ietf.org/html/1149"><text>RFC-1149</text></reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://jira.mongodb.org/browse/TOOLS-2456"><text>TOOLS-2456</text></reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <reference refuri="https://jira.mongodb.org/browse/TOOLS-2456"><text>this jira issue</text></reference>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <ref_role flag="~" domain="mongodb" name="binary" target="bin.mongod"><literal />
            </ref_role>
            </paragraph>
            </listItem>
            <listItem>
            <paragraph>
            <ref_role flag="~"
                  domain="mongodb"
                  name="binary"
                  target="bin.mongod"><literal><text>mongod</text></literal></ref_role>
            </paragraph>
            </listItem>

            <listItem>
            <paragraph>
            <role name="guilabel">
            <text>Test &lt;foo&gt;</text>
            </role>
            </paragraph>
            </listItem>

            <listItem>
            <paragraph>
            <ref_role domain="std" name="term" target="foo"></ref_role>
            </paragraph>
            </listItem>
            </list>
            </root>""",
    )


def test_doc_role() -> None:
    project_root = ROOT_PATH.joinpath("test_project")
    fileid = FileId("test.rst")
    project_config = ProjectConfig(project_root, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test bad text
    page, diagnostics = parse_rst(
        parser,
        fileid,
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
        fileid,
        """
* :doc:`Testing this </index>`
* :doc:`Testing that <./../source/index>`
* :doc:`index`
* :doc:`/index`
* :doc:`./../source/index`
* :doc:`/index/`
* :doc:`/`
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
        <root fileid="test.rst">
        <list enumtype="unordered">
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['/index', '']">
        <text>Testing this</text>
        </ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['./../source/index', '']">
        <text>Testing that</text>
        </ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['index', '']"></ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['/index', '']"></ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['./../source/index', '']"></ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['/index/', '']"></ref_role>
        </paragraph>
        </listItem>
        <listItem>
        <paragraph>
        <ref_role domain="std" name="doc" fileid="['/index', '']"></ref_role>
        </paragraph>
        </listItem>
        </list>
        </root>""",
    )


def test_rstobject() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test both forms of :manual: (an extlink), :rfc: (explicit title),
    # :binary: (rstobject), and :guilabel: (plain text)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. option:: --slowms <integer>

   test
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
            <target domain="std" name="option">
            <directive_argument><literal><text>--slowms &lt;integer&gt;</text></literal></directive_argument>
            <target_identifier ids="['--slowms']"><text>--slowms</text></target_identifier>
            <paragraph><text>test</text></paragraph>
            </target>
            </root>""",
    )


def test_bad_option() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. option:: =
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    print(ast_to_testing_string(page.ast))
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
            <target domain="std" name="option">
            <directive_argument><literal><text>=</text></literal></directive_argument>
            </target>
            </root>""",
    )


def test_accidental_indentation() -> None:
    path = FileId("test.rst")
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
        """<root fileid="test.rst">
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


def test_figure() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test good figures in variety of file formats
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: /test_parser/sample@2x.png
   :alt: sample png

.. figure:: /test_parser/sample.jpg
   :alt: sample jpeg

.. figure:: /test_project/source/general-features-tools.svg
   :alt: sample svg
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="figure" alt="sample png" checksum="af4fbbc65c96b5c8f6f299769e2783b4ab7393f047debc00ffae772b9c5a7665" width="100.0" height="100.0">
        <text>/test_parser/sample@2x.png</text>
    </directive>
    <directive name="figure" alt="sample jpeg" checksum="423345d0e4268d547aeaef46b74479f5df6e949d2b3288de1507f1f3082805ae" width="100.0" height="100.0">
        <text>/test_parser/sample.jpg</text>
    </directive>
    <directive name="figure" alt="sample svg" checksum="d769706e8087b6f08954b7f66d0cb167bc73f669c3d4b2ebb4af4de27e51c54f" width="56.0" height="56.0">
        <text>/test_project/source/general-features-tools.svg</text>
    </directive>
</root>""",
    )

    # Test good figure with all options
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: /test_parser/sample.png
   :alt: sample png
   :figwidth: 100
   :width: 90
   :scale: 1
   :align: left
   :lightbox:
   :class: class
   :border:

""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="figure" alt="sample png" checksum="af4fbbc65c96b5c8f6f299769e2783b4ab7393f047debc00ffae772b9c5a7665"
        align="left" border="True" class="class" figwidth="100" lightbox="True" scale="1" width="90" height="90.0">
        <text>/test_parser/sample.png</text>
    </directive>
</root>""",
    )

    # No filepath supplied
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure::
   :alt: no figure
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    # No file found
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: fake_figure.png
   :alt: missing figure file
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    # Missing required alt text
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: /test_parser/sample.png
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1


def test_atf_image() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test good atf-image with all options
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. atf-image:: /test_parser/sample.png
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="atf-image" checksum="af4fbbc65c96b5c8f6f299769e2783b4ab7393f047debc00ffae772b9c5a7665" width="100.0" height="100.0">
        <text>/test_parser/sample.png</text>
    </directive>
</root>""",
    )

    # No filepath supplied
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. atf-image::
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    # No file found
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. atf-image:: fake_atf-image.png
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1


def test_glossary_node() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. glossary::
  :sorted:

  _id
    foofoobarbar

  index
    foofoofoofoobarbarbarbar

  Upper Case
    This should not be first

  $cmd
    foobar

  aggregate
    foofoofoobarbarbar


""",
    )
    page.finish(diagnostics)

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
  <directive name="glossary" sorted="True">
    <definitionList>
      <definitionListItem>
        <term>
          <text>$cmd</text>
          <inline_target domain="std" name="term">
            <target_identifier ids="['$cmd']">
              <text>$cmd</text></target_identifier>
          </inline_target>
        </term>
        <paragraph><text>foobar</text></paragraph>
      </definitionListItem>

      <definitionListItem>
        <term>
          <text>_id</text>
          <inline_target domain="std" name="term">
            <target_identifier ids="['_id']">
              <text>_id</text>
            </target_identifier>
          </inline_target>
        </term>
        <paragraph><text>foofoobarbar</text></paragraph>
      </definitionListItem>

      <definitionListItem>
        <term>
          <text>aggregate</text>
          <inline_target domain="std" name="term">
            <target_identifier ids="['aggregate']">
              <text>aggregate</text></target_identifier>
          </inline_target>
        </term>
        <paragraph><text>foofoofoobarbarbar</text></paragraph>
      </definitionListItem>

      <definitionListItem>
        <term>
          <text>index</text>
          <inline_target domain="std" name="term">
            <target_identifier ids="['index']">
              <text>index</text></target_identifier>
          </inline_target>
        </term>
        <paragraph><text>foofoofoofoobarbarbarbar</text></paragraph>
      </definitionListItem>

      <definitionListItem>
        <term>
          <text>Upper Case</text>
          <inline_target domain="std" name="term">
            <target_identifier ids="['Upper Case']">
              <text>Upper Case</text></target_identifier>
          </inline_target>
        </term>
        <paragraph><text>This should not be first</text></paragraph>
      </definitionListItem>

    </definitionList>
  </directive>
</root>
""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. glossary::
  :sorted:

""",
    )

    page.finish(diagnostics)

    assert len(diagnostics) == 0

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. glossary::

  _id
    foo

  This is a paragraph, not a definition list item.

""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], MalformedGlossary)


def test_cond() -> None:
    path = FileId("test.rst")
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
        """<root fileid="test.rst">
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


def test_version() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. versionchanged:: 2.0
    This is some modified content.

    This is a child that should also be rendered here.

This paragraph is not a child.
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="versionchanged">
        <text>
        2.0
        </text>
        <text>
        This is some modified content.
        </text>
        <paragraph>
        <text>This is a child that should also be rendered here.</text>
        </paragraph>
        </directive>
        <paragraph>
        <text>This paragraph is not a child.</text>
        </paragraph>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. deprecated:: 1.8

A new paragraph.
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="deprecated">
        <text>
        1.8
        </text>
        </directive>
        <paragraph>
        <text>A new paragraph.</text>
        </paragraph>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. versionadded:: 2.1
    A description that includes *emphasized* text.

    A child paragraph.
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="versionadded">
        <text>
        2.1
        </text>
        <text>A description that includes </text>
        <emphasis><text>emphasized</text></emphasis>
        <text> text.</text>
        <paragraph>
        <text>A child paragraph.</text>
        </paragraph>
        </directive>
        </root>""",
    )


def test_list() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
- First bulleted item
- Second
- Third
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <list enumtype="unordered">
        <listItem><paragraph><text>First bulleted item</text></paragraph></listItem>
        <listItem><paragraph><text>Second</text></paragraph></listItem>
        <listItem><paragraph><text>Third</text></paragraph></listItem>
        </list>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
a. First list item
#. Second
#. Third

e. Fifth list item
#. Sixth
#. Seventh
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <list enumtype="loweralpha">
        <listItem><paragraph><text>First list item</text></paragraph></listItem>
        <listItem><paragraph><text>Second</text></paragraph></listItem>
        <listItem><paragraph><text>Third</text></paragraph></listItem>
        </list>
        <list enumtype="loweralpha" startat="5">
        <listItem><paragraph><text>Fifth list item</text></paragraph></listItem>
        <listItem><paragraph><text>Sixth</text></paragraph></listItem>
        <listItem><paragraph><text>Seventh</text></paragraph></listItem>
        </list>
        </root>""",
    )


def test_list_table() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Correct list-table
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38 72

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
       .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Excess rows
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38 72

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
     - .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1

    # No width option variant
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
       .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Comma-separated width option should not fail
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38,72

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
       .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # ", "-separated width option should not fail
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38, 72

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
       .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # "  "-separated width option should not fail
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38  72

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
       .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Incorrectly delimited width option should not fail
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :header-rows: 1
   :widths: 38,,72

   * - Stage
     - Description
     - Description 2

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst
     - .. include:: /includes/extracts/geoNear-stage-index-requirement.rst
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Nesting
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :widths: 38 72
   :header-rows: 1

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - .. include:: /includes/extracts/geoNear-stage-toc-description.rst

       + More nesting
       + Some description
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0

    # Nested list-tables
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :widths: 38 72
   :header-rows: 1

   * - Stage
     - Description

   * - :pipeline:`$geoNear`
     - Text here

       .. list-table::
          :widths: 30 30 40

          * - Stage
            - This is a cell
            - *text*

          * - :pipeline:`$geoNear`
            - Table cell
            - Testing Table cell
""",
    )
    assert len(diagnostics) == 0

    # Empty list-table
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
   :widths: 38 72
   :header-rows: 1
""",
    )
    assert len(diagnostics) == 0

    # Broken list-table
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::

   * -Java (Synchronous) version 4.7.0-beta0 or later.
     - MongoCrypt version 1.5.0-rc2 or later
""",
    )
    print(ast_to_testing_string(page.ast))
    assert [type(x) for x in diagnostics] == [InvalidTableStructure]

    # Only header rows
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. list-table::
    :header-rows: 1

    * - This is part of an invalid row and table
      - This is also part of an invalid row and table
      - This is the final part of the invalid row and table
    """,
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [InvalidTableStructure]
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst"></root>""",
    )


def test_footnote() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. [#footnote-test]

    This is an example of what a footnote looks like.

    It may have multiple children.
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <footnote id="footnote-test" name="footnote-test">
        <paragraph>
        <text>This is an example of what a footnote looks like.</text>
        </paragraph>
        <paragraph>
        <text>It may have multiple children.</text>
        </paragraph>
        </footnote>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. [#]
    This is an autonumbered footnote.
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <footnote id="id1">
        <paragraph>
        <text>This is an autonumbered footnote.</text>
        </paragraph>
        </footnote>
        </root>""",
    )

    # Test that docutils <label> nodes do not crash the parser.
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:manual:`eval </reference/command/eval>` [1]_

.. [1] MongoDB 4.2 doesn't support these commands.
""",
    )
    page.finish(diagnostics)
    assert not diagnostics


def test_footnote_reference() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
This is a footnote [#test-footnote]_ in use.
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <paragraph>
        <text>This is a footnote</text>
        <footnote_reference id="id1" refname="test-footnote" />
        <text> in use.</text>
        </paragraph>
        </root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
This is an autonumbered footnote [#]_ in use.
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <paragraph>
        <text>This is an autonumbered footnote</text>
        <footnote_reference id="id1" />
        <text> in use.</text>
        </paragraph>
        </root>""",
    )


def test_toctree() -> None:
    project_root = ROOT_PATH.joinpath("test_project")
    [project_config, project_config_diagnostics] = ProjectConfig.open(project_root)
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        FileId("test.rst"),
        """
.. toctree::
   :titlesonly:

   Title here </test1>
   /test2/faq
   URL with title <https://www.mongodb.com/docs/atlas>
   Associated Product <|non-existent-associated|>
   Associated Product <|test-name|>
   <https://www.mongodb.com/docs/stitch>
""",
    )
    page.finish(diagnostics)
    assert (
        len(diagnostics) == 2
        and "toctree" in diagnostics[0].message
        and "toctree" in diagnostics[1].message
    )
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst">
        <directive name="toctree" titlesonly="True" entries="[{'title': 'Title here', 'slug': '/test1'}, {'slug': '/test2/faq'}, {'title': 'URL with title', 'url': 'https://www.mongodb.com/docs/atlas'}, {'title': 'Associated Product', 'ref_project': 'test-name'}]" />
        </root>""",
    )


def test_callable_target() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. method:: db.collection.ensureIndex (keys, options)

   Creates an index on the specified field if the index does not already exist.

* :method:`db.collection.ensureIndex(keys, options)`
* :method:`db.collection.ensureIndex()`
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <target domain="mongodb" name="method">
    <directive_argument><literal><text>db.collection.ensureIndex (keys, options)</text></literal></directive_argument>
    <target_identifier ids="['db.collection.ensureIndex']"><text>db.collection.ensureIndex()</text></target_identifier>
    <paragraph>
    <text>Creates an index on the specified field if the index does not already exist.</text>
    </paragraph>
    </target>
    <list enumtype="unordered">
    <listItem><paragraph>
        <ref_role domain="mongodb" name="method" target="db.collection.ensureIndex"><literal /></ref_role>
    </paragraph></listItem>
    <listItem><paragraph>
        <ref_role domain="mongodb" name="method" target="db.collection.ensureIndex"><literal /></ref_role>
    </paragraph></listItem>
    </list>
</root>""",
    )

    # Ensure that a missing argument doesn't crash
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. method::

   Creates an index.
""",
    )
    page.finish(diagnostics)
    assert [type(diag) for diag in diagnostics] == [DocUtilsParseError]
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst"></root>""",
    )


def test_no_weird_targets() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
`universal link <ios-universal-links_>`_

`universal link <ios-universal-links_>`_

.. _ios-universal-links: https://developer.apple.com/library/content/documentation/General/Conceptual/AppSearch/UniversalLinks.html
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 2
    assert isinstance(diagnostics[0], InvalidURL) and isinstance(
        diagnostics[1], InvalidURL
    )


def test_dates() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. pubdate:: 2020-03-04

.. updated-date:: March 5, 2020
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="pubdate" date="2020-03-04"></directive>
    <directive name="updated-date"></directive>
</root>
""",
    )


def test_problematic() -> None:
    """Test that "<problematic>" nodes by the docutils parser --- typically when a
    role isn't known --- are excluded from the output AST. We might change this
    behavior, but for now we should define it."""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:bad-role-unknown:`Server write commands </server_write_commands.rst>`
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    check_ast_testing_string(
        page.ast, '<root fileid="test.rst"><paragraph></paragraph></root>'
    )


def test_deprecated() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. raw:: html

   <div>Test raw directive</div>
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    check_ast_testing_string(
        page.ast,
        """<root fileid="test.rst"></root>""",
    )


def test_definition_list() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
A term
  A definition for this term.

``Another term``
  A definition for *THIS* term.""",
    )

    assert not diagnostics

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <definitionList>
        <definitionListItem>
            <term><text>A term</text></term>
            <paragraph><text>A definition for this term.</text></paragraph>
        </definitionListItem>
        <definitionListItem>
            <term><literal><text>Another term</text></literal></term>
            <paragraph><text>A definition for </text><emphasis><text>THIS</text></emphasis><text> term.</text></paragraph>
        </definitionListItem>
    </definitionList>
</root>
""",
    )

    # Test a bizarre case
    page, diagnostics = parse_rst(
        parser,
        path,
        """
collection.createIndex( { name : -1 }, function(err, result) {
    console.log
""",
    )

    assert not diagnostics

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <definitionList>
        <definitionListItem>
            <term><text>collection.createIndex( { name : -1 }, function(err, result) {</text></term>
            <paragraph><text>console.log</text></paragraph>
        </definitionListItem>
    </definitionList>
</root>
""",
    )


def test_required_option() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: compass-create-database.png""",
    )
    assert [type(d) for d in diagnostics] == [DocUtilsParseError]

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. figure:: compass-create-database.png
   :alt: alt text""",
    )
    assert [type(d) for d in diagnostics] == []


def test_fields() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. method:: utils.jwt.encode()

   Generates an encoded JSON Web Token string for the ``payload`` based
   on the specified ``signingMethod`` and ``secret``.

   :returns:
       A JSON Web Token string encoded for the provided ``payload``.
""",
    )
    page.finish(diagnostics)
    assert diagnostics == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <target domain="mongodb" name="method">
    <directive_argument><literal><text>utils.jwt.encode()</text></literal></directive_argument>
    <target_identifier ids="['utils.jwt.encode']"><text>utils.jwt.encode()</text></target_identifier>
    <paragraph>
    <text>Generates an encoded JSON Web Token string for the </text><literal><text>payload</text></literal><text> based
on the specified </text><literal><text>signingMethod</text></literal><text> and </text><literal><text>secret</text></literal><text>.</text>
    </paragraph>
    <field_list><field name="returns" label="Returns"><paragraph><text>A JSON Web Token string encoded for the provided </text><literal><text>payload</text></literal><text>.</text></paragraph></field></field_list>
    </target>
</root>""",
    )

    # Test invalid field
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. method:: utils.crypto.encrypt()

   Generates an encrypted text string from the provided text using the
   specified encryption method and key.

   :invalid:
""",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], InvalidField)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <target domain="mongodb" name="method">
    <directive_argument><literal><text>utils.crypto.encrypt()</text></literal></directive_argument>
    <target_identifier ids="['utils.crypto.encrypt']"><text>utils.crypto.encrypt()</text></target_identifier>
    <paragraph>
    <text>Generates an encrypted text string from the provided text using the
specified encryption method and key.</text>
    </paragraph>
    <field_list></field_list>
    </target>
</root>""",
    )


def test_malformed_monospace() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, InlineJSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """`malformed syntax`""",
    )
    page.finish(diagnostics)
    assert [
        (type(d), d.did_you_mean() if isinstance(d, MakeCorrectionMixin) else "")
        for d in diagnostics
    ] == [(IncorrectMonospaceSyntax, ["``malformed syntax``"])]
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst"><literal><text>malformed syntax</text></literal></root>
""",
    )


def test_malformed_external_link() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, InlineJSONVisitor)

    page, diagnostics = parse_rst(
        parser, path, """`Atlas Data Lake <https://www.mongodb.com/docs/datalake/>`"""
    )
    page.finish(diagnostics)
    assert [
        (type(d), d.did_you_mean() if isinstance(d, MakeCorrectionMixin) else "")
        for d in diagnostics
    ] == [
        (
            IncorrectLinkSyntax,
            ["`Atlas Data Lake <https://www.mongodb.com/docs/datalake/>`__"],
        )
    ]
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst"><literal><text>Atlas Data Lake &lt;https://www.mongodb.com/docs/datalake/&gt;</text></literal></root>
""",
    )


def test_explicit_title_parsing() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
.. writeconcern:: <custom write concern name>

:writeconcern:`w:1 <\<custom write concern name\>>`""",
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        r"""
<root fileid="test.rst">
    <target domain="mongodb" name="writeconcern">
        <directive_argument>
            <literal><text>&lt;custom write concern name&gt;</text></literal>
        </directive_argument>
        <target_identifier ids="['writeconcern.&lt;custom write concern name&gt;']"><text>&lt;custom write concern name&gt;</text></target_identifier>
    </target>

    <paragraph>
        <ref_role domain="mongodb" name="writeconcern" target="writeconcern.&lt;custom write concern name&gt;">
            <literal><text>w:1</text></literal>
        </ref_role>
    </paragraph>
</root>
""",
    )


def test_invalid_blockquote() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
This is a paragraph.

   This is a blockquote.
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert [
        (type(d), d.did_you_mean() if isinstance(d, MakeCorrectionMixin) else "")
        for d in diagnostics
    ] == [
        (
            UnexpectedIndentation,
            [".. blockquote::"],
        )
    ]


def test_label_matches_heading() -> None:
    tabs_path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        tabs_path,
        """
.. _foobar-baz:

Foobar Baz
==========
""",
    )
    page.finish(diagnostics)
    assert not diagnostics

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <target domain="std" name="label">
        <target_identifier ids="['foobar-baz']"></target_identifier>
    </target>
    <section>
        <heading id="foobar-baz"><text>Foobar Baz</text></heading>
    </section>
</root>""",
    )


def test_duplicate_ref() -> None:
    """docutils changes the target node shape when duplicate labels are used. See: DOP-1326"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
==========
Index Page
==========

.. _a-heading:

A Heading
---------

.. _a-heading:

A Heading
---------
""",
    )

    page.finish(diagnostics)
    assert [type(x) for x in diagnostics] == [DocUtilsParseError]

    print(ast_to_testing_string(page.ast))
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <section>
        <heading id="index-page"><text>Index Page</text></heading>
        <target domain="std" name="label">
            <target_identifier ids="['a-heading']"></target_identifier>
        </target>
        <section>
            <heading id="a-heading"><text>A Heading</text></heading>
            <target domain="std" name="label">
                <target_identifier ids="['a-heading']"></target_identifier>
            </target>
        </section>
        <section>
            <heading id="a-heading"><text>A Heading</text></heading>
        </section>
    </section>
</root>""",
    )


def test_trailing_slash() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Link to :compass:`Compass </>`
Link to :charts:`Charts </path>`
Link to :atlas:`Atlas </path#hash>`
Link to :guides:`Guides </path/#hash>`
Link to :cloudmgr:`Cloud Manager file </test.csv>`
Link to :opsmgr:`Ops Manager </page?q=true>`
""",
    )

    page.finish(diagnostics)
    assert not diagnostics

    print(ast_to_testing_string(page.ast))
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
<paragraph>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/compass/current/"><text>Compass</text></reference>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/charts/path/"><text>Charts</text></reference>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/atlas/path/#hash"><text>Atlas</text></reference>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/guides/path/#hash"><text>Guides</text></reference>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/cloud-manager/test.csv"><text>Cloud Manager file</text></reference>
    <text>Link to </text><reference refuri="https://www.mongodb.com/docs/ops-manager/current/page/?q=true"><text>Ops Manager</text></reference>
</paragraph>
</root>
""",
    )


def test_escape() -> None:
    """Ensure that escaping characters after a substitution results in the proper output."""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # DOP-2196: Writers discovered that an |adl|\s substitution resulted in a box character rendering
    # after Atlas Data Lake.
    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
.. |adl| replace:: Atlas Data Lake

|adl|\ss
""",
    )

    page.finish(diagnostics)
    assert not diagnostics

    print(repr(ast_to_testing_string(page.ast)))
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <substitution_definition name="adl"><text>Atlas Data Lake</text></substitution_definition>
    <paragraph><substitution_reference name="adl"></substitution_reference><text>ss</text></paragraph>
</root>""",
    )


def test_directive_line_offset() -> None:
    """Ensure that line numbers are correctly tracked inside of directives."""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r""".. _kotlin-multiplatform-install:

========================================
Install Realm - Kotlin Multiplatform SDK
========================================

.. default-domain:: mongodb

Prerequisites
-------------

.. warning::

   You can track an issue with line numbers in :github:`this GitHub issue
   <https://github.com/mongodb/snooty-parser/pull/328>`__.

.. include:: /includes/steps/install-kotlin-multiplatform.rst
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert diagnostics[0].start[0] == 13


def test_field_list_in_list() -> None:
    """Tests DOP-2975"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
a. :hash: json

#. :hash: json
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 2


def test_invalid_utf8() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): b"""test line 1
test line 2
here is an invalid character sequence\x80 oh noooo
"""
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert [(type(d), d.start[0]) for d in diagnostics] == [(CannotOpenFile, 2)]


def test_valid_icon() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:icon:`trash-alt`
""",
    )
    page.finish(diagnostics)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <paragraph>
        <role name="icon" target="trash-alt"></role>
    </paragraph>
</root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:icon-fa5-brands:`Windows logo <windows>`
""",
    )
    page.finish(diagnostics)
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <paragraph>
        <role name="icon-fa5-brands" target="windows"><text>Windows logo</text></role>
    </paragraph>
</root>""",
    )


def test_invalid_icon() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:icon:`ICON-DNE`
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], IconMustBeDefined)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:icon-fa4:`shunned`
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], IconMustBeDefined)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
:icon-mms:`ellipsis`
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0


def test_invalid_string_argument() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
.. openapi-changelog::
   :api-version: 2.0
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 1
    print(diagnostics)
    assert isinstance(diagnostics[0], ExpectedStringArg)


def test_missing_expected_option() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
.. openapi-changelog:: cloud
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 1
    print(diagnostics)
    assert isinstance(diagnostics[0], ExpectedOption)


def test_invalid_changelog_option() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
.. openapi-changelog:: cloud
   :api-version: 1.0
""",
    )

    page.finish(diagnostics)
    assert len(diagnostics) == 1
    print(diagnostics)
    assert isinstance(diagnostics[0], DocUtilsParseError)


def test_standalone_literal_block() -> None:
    # Issues here discovered in DOP-3753
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"::",
    )
    page.finish(diagnostics)
    assert isinstance(diagnostics[0], RemovedLiteralBlockSyntax)

    page, diagnostics = parse_rst(
        parser,
        path,
        r"""
foo

::

bar
""",
    )

    page.finish(diagnostics)
    assert isinstance(diagnostics[0], RemovedLiteralBlockSyntax)


def test_invalid_facets() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. facet::
    :name: dne
    :values: dne

.. facet::
    :name: genre
    :values: reference

    .. facet::
        :name: version
        :values: dne

.. facet::
    :name: target_product
    :values: atlas, dne

""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 3
    assert isinstance(diagnostics[0], MissingFacet)
    assert isinstance(diagnostics[1], MissingFacet)
    assert isinstance(diagnostics[2], MissingFacet)
    assert any(
        diagnostic.message.find("target_product:dne") != -1
        for diagnostic in diagnostics
    )

    # Regression test from DOP-4253
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. facet::

   :name: genre
   :values: tutorial
""",
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 3


def test_valid_facets() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. facet::
    :name: target_product
    :values: atlas

    .. facet::
        :name: sub_product
        :values: charts, atlas-cli
    """,
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 0


def test_duplicate_directive_option() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. meta::
   :keywords: multicluster
   :keywords: multi-cluster
    """,
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [DocUtilsParseError]


def test_inconsistent_levels() -> None:
    """DOP-3969"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Re-opening a section level is not permitted
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Query Result Format
-------------------

.. tabs-drivers::

   .. tab::
      :tabid: shell

      Additional Methods
      ------------------

      Testing
""",
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [DocUtilsParseError]
    print(ast_to_testing_string(page.ast))

    # Opening a new child level is fine
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Query Result Format
-------------------

.. tabs-drivers::

   .. tab::
      :tabid: shell

      Additional Methods
      ~~~~~~~~~~~~~~~~~~

      Testing
""",
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == []
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <section>
        <heading id="query-result-format"><text>Query Result Format</text></heading>
        <directive name="tabs" tabset="drivers">
            <directive name="tab" tabid="shell"><text>MongoDB Shell</text>
                <section>
                    <heading id="additional-methods"><text>Additional Methods</text></heading>
                    <paragraph><text>Testing</text></paragraph>
                </section>
            </directive>
        </directive>
    </section>
</root>
""",
    )

    # Ensuring for my own satisfaction that a diagnostic is raised if we try shenanigans in non-directive
    # block contexts.
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Query Result Format
-------------------

* Foobar
* Additional Methods
  ------------------

  Testing
""",
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [DocUtilsParseError]

    # A less trivial error case where a child section is opened, but then subsequently
    # the parent section is added to.
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Procedure
---------

.. tabs-platforms::

   .. tab::
      :tabid: windows

      Hello
      ~~~~~

      Example
      -------
""",
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [DocUtilsParseError]

    # Multiple sub-sections is fine
    page, diagnostics = parse_rst(
        parser,
        path,
        """
Procedure
---------

.. tabs-platforms::

   .. tab::
      :tabid: windows

      Hello
      ~~~~~

      Example
      ~~~~~~~
""",
    )
    page.finish(diagnostics)
    assert not diagnostics


def test_heading_immediately_after_directive_dop_4745() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. note:: /somepath
   {
""",
    )
    page.finish(diagnostics)
    assert not diagnostics

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive name="note"><paragraph><text>/somepath
{</text></paragraph>
    </directive>
</root>""",
    )


def test_collapsible() -> None:
    """Test collapsible directive"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. collapsible::
   :heading: This is a heading
   :sub_heading: This is a subheading

   This is collapsible content

   .. code-block:: javascript
      
      This is code within collapsible content
""",
    )

    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive domain="mongodb" name="collapsible" heading="This is a heading" sub_heading="This is a subheading" id="this-is-a-heading">
        <section>
            <paragraph><text>This is collapsible content</text></paragraph><code lang="javascript" copyable="True">This is code within collapsible content</code>
        </section>
    </directive>
</root>""",
    )

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. collapsible::
   :heading: This is a heading
   :sub_heading: This is a subheading

""",
    )
    assert len(diagnostics) == 1
    assert [type(d) for d in diagnostics] == [MissingChild]

    page, diagnostics = parse_rst(
        parser,
        path,
        """
========================
This is the main heading
========================


.. collapsible::
   :heading: This is a heading
   :sub_heading: This is a subheading

   There is a heading inside
   -------------------------

   And more content within
""",
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
   <section>
      <heading id="this-is-the-main-heading"><text>This is the main heading</text></heading>
        <directive domain="mongodb" name="collapsible" heading="This is a heading" sub_heading="This is a subheading" id="this-is-a-heading">
            <section>
                <section>
                    <heading id="there-is-a-heading-inside"><text>There is a heading inside</text></heading>
                    <paragraph><text>And more content within</text></paragraph>
                </section>
            </section>
        </directive>
   </section>
</root>""",
    )


def test_collapsible_options_true() -> None:
    """Test collapsible directive"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. collapsible::
   :heading: This is a heading
   :expanded: true

   This is default-expanded collapsible content
""",
    )

    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
    <directive domain="mongodb" name="collapsible" heading="This is a heading" id="this-is-a-heading" expanded="True">
        <section>
            <paragraph><text>This is default-expanded collapsible content</text></paragraph>
        </section>
    </directive>
</root>""",
    )


def test_wayfinding_sorted() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. wayfinding:: MongoDB for drivers
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: php
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: c

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: java-sync

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: scala

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: csharp
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: kotlin-coroutine

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: pymongo

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: mongoid

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: motor
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: python

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: nodejs

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: kotlin-sync

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: rust
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: java-rs

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: go

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: cpp

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: swift

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: typescript

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: ruby 

      
   .. wayfinding-description::

      This page is for mongosh. For pages specific to a driver, see the following:
    """,
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
	<directive domain="mongodb" name="wayfinding">
        <text>MongoDB for drivers</text>
        <directive domain="mongodb" name="wayfinding-description">
            <paragraph><text>This page is for mongosh. For pages specific to a driver, see the following:</text></paragraph>
        </directive>
		<directive domain="mongodb" name="wayfinding-option" id="csharp" title="C#" language="c#">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="java-sync" title="Java Sync" language="java">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="nodejs" title="Node.js" language="javascript">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="pymongo" title="PyMongo" language="python">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="c" title="C" language="c">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="cpp" title="C++" language="c++">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="go" title="Go" language="golang">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="java-rs" title="Java RS" language="java">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="kotlin-coroutine" title="Kotlin Coroutine" language="kotlin">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="kotlin-sync" title="Kotlin Sync" language="kotlin">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="php" title="PHP" language="php">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="motor" title="Motor" language="python">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="python" title="Python" language="python">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="mongoid" title="Mongoid" language="ruby">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
        <directive domain="mongodb" name="wayfinding-option" id="ruby" title="Ruby" language="ruby">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="rust" title="Rust" language="rust">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="scala" title="Scala" language="scala">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="swift" title="Swift" language="swift">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
		<directive domain="mongodb" name="wayfinding-option" id="typescript" title="Typescript" language="typescript">
			<reference refuri="https://www.mongodb.com/docs/">
				<text>https://www.mongodb.com/docs/</text>
			</reference>
		</directive>
	</directive>
</root>
""",
    )


def test_wayfinding_errors() -> None:
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test invalid syntax
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. wayfinding::

   Hello this is text
   
   .. wayfinding-option::
      :id: php
    
   .. note::

      This is an admonition that does not belong!
   
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: c

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: java-sync
    
   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: bad-id
   
   .. wayfinding-option:: https://www.mongodb.com/docs/

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: c
    
   .. wayfinding-description::

      This is a description of the wayfinding component
    """,
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [
        # Missing argument
        DocUtilsParseError,
        # Missing option
        DocUtilsParseError,
        # Paragraph
        InvalidChild,
        # Note
        InvalidChild,
        # bad-id
        UnknownOptionId,
        # Duplicate "c" id
        DuplicateOptionId,
    ]

    # Test missing children
    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. wayfinding::

    """,
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [MissingChild, MissingChild]


def test_method_selector() -> None:
    path = FileId("test.txt")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Valid case
    page, diagnostics = parse_rst(
        parser,
        path,
        """
=========
Test Page
=========

.. method-selector::
   
   .. method-option::
      :id: driver

      .. method-description::
         
         This is an optional description for drivers. Go to the `docs homepage <https://mongodb.com/docs/>`__ for more info.

      This only shows when driver is selected.

   .. method-option::
      :id: cli

      This only shows when cli is selected.

   .. method-option::
      :id: api

      This only shows when cli is selected.

   .. method-option::
      :id: mongosh

      This only shows when cli is selected.

   .. method-option::
      :id: compass

      .. method-description::
         
         This is an optional description for compass. Compass is a tool to interact with MongoDB data.

      This only shows when compass is selected.

   .. method-option::
      :id: ui

      This only shows when ui is selected.
    """,
    )
    page.finish(diagnostics)
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.txt">
    <section>
        <heading id="test-page">
            <text>Test Page</text>
        </heading>
        <directive domain="mongodb" name="method-selector">
            <directive domain="mongodb" name="method-option" id="driver" title="Driver">
                <directive domain="mongodb" name="method-description">
                    <paragraph>
                        <text>This is an optional description for drivers. Go to the </text>
                        <reference refuri="https://mongodb.com/docs/">
                            <text>docs homepage</text>
                        </reference>
                        <text> for more info.</text>
                    </paragraph>
                </directive>
                <paragraph>
                    <text>This only shows when driver is selected.</text>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="method-option" id="cli" title="CLI">
                <paragraph>
                    <text>This only shows when cli is selected.</text>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="method-option" id="api" title="API">
                <paragraph>
                    <text>This only shows when cli is selected.</text>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="method-option" id="mongosh" title="Mongosh">
                <paragraph>
                    <text>This only shows when cli is selected.</text>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="method-option" id="compass" title="Compass">
                <directive domain="mongodb" name="method-description">
                    <paragraph>
                        <text>This is an optional description for compass. Compass is a tool to interact with MongoDB data.</text>
                    </paragraph>
                </directive>
                <paragraph>
                    <text>This only shows when compass is selected.</text>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="method-option" id="ui" title="UI">
                <paragraph>
                    <text>This only shows when ui is selected.</text>
                </paragraph>
            </directive>
        </directive>
    </section>
</root>
""",
    )

    # Errors case
    page, diagnostics = parse_rst(
        parser,
        path,
        """
=========
Test Page
=========

.. method-selector::

   .. method-option::

      Missing option id.

   .. method-description::
      
      This does not belong here.

   .. method-option::
      :id: cli

      This only shows when cli is selected.

   .. method-option::
      :id: not-valid

      This only shows when cli is selected.

   .. method-option::
      :id: mongosh

      This only shows when cli is selected.
    
   .. method-option::
      :id: driver

      .. method-description::
         
         This is an optional description for drivers. Go to the `docs homepage <https://mongodb.com/docs/>`__ for more info.

      This only shows when driver is selected.

   .. method-option::
      :id: compass

      .. method-description::
         
         This is an optional description for compass. Compass is a tool to interact with MongoDB data.

      This only shows when compass is selected.

   .. method-option::
      :id: ui

      This only shows when ui is selected.

   .. method-option::
      :id: cli

      This only shows when cli is selected.
    """,
    )
    page.finish(diagnostics)
    assert [type(d) for d in diagnostics] == [
        # Missing option id
        DocUtilsParseError,
        # Extra method-description in method-selector
        InvalidChild,
        # not-valid option id
        UnknownOptionId,
        # driver option is not first
        UnexpectedDirectiveOrder,
        # Duplicate "cli" id
        DuplicateOptionId,
    ]


def test_video() -> None:
    path = FileId("test.txt")
    project_config = ProjectConfig(ROOT_PATH, "")
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Valid cases
    page, diagnostics = parse_rst(
        parser,
        path,
        """
=========
Test Page
=========

.. video:: https://www.youtube.com/embed/XrJG994YxD8
   
.. video:: https://www.youtube.com/embed/XrJG994YxD8
   :title: Mastering Indexing for Perfect Query Matches
   :description: In this video, we learn about how Atlas Search indexes can be used to optimize queries.
   :thumbnail-url: https://i.ytimg.com/vi/XrJG994YxD8/maxresdefault.jpg
   :upload-date: 2023-11-08T05:00:28-08:00

.. video:: https://www.youtube.com/embed/XrJG994YxD8
   :thumbnail-url: https://i.ytimg.com/vi/XrJG994YxD8/maxresdefault.jpg
   :upload-date: 2023-11-08

.. video:: https://www.youtube.com/embed/XrJG994YxD8
   :description: This is an educational video.
    """,
    )
    page.finish(diagnostics)
    assert len(diagnostics) == 2
    assert isinstance(diagnostics[0], MissingStructuredDataFields)
    assert "['title', 'description']" in diagnostics[0].message
    assert isinstance(diagnostics[1], MissingStructuredDataFields)
    assert "['title', 'thumbnail-url', 'upload-date']" in diagnostics[1].message

    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.txt">
    <section>
        <heading id="test-page"><text>Test Page</text></heading>
        <directive name="video">
            <reference refuri="https://www.youtube.com/embed/XrJG994YxD8">
                <text>https://www.youtube.com/embed/XrJG994YxD8</text>
            </reference>
        </directive>
        <directive name="video" title="Mastering Indexing for Perfect Query Matches" description="In this video, we learn about how Atlas Search indexes can be used to optimize queries." thumbnail-url="https://i.ytimg.com/vi/XrJG994YxD8/maxresdefault.jpg" upload-date="2023-11-08T05:00:28-08:00">
            <reference refuri="https://www.youtube.com/embed/XrJG994YxD8">
                <text>https://www.youtube.com/embed/XrJG994YxD8</text>
            </reference>
        </directive>
        <directive name="video" thumbnail-url="https://i.ytimg.com/vi/XrJG994YxD8/maxresdefault.jpg" upload-date="2023-11-08">
            <reference refuri="https://www.youtube.com/embed/XrJG994YxD8">
                <text>https://www.youtube.com/embed/XrJG994YxD8</text>
            </reference>
        </directive>
        <directive name="video" description="This is an educational video.">
            <reference refuri="https://www.youtube.com/embed/XrJG994YxD8">
                <text>https://www.youtube.com/embed/XrJG994YxD8</text>
            </reference>
        </directive>
    </section>
</root>
""",
    )

    # Error cases
    page, diagnostics = parse_rst(
        parser,
        path,
        """
=========
Test Page
=========

.. video:: https://www.youtube.com/embed/XrJG994YxD8
   :thumbnail-url: https://i.ytimg.com/vi/XrJG994YxD8/maxresdefault.jpg
   :upload-date: 11-11-2011
    """,
    )
    page.finish(diagnostics)
    # Diagnostic due to invalid upload-date format
    assert [type(x) for x in diagnostics] == [DocUtilsParseError]


def test_parse_ast() -> None:
    with make_test(
        {
            Path(
                "source/test.ast"
            ): """
{
    "type": "root",
    "children": [
        {
            "type": "section",
            "children": [
                {
                    "type": "heading",
                    "children": [
                        {
                            "type": "text",
                            "value": "Interface GridFSBucket"
                        }
                    ],
                    "id": "interface-gridfsbucket"
                },
                {
                    "type": "paragraph",
                    "children": [
                        {
                            "type": "reference",
                            "children": [
                                {
                                    "type": "text",
                                    "value": "@ThreadSafe"
                                }
                            ],
                            "refuri": "http://mongodb.github.io/mongo-java-driver/5.2/apidocs/mongodb-driver-core/com/mongodb/annotations/ThreadSafe.html"
                        }
                    ]
                },
                {
                    "type": "directive",
                    "name": "important",
                    "domain": "",
                    "argument": [
                        {
                            "type": "text",
                            "value": "Important Callout Heading"
                        }
                    ],
                    "children": [
                        {
                            "type": "paragraph",
                            "children": [
                                {
                                    "type": "text",
                                    "value": "Important Callout Body Text"
                                }
                            ]
                        }
                    ],
                    "options": {}
                }
            ]
        }
    ],
    "fileid": "test.txt",
    "options": {}
}
""",
            Path(
                "source/bad-types.ast"
            ): """
{
    "type": "root",
    "children": [
        {
            "type": "section",
            "children": [
                {
                    "type": "beep",
                    "children": [
                        {
                            "type": "text",
                            "value": "Interface GridFSBucket"
                        }
                    ],
                    "id": "interface-gridfsbucket"
                }
            ]
        }
    ],
    "fileid": "bad-types.txt",
    "options": {}
}
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("test.txt")]
        assert not diagnostics
        bad_types_diagnostics = result.diagnostics[FileId("bad-types.txt")]
        assert [type(d) for d in bad_types_diagnostics] == [UnexpectedNodeType]


def test_valid_composable_tutorial() -> None:
    """Test composable directive"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)

    page, diagnostics = parse_rst(
        parser,
        path,
        """
.. composable-tutorial::
   :options: interface, language, deployment-type, cloud-provider
   :defaults: driver, nodejs, atlas, gcp

   .. selected-content::
      :selections: driver, nodejs, atlas, gcp

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - NodeJS
      Deployment Type - Atlas
      Cloud Provider - GCP

   .. selected-content::
      :selections: driver, c, atlas, gcp

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - C
      Deployment Type - atlas
      Cloud Provider - GCP

   .. selected-content::
      :selections: driver, cpp, atlas, aws

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - CPP
      Deployment Type - atlas
      Cloud Provider - AWS


   .. selected-content::
      :selections: atlas-admin-api, None, atlas, gcp

      This content will only be shown when the selections are as follows:
      Interface - Atlas Admin API
      Deployment Type - atlas
      Cloud Provider - GCP


   .. selected-content::
      :selections: atlas-admin-api, None, atlas, aws

      This content will only be shown when the selections are as follows:
      Interface - Atlas Admin API
      Deployment Type - Atlas
      Cloud Provider - AWS



   .. selected-content::
      :selections: atlas-admin-api, None, self, aws

      This content will only be shown when the selections are as follows:
      Interface - Atlas Admin API
      Deployment Type - self
      Cloud Provider - AWS
""",
    )
    assert not diagnostics
    check_ast_testing_string(
        page.ast,
        """
<root fileid="test.rst">
   <directive domain="mongodb" name="composable-tutorial"
      composable_options="[{'value': 'interface', 'text': 'Interface', 'default': 'driver', 'dependencies': [], 'selections': [{'value': 'driver', 'text': 'Driver'}, {'value': 'atlas-admin-api', 'text': 'Atlas Admin API'}]}, {'value': 'language', 'text': 'Language', 'default': 'nodejs', 'dependencies': [{'interface': 'driver'}], 'selections': [{'value': 'nodejs', 'text': 'Node.js'}, {'value': 'c', 'text': 'C'}, {'value': 'cpp', 'text': 'C++'}]}, {'value': 'deployment-type', 'text': 'Deployment Type', 'default': 'atlas', 'dependencies': [], 'selections': [{'value': 'atlas', 'text': 'Atlas (Cloud)'}, {'value': 'self', 'text': 'Self-Managed (On-premises)'}]}, {'value': 'cloud-provider', 'text': 'Cloud Provider', 'default': 'gcp', 'dependencies': [], 'selections': [{'value': 'gcp', 'text': 'GCP'}, {'value': 'aws', 'text': 'AWS'}]}]">
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'driver', 'language': 'nodejs', 'deployment-type': 'atlas', 'cloud-provider': 'gcp'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Drivers
Language - NodeJS
Deployment Type - Atlas
Cloud Provider - GCP</text></paragraph>
      </directive>
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'driver', 'language': 'c', 'deployment-type': 'atlas', 'cloud-provider': 'gcp'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Drivers
Language - C
Deployment Type - atlas
Cloud Provider - GCP</text></paragraph>
      </directive>
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'driver', 'language': 'cpp', 'deployment-type': 'atlas', 'cloud-provider': 'aws'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Drivers
Language - CPP
Deployment Type - atlas
Cloud Provider - AWS</text></paragraph>
      </directive>
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'atlas-admin-api', 'language': 'None', 'deployment-type': 'atlas', 'cloud-provider': 'gcp'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Atlas Admin API
Deployment Type - atlas
Cloud Provider - GCP</text></paragraph>
      </directive>
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'atlas-admin-api', 'language': 'None', 'deployment-type': 'atlas', 'cloud-provider': 'aws'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Atlas Admin API
Deployment Type - Atlas
Cloud Provider - AWS</text></paragraph>
      </directive>
      <directive domain="mongodb" name="selected-content"
         selections="{'interface': 'atlas-admin-api', 'language': 'None', 'deployment-type': 'self', 'cloud-provider': 'aws'}">
         <paragraph><text>This content will only be shown when the selections are as follows:
Interface - Atlas Admin API
Deployment Type - self
Cloud Provider - AWS</text></paragraph>
      </directive>
   </directive>
</root>
""",
    )


def test_composable_tutorial_errors() -> None:
    """Test composable handle errors"""
    path = FileId("test.rst")
    project_config = ProjectConfig(ROOT_PATH, "", source="./")
    parser = rstparser.Parser(project_config, JSONVisitor)
    _page, diagnostics = parse_rst(
        parser,
        path,
        """
.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-providerrr
   :defaults: driverrr, nodejs, repl, gcp

   .. selected-content::
      :selections: driver, nodejs, repl, gcpppppp
""",
    )
    assert [type(d) for d in diagnostics] == [
        # invalid default driverrrr
        UnknownOptionId,
        # invalid composable tutorial option cloud-providerr
        UnknownOptionId,
        # invalid child count gcppgcpppppp
        InvalidChildCount,
    ]

    _page, diagnostics = parse_rst(
        parser,
        path,
        """
.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-provider
   :defaults: driver, nodejs, repl, gcp
""",
    )
    assert len(diagnostics) == 1
    assert type(diagnostics[0]) == MissingChild

    _page, diagnostics = parse_rst(
        parser,
        path,
        """
.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-provider
   :defaults: driver, None, repl, gcp

   .. selected-content::
      :selections: driver, nodejs, repl, gcp
""",
    )
    assert len(diagnostics) == 1
    assert type(diagnostics[0]) == UnknownOptionId

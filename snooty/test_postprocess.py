"""An alternative and more granular approach to writing postprocessing tests.
   Eventually most postprocessor tests should probably be moved into this format."""

from pathlib import Path

from . import diagnostics
from .diagnostics import (
    DuplicateDirective,
    ExpectedTabs,
    InvalidChild,
    InvalidContextError,
    InvalidIAEntry,
    MissingTab,
    MissingTocTreeEntry,
    SubstitutionRefError,
    TabMustBeDirective,
    TargetNotFound,
)
from .types import FileId
from .util_test import (
    ast_to_testing_string,
    check_ast_testing_string,
    check_toctree_testing_string,
    make_test,
)


def test_ia() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. ia::

   .. entry::
      :url: /page1

   .. entry:: Snooty Item
      :url: https://docs.mongodb.com/snooty/
      :project-name: snooty
      :primary:

   .. entry:: Invalid
      :project-name: invalid

   .. note::

.. ia::
""",
            Path(
                "source/page1.txt"
            ): """
==============
Page One Title
==============

.. ia::

   .. entry::
      :url: https://google.com

   .. entry::
      :url: /nonexistent

   .. entry:: Title

   .. entry:: Snooty Item Two
      :url: https://docs.mongodb.com/snooty/
      :project-name: snooty
""",
        }
    ) as result:

        active_file = "index.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 3
        assert isinstance(diagnostics[0], InvalidIAEntry)
        assert isinstance(diagnostics[1], InvalidChild)
        assert isinstance(diagnostics[2], DuplicateDirective)
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt" ia="[{'title': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Page One Title'}], 'slug': '/page1'}, {'title': [{'type': 'text', 'position': {'start': {'line': 6}}, 'value': 'Snooty Item'}], 'project_name': 'snooty', 'url': 'https://docs.mongodb.com/snooty/', 'primary': True}]">
<directive name="ia">
<directive name="entry" url="/page1" />
<directive name="entry" url="https://docs.mongodb.com/snooty/" project-name="snooty" primary="True">
<text>Snooty Item</text>
</directive>
<directive name="entry" project-name="invalid">
<text>Invalid</text>
</directive>
<directive name="note" />
</directive>
<directive name="ia" />
</root>
""",
        )

        active_file = "page1.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 3
        assert isinstance(diagnostics[0], InvalidIAEntry)
        assert isinstance(diagnostics[1], MissingTocTreeEntry)
        assert isinstance(diagnostics[2], InvalidIAEntry)
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="page1.txt" ia="[{'title': [{'type': 'text', 'position': {'start': {'line': 15}}, 'value': 'Snooty Item Two'}], 'project_name': 'snooty', 'url': 'https://docs.mongodb.com/snooty/', 'primary': False}]">
<section>
<heading id="page-one-title"><text>Page One Title</text></heading>
<directive name="ia">
<directive name="entry" url="https://google.com" />
<directive name="entry" url="/nonexistent" />
<directive name="entry">
<text>Title</text>
</directive>
<directive name="entry" url="https://docs.mongodb.com/snooty/" project-name="snooty">
<text>Snooty Item Two</text>
</directive>
</directive>
</section>
</root>
""",
        )
        check_toctree_testing_string(
            result.metadata["iatree"],
            """
<toctree slug="/">
    <title><text>untitled</text></title>
    <toctree slug="/page1">
        <title><text>Page One Title</text></title>
        <toctree url="https://docs.mongodb.com/snooty/" project_name="snooty">
            <title><text>Snooty Item Two</text></title>
        </toctree>
    </toctree>
    <toctree url="https://docs.mongodb.com/snooty/" project_name="snooty" primary="True">
        <title><text>Snooty Item</text></title>
    </toctree>
</toctree>
""",
        )


# ensure that broken links still generate titles
def test_broken_link() -> None:
    with make_test(
        {
            Path(
                "source/param.txt"
            ): """
======
$title
======

.. parameter:: $title

The :parameter:`title` stuff works


"""
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("param.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], TargetNotFound)

        page = result.pages[FileId("param.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="param.txt">
    <section>
        <heading id="-title">
            <text>$title</text>
        </heading>
        <target domain="mongodb" name="parameter" html_id="mongodb-parameter-param.-title">
            <directive_argument>
                <literal><text>$title</text></literal>
            </directive_argument>
            <target_identifier ids="['param.$title']">
                <text>$title</text>
            </target_identifier>
        </target>
        <paragraph>
            <text>The </text>
            <ref_role domain="mongodb" name="parameter" target="param.title">
                <literal><text>title</text></literal>
            </ref_role>
            <text> stuff works</text>
        </paragraph>
    </section>
</root>
                """,
        )


# Ensure that "index.txt" can add itself to the toctree
def test_toctree_self_add() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. toctree::

    /page1
    Overview </index>
    /page2
            """,
            Path("source/page1.txt"): "",
            Path("source/page2.txt"): "",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        check_toctree_testing_string(
            result.metadata["toctree"],
            """
<toctree slug="/">
    <title><text>untitled</text></title>
    <toctree slug="page1" drawer="True" />
    <toctree slug="/" drawer="True">
        <title><text>Overview</text></title>
    </toctree>
    <toctree slug="page2" drawer="True" />
</toctree>
""",
        )


def test_case_sensitive_labels() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. _a-MixedCase-Label:

============
Main Heading
============

:ref:`a-mixedcase-label`

:ref:`a-MixedCase-Label`
"""
        }
    ) as result:
        assert [
            "a-mixedcase-label" in diagnostic.message
            for diagnostic in result.diagnostics[FileId("index.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("index.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
    <target domain="std" name="label" html_id="std-label-a-MixedCase-Label">
        <target_identifier ids="['a-MixedCase-Label']"><text>Main Heading</text></target_identifier>
    </target>
    <section>
        <heading id="main-heading"><text>Main Heading</text></heading>
        <paragraph><ref_role domain="std" name="label" target="a-mixedcase-label"><text>a-mixedcase-label</text></ref_role></paragraph>
        <paragraph>
            <ref_role domain="std" name="label" target="a-MixedCase-Label" fileid="['index', 'std-label-a-MixedCase-Label']">
                <text>Main Heading</text>
            </ref_role>
        </paragraph>
    </section>
</root>
        """,
        )


def test_same_page_target_resolution() -> None:
    with make_test(
        {
            Path(
                "source/program1.txt"
            ): """
=========
Program 1
=========

.. program:: program1

.. option:: --verbose

   Verbose

.. include:: /includes/fact.rst
""",
            Path(
                "source/program2.txt"
            ): """
=========
Program 2
=========

.. program:: program2

.. option:: --verbose

   Verbose

.. include:: /includes/fact.rst
""",
            Path(
                "source/includes/fact.rst"
            ): """
:option:`--verbose`

:option:`program1 --verbose`

:option:`program2 --verbose`
""",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        page = result.pages[FileId("program1.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="program1.txt"><section>
    <heading id="program-1"><text>Program 1</text></heading>

    <target domain="std" name="program" html_id="std-program-program1">
        <directive_argument>
            <literal><text>program1</text></literal>
        </directive_argument>
        <target_identifier ids="['program1']"><text>program1</text></target_identifier>
    </target>

    <target domain="std" name="option" html_id="std-option-program1.--verbose">
        <directive_argument><literal><text>--verbose</text></literal></directive_argument>
        <target_identifier ids="['--verbose', 'program1.--verbose']"><text>program1 --verbose</text></target_identifier>
        <paragraph><text>Verbose</text></paragraph>
    </target>

    <directive name="include">
        <text>/includes/fact.rst</text>
        <root fileid="includes/fact.rst">
            <paragraph>
                <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
                    <literal><text>--verbose</text></literal>
                </ref_role>
            </paragraph>

            <paragraph>
                <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
                    <literal><text>program1 --verbose</text></literal>
                </ref_role>
            </paragraph>

            <paragraph>
                <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
                    <literal><text>program2 --verbose</text></literal>
                </ref_role>
            </paragraph>
        </root>
    </directive>
</section></root>
        """,
        )

        page = result.pages[FileId("program2.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="program2.txt"><section>
    <heading id="program-2"><text>Program 2</text></heading>

    <target domain="std" name="program" html_id="std-program-program2">
        <directive_argument>
            <literal><text>program2</text></literal>
        </directive_argument>
        <target_identifier ids="['program2']"><text>program2</text></target_identifier>
    </target>

    <target domain="std" name="option" html_id="std-option-program2.--verbose">
        <directive_argument><literal><text>--verbose</text></literal></directive_argument>
        <target_identifier ids="['--verbose', 'program2.--verbose']"><text>program2 --verbose</text></target_identifier>
        <paragraph><text>Verbose</text></paragraph>
    </target>

    <directive name="include">
        <text>/includes/fact.rst</text>
        <root fileid="includes/fact.rst">
            <paragraph>
                <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
                    <literal><text>--verbose</text></literal>
                </ref_role>
            </paragraph>

            <paragraph>
                <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
                    <literal><text>program1 --verbose</text></literal>
                </ref_role>
            </paragraph>

            <paragraph>
                <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
                    <literal><text>program2 --verbose</text></literal>
                </ref_role>
            </paragraph>
        </root>
    </directive>
</section></root>
        """,
        )


def test_abbreviated_link() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. method:: db.collection.watch()

:method:`~db.collection.watch`
""",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"

        page = result.pages[FileId("index.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
    <target domain="mongodb" name="method" html_id="mongodb-method-db.collection.watch">
        <directive_argument><literal><text>db.collection.watch()</text></literal></directive_argument>
        <target_identifier ids="['db.collection.watch']"><text>db.collection.watch()</text></target_identifier>
    </target>

    <paragraph>
        <ref_role domain="mongodb" name="method" target="db.collection.watch" flag="~" fileid="['index', 'mongodb-method-db.collection.watch']">
            <literal><text>watch()</text></literal>
        </ref_role>
    </paragraph>
</root>
        """,
        )


def test_language_selector() -> None:
    with make_test(
        {
            Path(
                "source/tabs.txt"
            ): """
.. tabs-pillstrip:: languages

.. tabs-drivers::
   :hidden:

   .. tab::
      :tabid: shell

      Shell

   .. tab::
      :tabid: python

      Python
"""
        }
    ) as result:
        for d in result.diagnostics[FileId("tabs.txt")]:
            print(d.message)
        assert [
            "deprecated" in diagnostic.message
            for diagnostic in result.diagnostics[FileId("tabs.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("tabs.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs.txt" selectors="{'drivers': {'shell': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'MongoDB Shell'}], 'python': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Python'}]}}">
<directive name="tabs-pillstrip"><text>languages</text></directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="shell"><text>MongoDB Shell</text>
<paragraph><text>Shell</text></paragraph>
</directive>
<directive name="tab" tabid="python"><text>Python</text>
<paragraph><text>Python</text></paragraph>
</directive>
</directive>
</root>
            """,
        )

    # Ensure that diagnostic is output when some languages don't appear in every tabset
    with make_test(
        {
            Path(
                "source/tabs-two.txt"
            ): """
.. tabs-selector:: drivers

.. tabs-drivers::
   :hidden:

   .. tab::
      :tabid: c

      C

   .. tab::
      :tabid: nodejs

      Node.js

.. tabs-drivers::
   :hidden:

   .. tab::
      :tabid: c

      C

.. tabs-drivers::
   :hidden:

   .. tab::
      :tabid: python

      Python
"""
        }
    ) as result:
        assert [
            "nodejs" in d.message
            and "c" in d.message
            and "python" in d.message
            and type(d) == MissingTab
            for d in result.diagnostics[FileId("tabs-two.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("tabs-two.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs-two.txt" selectors="{'drivers': {'c': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'C'}], 'nodejs': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Node.js'}]}}">
<directive name="tabs-selector"><text>drivers</text></directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="c"><text>C</text>
<paragraph><text>C</text></paragraph>
</directive>
<directive name="tab" tabid="nodejs"><text>Node.js</text>
<paragraph><text>Node.js</text></paragraph>
</directive>
</directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="c"><text>C</text>
<paragraph><text>C</text></paragraph>
</directive>
</directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="python"><text>Python</text>
<paragraph><text>Python</text></paragraph>
</directive>
</directive>
</root>
            """,
        )

    # Ensure that diagnostic is output when tabs are missing from page with language selector
    with make_test(
        {
            Path(
                "source/tabs-three.txt"
            ): """
.. tabs-selector:: drivers
"""
        }
    ) as result:
        assert [
            type(diagnostic) == ExpectedTabs
            for diagnostic in result.diagnostics[FileId("tabs-three.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("tabs-three.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs-three.txt">
<directive name="tabs-selector"><text>drivers</text></directive>
</root>
            """,
        )

    # Ensure postprocessor doesn't fail when no argument is specified
    with make_test(
        {
            Path(
                "source/tabs-four.txt"
            ): """
.. tabs-selector::

.. tabs-drivers::
   :hidden:

   .. tab::
      :tabid: java-sync

      Java (sync)
"""
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        page = result.pages[FileId("tabs-four.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs-four.txt">
<directive name="tabs-selector" />
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="java-sync"><text>Java (Sync)</text>
<paragraph><text>Java (sync)</text></paragraph>
</directive>
</directive>
</root>
            """,
        )

    # Ensure non-drivers tabset works properly
    with make_test(
        {
            Path(
                "source/tabs-five.txt"
            ): """
.. tabs-selector:: platforms

.. tabs-platforms::
   :hidden:

   .. tab::
      :tabid: windows

      Windows

   .. tab::
      :tabid: macos

      macOS

   .. tab::
      :tabid: linux

      Linux
"""
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        page = result.pages[FileId("tabs-five.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs-five.txt" selectors="{'platforms': {'windows': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Windows'}], 'macos': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'macOS'}], 'linux': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Linux'}]}}">
<directive name="tabs-selector"><text>platforms</text></directive>
<directive name="tabs" hidden="True" tabset="platforms">
<directive name="tab" tabid="windows"><text>Windows</text>
<paragraph><text>Windows</text></paragraph>
</directive>
<directive name="tab" tabid="macos"><text>macOS</text>
<paragraph><text>macOS</text></paragraph>
</directive>
<directive name="tab" tabid="linux"><text>Linux</text>
<paragraph><text>Linux</text></paragraph>
</directive>
</directive>
</root>
            """,
        )

    # Ensure a second tabs-selector directive doesnt' overwrite the first tabset
    with make_test(
        {
            Path(
                "source/tabs-six.txt"
            ): """
.. tabs-selector:: drivers

.. tabs-drivers::

   .. tab::
      :tabid: java-sync

      Java (sync)

   .. tab::
      :tabid: python

      Python tab

.. tabs-selector:: drivers

.. tabs-drivers::

   .. tab::
      :tabid: java-sync

      Java (sync)
"""
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("tabs-six.txt")]
        assert isinstance(diagnostics[0], DuplicateDirective)
        assert isinstance(diagnostics[1], MissingTab)
        page = result.pages[FileId("tabs-six.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="tabs-six.txt" selectors="{'drivers': {'java-sync': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Java (Sync)'}], 'python': [{'type': 'text', 'position': {'start': {'line': 3}}, 'value': 'Python'}]}}">
<directive name="tabs-selector"><text>drivers</text></directive>
<directive name="tabs" tabset="drivers">
<directive name="tab" tabid="java-sync"><text>Java (Sync)</text>
<paragraph><text>Java (sync)</text></paragraph>
</directive>
<directive name="tab" tabid="python"><text>Python</text>
<paragraph><text>Python tab</text></paragraph>
</directive>
</directive>
<directive name="tabs-selector"><text>drivers</text></directive>
<directive name="tabs" tabset="drivers">
<directive name="tab" tabid="java-sync"><text>Java (Sync)</text>
<paragraph><text>Java (sync)</text></paragraph>
</directive>
</directive>
</root>
            """,
        )

    # Ensure we gracefully handle invalid children in named tabs
    with make_test(
        {
            Path(
                "source/tabs-six.txt"
            ): """
.. tabs-drivers::

   .. tab::
      :tabid: java-sync

      Java (sync)

   .. tip::

      A tip
"""
        }
    ) as result:
        assert [type(d) for d in result.diagnostics[FileId("tabs-six.txt")]] == [
            TabMustBeDirective
        ]

    # Ensure we gracefully handle invalid children in tabs::
    with make_test(
        {
            Path(
                "source/tabs-six.txt"
            ): """
.. tabs::

   .. tab::
      :tabid: java-sync

      Java (sync)

   .. tip::

      A tip
"""
        }
    ) as result:
        assert [type(d) for d in result.diagnostics[FileId("tabs-six.txt")]] == [
            TabMustBeDirective
        ]


def test_correct_diagnostic_path() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. _a-MixedCase-Label:

============
Main Heading
============

.. include:: /includes/fact.rst
""",
            Path(
                "source/includes/fact.rst"
            ): """
:ref:`missing-ref`
""",
        }
    ) as result:
        assert {
            k: [type(diag) for diag in v] for k, v in result.diagnostics.items() if v
        } == {
            FileId("includes/fact.rst"): [diagnostics.TargetNotFound]
        }, "Incorrect diagnostics raised"


def test_subcommands() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
=========
Program 1
=========

.. program:: realmcli

.. option:: --verbose

   Verbose

.. option:: --version

   Version

.. program:: realmcli import

.. option:: --verbose

   Verbose

.. program:: realmcli export

.. option:: --verbose

   Verbose

.. program:: realmcli export just-silly-now

.. option:: --verbose

   Verbose

.. program:: a-program

.. option:: --verbose

   Verbose

""",
            Path(
                "source/links.txt"
            ): """
* :option:`realmcli export --verbose`
* :option:`realmcli export just-silly-now --verbose`
* :option:`realmcli import --verbose`
* :option:`realmcli --verbose`
""",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        check_ast_testing_string(
            result.pages[FileId("links.txt")].ast,
            """
<root fileid="links.txt">
<list enumtype="unordered">
    <listItem>
        <paragraph>
            <ref_role domain="std" name="option" target="realmcli export.--verbose" fileid="['index', 'std-option-realmcli-export.--verbose']">
                <literal><text>realmcli export --verbose</text></literal>
            </ref_role>
        </paragraph>
    </listItem>
    <listItem>
        <paragraph>
            <ref_role domain="std" name="option" target="realmcli export just-silly-now.--verbose" fileid="['index', 'std-option-realmcli-export-just-silly-now.--verbose']">
                <literal><text>realmcli export just-silly-now --verbose</text></literal>
            </ref_role>
        </paragraph>
    </listItem>
    <listItem>
        <paragraph>
            <ref_role domain="std" name="option" target="realmcli import.--verbose" fileid="['index', 'std-option-realmcli-import.--verbose']">
                <literal><text>realmcli import --verbose</text></literal>
            </ref_role>
        </paragraph>
    </listItem>
    <listItem>
        <paragraph>
            <ref_role domain="std" name="option" target="realmcli.--verbose" fileid="['index', 'std-option-realmcli.--verbose']">
                <literal><text>realmcli --verbose</text></literal>
            </ref_role>
        </paragraph>
    </listItem>
</list>
</root>
    """,
        )

    # Ensure that the correct HTML IDs exist
    index_page = result.pages[FileId("index.txt")]
    index_page_ast = ast_to_testing_string(index_page.ast)
    for html_id in (
        "std-option-realmcli.--verbose",
        "std-option-realmcli-export.--verbose",
        "std-option-realmcli-export-just-silly-now.--verbose",
        "std-option-realmcli-import.--verbose",
    ):
        assert f'"{html_id}"' in index_page_ast, f"missing {html_id}"


def test_heading_id_unique() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
==========
Index Page
==========

A Heading
---------

.. include:: /includes/fact.rst

.. include:: /includes/fact.rst
""",
            Path(
                "source/includes/fact.rst"
            ): """
A Heading
~~~~~~~~~
        """,
        }
    ) as result:
        for d in result.diagnostics[FileId("index.txt")]:
            print(d.message)
        assert not result.diagnostics[FileId("index.txt")]
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
<section>
    <heading id="index-page"><text>Index Page</text></heading>
    <section>
        <heading id="a-heading"><text>A Heading</text></heading>
        <directive name="include"><text>/includes/fact.rst</text>
            <root fileid="includes/fact.rst">
                <section>
                    <heading id="a-heading-1"><text>A Heading</text></heading>
                </section>
            </root>
        </directive>
        <directive name="include"><text>/includes/fact.rst</text>
            <root fileid="includes/fact.rst">
                <section>
                    <heading id="a-heading-2"><text>A Heading</text></heading>
                </section>
            </root>
        </directive>
    </section>
</section></root>""",
        )


def test_include_subset() -> None:
    with make_test(
        {
            # Splice on comments
            Path(
                "source/program1.txt"
            ): """
.. include:: /includes/included.rst
   :start-after: start-comment
   :end-before: end-comment
""",
            # Splice on labels
            Path(
                "source/program2.txt"
            ): """
.. include:: /includes/included.rst
   :start-after: start-label
   :end-before: end-label
""",
            Path(
                "source/includes/included.rst"
            ): """
.. start-comment

Section Heading
---------------

Paragraph.

.. end-comment

.. _start-label:

Section Heading
---------------

Paragraph

.. _end-label:
""",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        page = result.pages[FileId("program1.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="program1.txt">
    <directive name="include" start-after="start-comment" end-before="end-comment">
        <text>/includes/included.rst</text>
        <root fileid="includes/included.rst">
            <comment><text>start-comment</text></comment>
            <section>
                <heading id="section-heading">
                    <text>Section Heading</text>
                </heading>
                <paragraph>
                    <text>Paragraph.</text>
                </paragraph>
                <comment>
                    <text>end-comment</text>
                </comment>
            </section>
        </root>
    </directive>
</root>
        """,
        )

        page = result.pages[FileId("program2.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="program2.txt">
    <directive name="include" start-after="start-label" end-before="end-label">
        <text>/includes/included.rst</text>
        <root fileid="includes/included.rst">
            <section>
                <target domain="std" name="label" html_id="std-label-start-label">
                    <target_identifier ids="['start-label']">
                        <text>Section Heading</text>
                    </target_identifier>
                </target>
            </section>
            <section>
                <heading id="section-heading">
                    <text>Section Heading</text>
                </heading>
                <paragraph>
                    <text>Paragraph</text>
                </paragraph>
                <target domain="std" name="label" html_id="std-label-end-label">
                    <target_identifier ids="['end-label']"/>
                </target>
            </section>
        </root>
    </directive>
</root>
        """,
        )


def test_include_subset_fails() -> None:
    with make_test(
        {
            # Splice on text in reverse order
            Path(
                "source/program1.txt"
            ): """
.. include:: /includes/included.rst
   :start-after: end-text
   :end-before: start-text
""",
            # Can't find start text
            Path(
                "source/program2.txt"
            ): """
.. include:: /includes/included.rst
   :start-after: fake-start-text
   :end-before: end-text
""",
            # Can't find end text
            Path(
                "source/program3.txt"
            ): """
.. include:: /includes/included.rst
   :start-after: start-text
   :end-before: fake-end-text
""",
            Path(
                "source/includes/included.rst"
            ): """
.. start-comment

Section Heading
---------------

Paragraph.

.. end-comment

start-text

end-text

.. _start-label:

Section Heading
---------------

Paragraph

.. _end-label:
""",
        }
    ) as result:
        assert (
            len(
                [
                    diagnostics
                    for diagnostics in result.diagnostics.values()
                    if diagnostics
                ]
            )
            == 3
        ), "Should raise 3 diagnostics"


def test_replacements() -> None:
    with make_test(
        {
            # Correctly handles inline replacement
            Path(
                "source/inline.txt"
            ): """
.. include:: /includes/replacement-inline.rst

   .. replacement:: i-hope

      Yes

   .. replacement:: maybe

      Yes
""",
            Path(
                "source/includes/replacement-inline.rst"
            ): """
Do we correctly handle replacing inline values? |i-hope| we do.
""",
            # Correctly handles own-paragraph replacement
            Path(
                "source/block.txt"
            ): """
.. include:: /includes/replacement-block.rst

   .. replacement:: code

      .. code-block:: python

         mongo --port 27017
""",
            Path(
                "source/includes/replacement-block.rst"
            ): """
The following should be a code block:

|code|
""",
        },
    ) as result:

        active_file = "inline.txt"
        assert not result.diagnostics[FileId(active_file)]
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="inline.txt">
    <directive name="include">
        <text>/includes/replacement-inline.rst</text>
        <directive name="replacement"><text>i-hope</text><paragraph><text>Yes</text></paragraph></directive>
        <directive name="replacement"><text>maybe</text><paragraph><text>Yes</text></paragraph></directive>
        <root fileid="includes/replacement-inline.rst">
            <paragraph>
                <text>Do we correctly handle replacing inline values? </text>
                <substitution_reference name="i-hope"><text>Yes</text></substitution_reference>
                <text> we do.</text>
            </paragraph>
        </root>
    </directive>
</root>
""",
        )

        active_file = "block.txt"
        assert not result.diagnostics[FileId(active_file)]
        page = result.pages[FileId(active_file)]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="block.txt">
    <directive name="include">
        <text>/includes/replacement-block.rst</text>
        <directive name="replacement"><text>code</text><code lang="python" copyable="True">
            mongo --port 27017
        </code></directive>
        <root fileid="includes/replacement-block.rst">
            <paragraph>
                <text>The following should be a code block:</text>
            </paragraph>
            <substitution_reference name="code">
                <code lang="python" copyable="True">
                    mongo --port 27017
                </code>
            </substitution_reference>
        </root>
    </directive>
</root>
""",
        )


def test_replacements_scope() -> None:
    with make_test(
        {
            Path(
                "source/includes/a.txt"
            ): """
.. include:: /includes/b.rst

   .. replacement:: foo

      foo

   .. replacement:: bar

      bar
""",
            Path(
                "source/includes/b.rst"
            ): """
.. include:: /includes/c.rst

   .. replacement:: foo

      foo
""",
            Path(
                "source/includes/c.rst"
            ): """
|foo|

|bar|
""",
        },
    ) as result:
        print(result.diagnostics)
        assert not result.diagnostics[FileId("includes/b.rst")]
        assert not result.diagnostics[FileId("includes/a.txt")]
        assert [type(x) for x in result.diagnostics[FileId("includes/c.rst")]] == [
            SubstitutionRefError
        ]


def test_replacement_context() -> None:
    with make_test(
        {
            Path(
                "source/includes/a.txt"
            ): """
.. include:: /includes/b.rst

   .. replacement:: two-paragraphs

      foo

      bar

   .. replacement:: a-codeblock

      .. code-block:: sh

         ls
""",
            Path(
                "source/includes/b.rst"
            ): """
Block in Inline Contexts
------------------------

test |two-paragraphs|

test |a-codeblock|

Block in Block Contexts
-----------------------

|two-paragraphs|

|a-codeblock|
""",
        },
    ) as result:
        assert [type(x) for x in result.diagnostics[FileId("includes/b.rst")]] == [
            InvalidContextError,
            InvalidContextError,
            SubstitutionRefError,
            SubstitutionRefError,
        ]


def test_named_references() -> None:
    with make_test(
        {
            # Valid extlink reference
            Path(
                "source/valid.txt"
            ): """
.. _`MongoDB, Inc.`: https://www.mongodb.com?tck=snooty

Link to `MongoDB, Inc.`_
""",
            # Valid extlink reference
            Path(
                "source/alternate.txt"
            ): """
Defining `docs link <https://docs.mongodb.com>`_

Referencing `docs link`_
""",
            # Reference to nonexistent extlink
            Path(
                "source/nonexistent.txt"
            ): """
Link to `nonexistent`_
""",
            # Attempt to redefine extlink
            Path(
                "source/duplicate.txt"
            ): """
This is `GitHub <https://github.com>`_

This is not `GitHub <https://twitter.com>`_

Reference `GitHub`_
""",
        },
    ) as result:

        active_file = "valid.txt"
        assert not result.diagnostics[FileId(active_file)]
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="valid.txt">
    <named_reference refname="MongoDB, Inc." refuri="https://www.mongodb.com?tck=snooty" />
    <paragraph>
        <text>Link to </text>
        <reference refname="MongoDB, Inc." refuri="https://www.mongodb.com?tck=snooty"><text>MongoDB, Inc.</text></reference>
    </paragraph>
</root>
""",
        )

        active_file = "alternate.txt"
        assert not result.diagnostics[FileId(active_file)]
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="alternate.txt">
    <paragraph>
        <text>Defining </text>
        <reference refuri="https://docs.mongodb.com"><text>docs link</text></reference>
        <named_reference refname="docs link" refuri="https://docs.mongodb.com" />
    </paragraph>
    <paragraph>
        <text>Referencing </text>
        <reference refname="docs link" refuri="https://docs.mongodb.com"><text>docs link</text></reference>
    </paragraph>
</root>
""",
        )

        active_file = "nonexistent.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], TargetNotFound)
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="nonexistent.txt">
    <paragraph>
        <text>Link to </text>
        <reference refname="nonexistent"><text>nonexistent</text></reference>
    </paragraph>
</root>
""",
        )

        active_file = "duplicate.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="duplicate.txt">
    <paragraph>
        <text>This is </text>
        <reference refuri="https://github.com"><text>GitHub</text></reference>
        <named_reference refname="GitHub" refuri="https://github.com" />
    </paragraph>
    <paragraph>
        <text>This is not </text>
        <reference refuri="https://twitter.com"><text>GitHub</text></reference>
        <named_reference refname="GitHub" refuri="https://twitter.com" />
    </paragraph>
    <paragraph>
        <text>Reference </text>
        <reference refname="GitHub" refuri="https://twitter.com"><text>GitHub</text></reference>
    </paragraph>
</root>
""",
        )


def test_contents_directive() -> None:
    with make_test(
        {
            Path(
                "source/page.txt"
            ): """
=====
Title
=====

.. contents::
   :depth: 2

First Heading
-------------

Second Heading
~~~~~~~~~~~~~~

Omitted Heading
^^^^^^^^^^^^^^^^

Third Heading
-------------

.. contents::
   :depth: 3
""",
            Path(
                "source/no-contents.txt"
            ): """
=======
Title 2
=======

A Heading
---------
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("page.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], DuplicateDirective)
        page = result.pages[FileId("page.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="page.txt" headings="[{'depth': 2, 'id': 'first-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 9}}, 'value': 'First Heading'}]}, {'depth': 3, 'id': 'second-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 12}}, 'value': 'Second Heading'}]}, {'depth': 2, 'id': 'third-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 18}}, 'value': 'Third Heading'}]}]">
<section>
<heading id="title"><text>Title</text></heading>
<directive name="contents" depth="2" />
<section>
<heading id="first-heading"><text>First Heading</text></heading>
<section>
<heading id="second-heading"><text>Second Heading</text></heading>
<section>
<heading id="omitted-heading"><text>Omitted Heading</text></heading>
</section>
</section>
</section>
<section>
<heading id="third-heading"><text>Third Heading</text></heading>
<directive name="contents" depth="3" />
</section>
</section>
</root>
            """,
        )

        # No headings object attached to root without contents directive
        page = result.pages[FileId("no-contents.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="no-contents.txt">
<section>
<heading id="title-2"><text>Title 2</text></heading>
<section>
<heading id="a-heading"><text>A Heading</text></heading>
</section>
</section>
</root>
            """,
        )


def test_banner_postprocess_multiple_pages_one_banner() -> None:
    # Banners should apply to any pages whose source paths match our glob pattern in targets
    # and should be prepended to the first section of a page which contains a header
    # if no suitable section can be found, the banner should prepend to the top of the page
    with make_test(
        {
            Path(
                "source/test/page1.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "source/test/page2.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "source/how-to/page1.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "snooty.toml"
            ): """
name = "test_name"
intersphinx = ["https://docs.mongodb.com/manual/objects.inv"]
title = "MongoDB title"

[[banners]]
targets = ["test/*.txt"]
variant = "info"
value = "This product is deprecated"
            """,
        }
    ) as result:
        page1 = result.pages[FileId("test/page1.txt")]
        diagnostics = result.diagnostics[FileId("test/page1.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page1.ast,
            """
<root fileid="test/page1.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<directive domain="mongodb" name="banner" variant="info">
<text>This product is deprecated</text>
</directive>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )
        page2 = result.pages[FileId("test/page2.txt")]
        diagnostics = result.diagnostics[FileId("test/page2.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page2.ast,
            """
<root fileid="test/page2.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<directive domain="mongodb" name="banner" variant="info">
<text>This product is deprecated</text>
</directive>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )
        page3 = result.pages[FileId("how-to/page1.txt")]
        diagnostics = result.diagnostics[FileId("how-to/page1.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page3.ast,
            """
<root fileid="how-to/page1.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )


def test_banner_postprocess_multiple_banners() -> None:
    with make_test(
        {
            Path(
                "source/test/page1.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "source/guide/page2.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "source/how-to/page1.txt"
            ): """
==========
Index Page
==========

A Heading
---------

Paragraph

            """,
            Path(
                "snooty.toml"
            ): """
name = "test_name"
intersphinx = ["https://docs.mongodb.com/manual/objects.inv"]
title = "MongoDB title"

[[banners]]
targets = ["test/*.txt"]
variant = "info"
value = "This product is deprecated"

[[banners]]
targets = ["guide/*.txt"]
variant = "warning"
value = "This product is out of date"
            """,
        }
    ) as result:
        page1 = result.pages[FileId("test/page1.txt")]
        diagnostics = result.diagnostics[FileId("test/page1.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page1.ast,
            """
<root fileid="test/page1.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<directive domain="mongodb" name="banner" variant="info">
<text>This product is deprecated</text>
</directive>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )
        page2 = result.pages[FileId("guide/page2.txt")]
        diagnostics = result.diagnostics[FileId("test/page2.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page2.ast,
            """
<root fileid="guide/page2.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<directive domain="mongodb" name="banner" variant="warning">
<text>This product is out of date</text>
</directive>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )
        page3 = result.pages[FileId("how-to/page1.txt")]
        diagnostics = result.diagnostics[FileId("how-to/page1.txt")]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page3.ast,
            """
<root fileid="how-to/page1.txt">
<section>
<heading id="index-page">
<text>Index Page</text>
</heading>
<section>
<heading id="a-heading">
<text>A Heading</text>
</heading>
<paragraph>
<text>Paragraph</text>
</paragraph>
</section>
</section>
</root>
            """,
        )


def test_monospace_limit_fix() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
=====
Title
=====
.. limit:: a test of a limit
:limit:`a test of a limit`
"""
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        page = result.pages[FileId("index.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
<section><heading id="title">
<text>Title</text></heading>
<target domain="mongodb" name="limit" html_id="mongodb-limit-a-test-of-a-limit">
<directive_argument><text>a test of a limit</text>
</directive_argument><target_identifier ids="['a test of a limit']">
<text>a test of a limit</text></target_identifier></target><paragraph>
<ref_role domain="mongodb" name="limit" target="a test of a limit" fileid="['index', 'mongodb-limit-a-test-of-a-limit']">
<text>a test of a limit</text>
</ref_role></paragraph></section></root>""",
        )


def test_block_substitutions_in_lists() -> None:
    # There were some subtle issues with inserting a BlockSubstitutionReference instead of a paragraph
    # node that led to a ListItemNode living *outside* of the ListNode. Test that case.
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. |checkmark| unicode:: U+2713

.. list-table::
   :header-rows: 1

   * - Col 1
     - Col 2

   * - :readconcern:`"majority"`
     - |checkmark|

   * - :readconcern:`"majority"`
     - |checkmark|
"""
        }
    ) as result:
        print(ast_to_testing_string(result.pages[FileId("index.txt")].ast))
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
<root fileid="index.txt">
    <substitution_definition name="checkmark">
        <text>✓</text>
    </substitution_definition>
    <directive name="list-table" header-rows="1">
        <list enumtype="unordered">
            <listItem>
                <list enumtype="unordered">
                    <listItem>
                        <paragraph>
                            <text>Col 1</text>
                        </paragraph>
                    </listItem>
                    <listItem>
                        <paragraph>
                            <text>Col 2</text>
                        </paragraph>
                    </listItem>
                </list>
            </listItem>
            <listItem>
                <list enumtype="unordered">
                    <listItem>
                        <paragraph>
                            <ref_role domain="mongodb" name="readconcern" target="readconcern.&quot;majority&quot;">
                                <literal>
                                    <text>"majority"</text>
                                </literal>
                            </ref_role>
                        </paragraph>
                    </listItem>
                    <listItem>
                        <substitution_reference name="checkmark">
                            <paragraph>
                                <text>✓</text>
                            </paragraph>
                        </substitution_reference>
                    </listItem>
                </list>
            </listItem>
            <listItem>
                <list enumtype="unordered">
                    <listItem>
                        <paragraph>
                            <ref_role domain="mongodb" name="readconcern" target="readconcern.&quot;majority&quot;">
                                <literal>
                                    <text>"majority"</text>
                                </literal>
                            </ref_role>
                        </paragraph>
                    </listItem>
                    <listItem>
                        <substitution_reference name="checkmark">
                            <paragraph>
                                <text>✓</text>
                            </paragraph>
                        </substitution_reference>
                    </listItem>
                </list>
            </listItem>
        </list>
    </directive>
</root>""",
        )

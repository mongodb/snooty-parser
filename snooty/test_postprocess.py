"""An alternative and more granular approach to writing postprocessing tests.
Eventually most postprocessor tests should probably be moved into this format."""

from pathlib import Path, PurePath
from typing import Any, Dict, cast

from snooty.types import Facet

from . import diagnostics
from .diagnostics import (
    ChapterAlreadyExists,
    ChildlessRef,
    DocUtilsParseError,
    DuplicatedExternalToc,
    DuplicateDirective,
    ExpectedPathArg,
    ExpectedTabs,
    GuideAlreadyHasChapter,
    InvalidChapter,
    InvalidChild,
    InvalidContextError,
    InvalidIAEntry,
    InvalidIALinkedData,
    InvalidNestedTabStructure,
    InvalidVersion,
    MissingChild,
    MissingTab,
    MissingTocTreeEntry,
    NestedDirective,
    OrphanedPage,
    SubstitutionRefError,
    TabMustBeDirective,
    TargetNotFound,
    UnexpectedDirectiveOrder,
    UnknownDefaultTabId,
)
from .n import FileId
from .util_test import (
    ast_to_testing_string,
    check_ast_testing_string,
    check_toctree_testing_string,
    make_test,
)


def test_tabs_contain_tabs_contain_procedures() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. tabs-platforms::

   .. tab::
      :tabid: windows

      .. tabs::

         .. tab::
            :tabid: homebrew

            .. procedure::


"""
        }
    ) as result:
        active_file = "index.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], InvalidNestedTabStructure)

    with make_test(
        {
            Path(
                "source/page1.txt"
            ): """
.. tabs-platforms::

   .. tab::
      :tabid: windows

      .. include:: /includes/test.rst

      .. tabs::

         .. tab::
            :tabid: homebrew

            .. include:: /includes/test.rst

            .. procedure::


""",
            Path(
                "source/page2.txt"
            ): """
.. tabs-platforms::

   .. tab::
      :tabid: windows

      Select the appropriate tab based on your Linux distribution and
      desired package from the tabs below:

      .. tabs::

         .. tab::
            :tabid: homebrew

            .. include:: /includes/test.rst

             To manually install :binary:`mongosh` using a downloaded ``.zip``

            .. procedure::


""",
            Path(
                "source/page3.txt"
            ): """
.. tabs-platforms::

   .. tab::
      :tabid: windows

      .. tabs::

         .. tab::
            :tabid: homebrew

            .. procedure::

               .. step::

                  foo

            .. note::

               Wow

         .. tab::
            :tabid: oh yeah

            .. procedure::

            .. tabs::

               .. tab::
                  :tabid: homebrew

                  .. procedure::


""",
            Path(
                "source/includes/test.rst"
            ): """
:option:`--verbose`

:option:`program1 --verbose`

:option:`program2 --verbose`
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("page1.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], InvalidNestedTabStructure)

        diagnostics = result.diagnostics[FileId("page2.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], InvalidNestedTabStructure)

        diagnostics = result.diagnostics[FileId("page3.txt")]
        assert len(diagnostics) == 3
        assert isinstance(diagnostics[0], InvalidNestedTabStructure)
        assert isinstance(diagnostics[1], InvalidNestedTabStructure)
        assert isinstance(diagnostics[2], InvalidNestedTabStructure)


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
        assert {type(d) for d in diagnostics} == {
            InvalidIAEntry,
            MissingTocTreeEntry,
            InvalidIAEntry,
            OrphanedPage,
        }
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


def test_ia_linked_data() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. ia::

   .. entry:: Atlas
      :url: https://www.mongodb.com/docs/atlas/getting-started/

   .. entry:: MongoDB Database Manual
      :url: https://www.mongodb.com/docs/manual/

   .. entry:: Client Libraries
      :id: client-libraries
      :url: https://www.mongodb.com/docs/drivers/

.. card-group::
   :columns: 4
   :layout: default
   :ia-entry-id: client-libraries
   :type: drivers
   :style: extra-compact

   .. card::
      :headline: C
      :url: https://www.mongodb.com/docs/drivers/c/

   .. there is no headline
   .. card::
      :url: https://google.com/

   .. card::
      :headline: C++
      :url: https://www.mongodb.com/docs/drivers/cxx/

   .. card::
      :headline: No url

.. card-group::
   :columns: 4
   :layout: default
   :style: extra-compact

   .. card::
      :headline: Wahoo
      :url: https://www.mongodb.com/docs/drivers/java/
""",
            Path(
                "source/page1.txt"
            ): """
:orphan:

.. card-group::
   :columns: 4
   :layout: default
   :ia-entry-id: not-a-valid-id
   :type: drivers
   :style: extra-compact

   .. card::
      :headline: C
      :url: https://www.mongodb.com/docs/drivers/c/
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 2
        assert isinstance(diagnostics[0], InvalidIALinkedData)
        assert isinstance(diagnostics[1], InvalidIALinkedData)

        diagnostics = result.diagnostics[FileId("page1.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], InvalidIALinkedData)

        # Ensure the one IA entry that has linked data contains said linked data.
        metadata = cast(Dict[str, Any], result.metadata)
        ia_tree = metadata["iatree"]
        root_children = ia_tree["children"]
        for entry in root_children:
            linked_data = entry.get("linked_data")
            if entry["title"][0]["value"] == "Client Libraries":
                assert entry["id"] == "client-libraries"
                assert len(linked_data) == 2
            else:
                assert not linked_data


def test_guides() -> None:
    # Chapters are generated properly and page ast should look as expected
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Guides
======

.. chapters::

    .. chapter:: Atlas
        :description: This is the description for the Atlas chapter.
        :icon: /path/to/icon.png

        .. guide:: /path/to/guide1.txt
        .. guide:: /path/to/guide2.txt

    .. include:: /chapters/crud.rst
            """,
            Path(
                "source/chapters/crud.rst"
            ): """
.. chapter:: CRUD
    :description: This is the description for the CRUD chapter.

    .. guide:: /path/to/guide3.txt
            """,
            Path("source/path/to/icon.png"): "",
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ]
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
    <section>
        <heading id="guides">
            <text>Guides</text>
        </heading>
        <directive domain="mongodb" name="chapters">
            <directive domain="mongodb" name="chapter" description="This is the description for the Atlas chapter." icon="/path/to/icon.png" checksum="0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8">
                <text>Atlas</text>
                <directive domain="mongodb" name="guide">
                    <text>/path/to/guide1.txt</text>
                </directive>
                <directive domain="mongodb" name="guide">
                    <text>/path/to/guide2.txt</text>
                </directive>
            </directive>
            <directive name="include">
                <text>/chapters/crud.rst</text>
                <root fileid="chapters/crud.rst">
                    <directive domain="mongodb" name="chapter" description="This is the description for the CRUD chapter.">
                        <text>CRUD</text>
                        <directive domain="mongodb" name="guide">
                            <text>/path/to/guide3.txt</text>
                        </directive>
                    </directive>
                </root>
            </directive>
        </directive>
    </section>
</root>
            """,
        )
        chapters = cast(Dict[str, Any], result.metadata["chapters"])
        assert len(chapters) == 2
        assert (
            chapters["Atlas"]["description"]
            == "This is the description for the Atlas chapter."
        )
        assert chapters["Atlas"]["guides"] == ["path/to/guide1", "path/to/guide2"]
        assert chapters["Atlas"]["chapter_number"] == 1
        assert chapters["Atlas"]["icon"] == "/path/to/icon.png"
        assert (
            chapters["CRUD"]["description"]
            == "This is the description for the CRUD chapter."
        )
        assert chapters["CRUD"]["guides"] == ["path/to/guide3"]
        assert chapters["CRUD"]["chapter_number"] == 2
        assert chapters["CRUD"]["icon"] == None

    # Guides metadata is added to the project's metadata document
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Guides
======

.. chapters::

    .. chapter:: Atlas
        :description: This is the description for the Atlas chapter.

        .. guide:: /path/to/guide1.txt
            """,
            Path(
                "source/path/to/guide1.txt"
            ): """
:orphan:

=======
Guide 1
=======

.. time:: 20
.. short-description::

   This is guide 1.
            """,
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ]
        guides = cast(Dict[str, Any], result.metadata["guides"])
        assert len(guides) == 1

        test_guide_data = guides["path/to/guide1"]
        assert test_guide_data["completion_time"] == 20
        assert test_guide_data["title"][0]["value"] == "Guide 1"
        test_guide_description = test_guide_data["description"][0]["children"][0]
        assert test_guide_description["value"] == "This is guide 1."
        assert test_guide_data["chapter_name"] == "Atlas"

    # Diagnostic errors reported
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Guides
======

.. chapters::

   .. chapter:: Missing Description

      .. guide:: /path/to/guide1.txt

   .. chapter:: Good Chapter Here
      :description: The description exists! No errors

      .. guide:: /path/to/guide2.txt

   .. chapter:: No Guides
      :description: No guides

   .. guide:: /path/to/guide3.txt

   .. chapter::
      :description: No title

      .. guide:: /path/to/guide4.txt

   .. chapter:: Invalid nested chapter
      :description: Also no guides found

      .. chapter:: Should throw error
         :description: Whoops

         .. guide:: /path/to/guide5.txt
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert [type(x) for x in diagnostics] == [
            DocUtilsParseError,
            MissingChild,
            InvalidChild,
            InvalidChapter,
            InvalidChild,
            MissingChild,
        ]

    # Test missing directives in "chapters" directive
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Guides
======

.. chapters::
"""
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], MissingChild)

    # Test duplicate chapters
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. chapters::

   .. chapter:: Test
      :description: This is a chapter

      .. guide:: /path/to/guide1.txt

   .. chapter:: Test
      :description: This is a chapter

      .. guide:: /path/to/guide2.txt
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], ChapterAlreadyExists)

    # Test adding 1 guide to multiple children
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. chapters::

   .. chapter:: Test
      :description: This is a chapter

      .. guide:: /path/to/guide1.txt

   .. chapter:: Test: The Sequel
      :description: This is another chapter

      .. guide:: /path/to/guide1.txt
      .. guide:: /path/to/guide2.txt
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], GuideAlreadyHasChapter)


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


# Test for toctree icon
def test_tocicon() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
:tocicon: sync

=============================
Collections :icon:`sync-pill`
=============================
            """
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt" tocicon="sync">
    <section>
        <heading id="collections">
            <text>Collections </text>
            <role name="icon" target="sync-pill"></role>
        </heading>
    </section>
</root>
""",
        )


def test_toctree_tocicon() -> None:
    with make_test(
        {
            Path(
                "source/install.txt"
            ): """
:tocicon: sync

=============================
Collections :icon:`sync-pill`
=============================
            """,
            Path(
                "source/index.txt"
            ): """
.. toctree::
   :titlesonly:

   Overview </index>
   /install
            """,
        }
    ) as result:
        check_toctree_testing_string(
            result.metadata["toctree"],
            """
<toctree slug="/">
    <title><text>untitled</text></title>
    <toctree slug="/" drawer="True">
        <title><text>Overview</text></title>
    </toctree>
    <toctree slug="install" drawer="True" tocicon="sync">
        <title><text>Collections </text><role name="icon" target="sync-pill"></role></title>
    </toctree>
</toctree>
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
    <toctree slug="/" drawer="True" >
        <title><text>Overview</text></title>
    </toctree>
    <toctree slug="page2" drawer="True" />
</toctree>
""",
        )


def test_toctree_duplicate_node() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test_name"
title = "MongoDB title"

[[associated_products]]
name = "test_associated_product"
versions = ["v1", "v2"]
            """,
            Path(
                "source/index.txt"
            ): """
.. toctree::

    /page1
    Duplicate Toc <|test_associated_product|>
            """,
            Path(
                "source/page1.txt"
            ): """
==================
Page 1
==================

.. toctree::

   Duplicate Toc <|test_associated_product|>
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], DuplicatedExternalToc)


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


def test_childless_ref_include() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. _invisible-ref:

.. include:: /includes/fact.rst
""",
            Path(
                "source/includes/fact.rst"
            ): """
We have a link below here, but you can't see it!

See that info at :ref:`invisible-ref`
""",
        }
    ) as result:
        assert {
            k: [type(diag) for diag in v] for k, v in result.diagnostics.items() if v
        } == {
            FileId("includes/fact.rst"): [ChildlessRef]
        }, "Childless Ref diagnostics error raised"


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
:orphan:

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
<root fileid="links.txt" orphan="">
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


def test_missing_include_argument() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. include::
""",
        }
    ) as result:
        assert [type(d) for d in result.diagnostics[FileId("index.txt")]] == [
            ExpectedPathArg
        ]


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

    # Test replacements that have multiple inline elements: DOP-2620
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. binary:: mongod

.. |both| replace:: Available for :binary:`~bin.mongod` only.

|both|

"""
        }
    ) as result:
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
<root fileid="index.txt">
    <target domain="mongodb" name="binary" html_id="mongodb-binary-bin.mongod">
        <directive_argument>
            <literal>
                <text>mongod</text>
            </literal>
        </directive_argument>
        <target_identifier ids="['bin.mongod']">
            <text>mongod</text>
        </target_identifier>
    </target>
    <substitution_definition name="both">
        <text>Available for </text>
        <ref_role domain="mongodb" name="binary" target="bin.mongod" flag="~" fileid="['index', 'mongodb-binary-bin.mongod']">
            <literal>
                <text>mongod</text>
            </literal>
        </ref_role>
        <text> only.</text>
    </substitution_definition>
    <substitution_reference name="both">
        <paragraph>
            <text>Available for </text>
            <ref_role domain="mongodb" name="binary" target="bin.mongod" flag="~" fileid="['index', 'mongodb-binary-bin.mongod']">
                <literal>
                    <text>mongod</text>
                </literal>
            </ref_role>
            <text> only.</text>
        </paragraph>
    </substitution_reference>
</root>""",
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
            # Should not be able to link to a named reference from another .txt
            Path(
                "source/foo.txt"
            ): """
.. include:: /fact-reference.rst

`docs link`_
""",
            Path("source/fact-reference.rst"): "`docs link`_",
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

        # Should not be able to link to a named reference from another .txt
        active_file = "foo.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1
        active_file = "fact-reference.rst"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1


def test_instruqt_directive() -> None:
    with make_test(
        {
            Path(
                "source/page.txt"
            ): """

=====
Title
=====

.. instruqt::
    :title: TestLab
    :drawer: True



""",
        }
    ) as result:
        active_file = "page.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 0
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="page.txt" instruqt="True">
<section>
<heading id="title">
<text> Title
</text>
</heading>
<directive domain="mongodb" name= "instruqt" title="TestLab" drawer="True">
</directive>
</section>
</root>
""",
        )
    with make_test(
        {
            Path(
                "source/page1.txt"
            ): """

=====
Title
=====

.. instruqt::
    :title: TestLab
    :drawer: True

.. instruqt::
    :title: Test Another Lab
    :drawer: True

""",
        }
    ) as result:
        active_file = "page1.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], DuplicateDirective)
        page = result.pages[FileId(active_file)]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="page1.txt" instruqt="True">
<section>
<heading id="title">
<text> Title
</text>
</heading>
<directive domain="mongodb" name= "instruqt" title="TestLab" drawer="True">
</directive>
<directive domain="mongodb" name= "instruqt" title="Test Another Lab" drawer="True">
</directive>
</section>
</root>
""",
        )
    with make_test(
        {
            Path(
                "source/page2.txt"
            ): """

=====
Title
=====

.. instruqt::
    :Title: Test Lab

""",
        }
    ) as result:
        active_file = "page2.txt"
        diagnostics = result.diagnostics[FileId(active_file)]
        assert len(diagnostics) == 0
        page = result.pages[FileId(active_file)]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root fileid="page2.txt" >
<section>
<heading id="title">
<text> Title
</text>
</heading>
<directive domain="mongodb" name="instruqt" title= "Test Lab">
</directive>
</section>
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
<root fileid="page.txt" headings="[{'depth': 2, 'id': 'first-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 9}}, 'value': 'First Heading'}], 'selector_ids': {}}, {'depth': 3, 'id': 'second-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 12}}, 'value': 'Second Heading'}], 'selector_ids': {}}, {'depth': 2, 'id': 'third-heading', 'title': [{'type': 'text', 'position': {'start': {'line': 18}}, 'value': 'Third Heading'}], 'selector_ids': {}}]">
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


def test_targets_with_backslashes() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): r"""
:phpmethod:`MongoDB\Database::listCollections()`
:phpmethod:`foobar <MongoDB\Database::listCollections()>`

.. phpmethod:: MongoDB\Database::listCollections()
"""
        }
    ) as result:
        assert not result.diagnostics[FileId("index.txt")]
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            r"""
<root fileid="index.txt">
    <paragraph>
        <ref_role domain="mongodb" name="phpmethod" target="phpmethod.MongoDB\Database::listCollections()" fileid="['index', 'mongodb-phpmethod-phpmethod.MongoDB-Database--listCollections--']">
            <literal><text>MongoDB\Database::listCollections()</text></literal>
        </ref_role>
        <text> </text>
        <ref_role domain="mongodb" name="phpmethod" target="phpmethod.MongoDB\Database::listCollections()" fileid="['index', 'mongodb-phpmethod-phpmethod.MongoDB-Database--listCollections--']">
            <literal><text>foobar</text></literal>
        </ref_role>
    </paragraph>
    <target domain="mongodb" name="phpmethod" html_id="mongodb-phpmethod-phpmethod.MongoDB-Database--listCollections--">
        <directive_argument><literal><text>MongoDB\Database::listCollections()</text></literal></directive_argument>
        <target_identifier ids="['phpmethod.MongoDB\\Database::listCollections()']">
            <text>MongoDB\Database::listCollections()</text>
        </target_identifier>
    </target>
</root>
""",
        )


def test_target_quotes() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): r"""
:writeconcern:`majority <\"majority\">`
:writeconcern:`majority <"majority">`

.. writeconcern:: "majority"
"""
        }
    ) as result:
        assert not result.diagnostics[FileId("index.txt")]
        print(ast_to_testing_string(result.pages[FileId("index.txt")].ast))

        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
    <root fileid="index.txt">
    <paragraph>
        <ref_role domain="mongodb" name="writeconcern" target="writeconcern.&quot;majority&quot;" fileid="['index', 'mongodb-writeconcern-writeconcern.-majority-']">
            <literal><text>majority</text></literal>
        </ref_role><text></text>
        <ref_role domain="mongodb" name="writeconcern" target="writeconcern.&quot;majority&quot;" fileid="['index', 'mongodb-writeconcern-writeconcern.-majority-']">
            <literal><text>majority</text></literal>
        </ref_role>
    </paragraph>

    <target domain="mongodb" name="writeconcern" html_id="mongodb-writeconcern-writeconcern.-majority-">
        <directive_argument><literal><text>"majority"</text></literal></directive_argument>
        <target_identifier ids="['writeconcern.&quot;majority&quot;']">
            <text>"majority"</text>
        </target_identifier>
    </target>
</root>""",
        )


def test_canonical() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Test
======

This is a test intro
            """,
            Path(
                "snooty.toml"
            ): """
name = "test_name"
title = "MongoDB title"
canonical = "https://mongodb.com/docs/mongocli/install"
            """,
        }
    ) as result:
        metadata = cast(Dict[str, Any], result.metadata)
        assert metadata["canonical"] == "https://mongodb.com/docs/mongocli/install"


def test_metadata() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
======
Test
======

This is a test intro
            """,
            Path(
                "snooty.toml"
            ): """
name = "test_name"
title = "MongoDB title"

[[associated_products]]
name = "test_associated_product"
versions = ["v1", "v2"]
            """,
        }
    ) as result:
        metadata = cast(Dict[str, Any], result.metadata)
        assert len(metadata["associated_products"]) == 1
        assert len(metadata["associated_products"][0]["versions"]) == 2
        assert metadata["associated_products"][0]["name"] == "test_associated_product"


def test_openapi_metadata() -> None:
    with make_test(
        {
            Path(
                "source/admin/api/v3.txt"
            ): """
:orphan:
:template: openapi
:title: Atlas App Services Admin API

.. default-domain: mongodb

.. _admin-api:

.. openapi:: /openapi-admin-v3.yaml
            """,
            Path("source/openapi-admin-v3.yaml"): "",
            Path(
                "source/admin/api/url.txt"
            ): """
.. openapi:: https://raw.githubusercontent.com/mongodb/snooty-parser/master/test_data/test_parser/openapi-admin-v3.yaml
            """,
            Path(
                "source/admin/api/atlas.txt"
            ): """
.. openapi:: cloud
    :uses-realm:
            """,
            Path(
                "source/reference/api-resources-spec/v2.txt"
            ): """
.. openapi:: cloud
   :api-version: 2.0
            """,
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        openapi_pages = cast(Dict[str, Any], result.metadata["openapi_pages"])

        local_file_page = openapi_pages["admin/api/v3"]
        assert local_file_page["source_type"] == "local"
        assert local_file_page["source"] == "/openapi-admin-v3.yaml"

        url_page = openapi_pages["admin/api/url"]
        assert url_page["source_type"] == "url"
        assert (
            url_page["source"]
            == "https://raw.githubusercontent.com/mongodb/snooty-parser/master/test_data/test_parser/openapi-admin-v3.yaml"
        )

        atlas_page = openapi_pages["admin/api/atlas"]
        assert atlas_page["source_type"] == "atlas"
        assert atlas_page["source"] == "cloud"

        versioned_page = openapi_pages["reference/api-resources-spec/v2"]
        assert versioned_page["source_type"] == "atlas"
        assert versioned_page["source"] == "cloud"
        assert versioned_page["api_version"] == "2.0"
        resource_versions = versioned_page["resource_versions"]
        assert isinstance(resource_versions, list)
        assert all(isinstance(rv, str) for rv in resource_versions)


def test_openapi_preview() -> None:
    with make_test(
        {
            Path(
                "source/admin/api/preview.txt"
            ): """
.. openapi:: https://raw.githubusercontent.com/mongodb/snooty-parser/master/test_data/test_parser/openapi-admin-v3.yaml
   :preview:
            """,
        }
    ) as result:
        assert not [
            diagnostics for diagnostics in result.diagnostics.values() if diagnostics
        ], "Should not raise any diagnostics"
        assert "openapi_pages" not in result.metadata


def test_openapi_duplicates() -> None:
    with make_test(
        {
            Path(
                "source/admin/api/v3.txt"
            ): """
.. openapi:: /openapi-admin-v3.yaml

.. openapi:: https://raw.githubusercontent.com/mongodb/snooty-parser/master/test_data/test_parser/openapi-admin-v3.yaml
            """,
            Path("source/openapi-admin-v3.yaml"): "",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("admin/api/v3.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], DuplicateDirective)

        openapi_pages = cast(Dict[str, Any], result.metadata["openapi_pages"])
        # First openapi directive should be source of truth
        file_metadata = openapi_pages["admin/api/v3"]
        assert file_metadata["source_type"] == "local"
        assert file_metadata["source"] == "/openapi-admin-v3.yaml"


def test_openapi_invalid_version() -> None:
    with make_test(
        {
            Path(
                "source/reference/api-resources-spec/v3.txt"
            ): """
.. openapi:: cloud
   :api-version: 17.5
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("reference/api-resources-spec/v3.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], InvalidVersion)


def test_openapi_changelog_duplicates() -> None:
    with make_test(
        {
            Path(
                "source/reference/api-changelog.txt"
            ): """
.. openapi-changelog:: cloud
   :api-version: 2.0

.. openapi-changelog:: cloud
   :api-version: 2.0
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("reference/api-changelog.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], DuplicateDirective)


def test_static_assets() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. include:: /foo.rst
            """,
            Path(
                "source/foo.rst"
            ): """
.. figure:: figure.blob
            """,
            Path("source/figure.blob"): r"",
        }
    ) as result:
        assert [x.key for x in result.pages[FileId("index.txt")].static_assets] == [
            "figure.blob"
        ]


def test_facets() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """

.. facet::
   :name: genre
   :values: tutorial, reference

.. facet::
   :name: target_product
   :values: atlas

   .. facet::
      :name: version
      :values: v1.2

   .. facet::
      :name: sub_product
      :values: charts, data-federation


===========================
Facets
===========================
            """
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        facets = page.facets
        sortFn = lambda facet: facet.category + facet.value
        assert facets is not None
        assert facets.sort(key=sortFn) == (
            [
                Facet(category="genre", value="tutorial"),
                Facet(category="genre", value="reference"),
                Facet(
                    category="target_product",
                    value="atlas",
                    sub_facets=[
                        Facet(category="version", value="v1.2"),
                        Facet(
                            category="sub_product",
                            value="charts",
                            display_name="Charts",
                        ),
                        Facet(
                            category="sub_product",
                            value="data-federation",
                            display_name="Data Federation",
                        ),
                    ],
                ),
            ]
        ).sort(key=sortFn)

        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
  <section>
    <heading id="facets"><text>Facets</text></heading>
  </section>
</root>
            """,
        )


def test_toml_facets() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. facet::
   :name: genre
   :values: reference

.. facet::
   :name: target_product
   :values: atlas

   .. facet::
      :name: version
      :values: v1.2

   .. facet::
      :name: sub_product
      :values: charts,atlas-cli

.. facet::
   :name: genre
   :values: tutorial

===========================
Facets
===========================
            """,
            Path(
                "source/facets.toml"
            ): """
[[facets]]
category="target_product"
value = "drivers"

    [[facets.sub_facets]]
    category="sub_product"
    value = "c_driver"

[[facets]]
category = "programming_language"  # validate
value = "shell"

[[facets]]
category="test_facet"
value = "test"

    [[facets.sub_facets]]
    category="tested_nest"
    value = "test_nest"
""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        facets = page.facets

        assert facets is not None
        assert sorted(facets) == sorted(
            [
                Facet(category="genre", value="reference", display_name="Reference"),
                Facet(category="genre", value="tutorial", display_name="Tutorial"),
                Facet(
                    category="target_product",
                    value="atlas",
                    sub_facets=[
                        Facet(category="version", value="v1.2", display_name="v1.2"),
                        Facet(
                            category="sub_product",
                            value="charts",
                            display_name="Charts",
                        ),
                        Facet(
                            category="sub_product",
                            value="atlas-cli",
                            display_name="Atlas CLI",
                        ),
                    ],
                    display_name="Atlas",
                ),
                Facet(
                    category="programming_language", value="shell", display_name="Shell"
                ),
            ]
        )

        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
  <section>
    <heading id="facets"><text>Facets</text></heading>
  </section>
</root>
            """,
        )


def test_images() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """

======
Images
======

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img
            """
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
  <section>
    <heading id="images"><text>Images</text></heading>
    <directive name="image" alt="img"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
  </section>
</root>
""",
        )

    with make_test(
        {
            Path(
                "source/index.txt"
            ): """

======
Images
======

Image test

======
Images
======

Image test

======
Images
======

Image test


.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img

.. image:: /path/to/image.png
   :alt: img
            """
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
  <section>
    <heading id="images"><text>Images</text></heading>
    <paragraph><text>Image test</text></paragraph>
  </section>
  <section>
    <heading id="images-1"><text>Images</text></heading>
    <paragraph><text>Image test</text></paragraph>
  </section>
  <section>
    <heading id="images-2"><text>Images</text></heading>
    <paragraph><text>Image test</text></paragraph>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
    <directive name="image" alt="img" loading="lazy"><text>/path/to/image.png</text></directive>
  </section>
</root>
        """,
        )


def test_orphan_diagnostic() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
==========
Index Page
==========

.. toctree::

   /not-an-orphan
            """,
            Path(
                "source/orphan.txt"
            ): """
=========
An Orphan
=========
            """,
            Path(
                "source/marked-orphan.txt"
            ): """
:orphan:

===============
A Marked Orphan
===============
            """,
            Path(
                "source/not-an-orphan.txt"
            ): """
=============
Not An Orphan
=============
            """,
        }
    ) as result:
        assert {
            k: [type(d) for d in v] for k, v in result.diagnostics.items() if v
        } == {FileId("orphan.txt"): [OrphanedPage]}


def test_slug_to_breadcrumb_labels() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
==========
Index Page
==========

.. toctree::
   :titlesonly:

   Look at This </page1>
   Well, You Learned It </page2>
""",
            Path(
                "source/page1.txt"
            ): """
==============
Page One Title
==============

This is a cool first page.

.. toctree::
   </ref/page3>
""",
            Path(
                "source/page2.txt"
            ): """
==============
Page Two Title
==============

I think we did a great job teaching them.
""",
            Path(
                "source/ref/page3.txt"
            ): """
================
Page Three Title
================

Alrighty
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 0

        slug_to_breadcrumb_label_entry = cast(
            Dict[str, str], result.metadata["slugToBreadcrumbLabel"]
        )
        assert slug_to_breadcrumb_label_entry["page1"] == "Look at This"
        assert slug_to_breadcrumb_label_entry["page2"] == "Well, You Learned It"
        assert slug_to_breadcrumb_label_entry["ref/page3"] == "Page Three Title"

    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
==========
Index Page
==========

.. toctree::
   :titlesonly:

   </page1>
   </page2>
""",
            Path(
                "source/page1.txt"
            ): """
==============
Configure ``mongosh``
==============

Text for configuration.

""",
            Path(
                "source/page2.txt"
            ): """
==============
Customize the :binary:`~bin.mongosh` Prompt
==============

A very well-written page.
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 0

        slug_to_breadcrumb_label_entry = cast(
            Dict[str, str], result.metadata["slugToBreadcrumbLabel"]
        )
        assert slug_to_breadcrumb_label_entry["page1"] == "Configure mongosh"
        assert slug_to_breadcrumb_label_entry["page2"] == "Customize the mongosh Prompt"


def test_nested_collapsibles() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. collapsible::
    :heading: Heading
    :sub_heading: Subheading

    This is a parent 

    .. collapsible::
        :heading: Heading 2
        :sub_heading: Subheading 2

        This is a nested 
            """,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], NestedDirective)


def test_collapsible_headings() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents::
    :depth: 2

===================
Heading of the page
===================

Subsection heading
------------------

Subsubsection heading
~~~~~~~~~~~~~~~~~~~~~

.. collapsible::
    :heading: Collapsible heading
    :sub_heading: Subheading

    ~~~~~~~~~~~~~~~
    This is content
    ~~~~~~~~~~~~~~~
""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert (page.ast.options.get("headings")) == [
            {
                "depth": 2,
                "id": "subsection-heading",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 9}},
                        "value": "Subsection heading",
                    }
                ],
                "selector_ids": {},
            },
            {
                "depth": 3,
                "id": "subsubsection-heading",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 12}},
                        "value": "Subsubsection heading",
                    }
                ],
                "selector_ids": {},
            },
        ]

    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents::
   :depth: 1

===================
Heading of the page
===================

Subsection heading
------------------

.. collapsible::
    :heading: Collapsible heading
    :sub_heading: Subheading

    ~~~~~~~~~~~~~~~
    This is content
    ~~~~~~~~~~~~~~~

Subsubsection heading
~~~~~~~~~~~~~~~~~~~~~

.. collapsible::
    :heading: Collapsible heading 2
    :sub_heading: Subheading 2

    ~~~~~~~~~~~~~~~~~
    This is content 2
    ~~~~~~~~~~~~~~~~~
            """,
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert page.ast.options.get("headings") == [
            {
                "depth": 2,
                "id": "subsection-heading",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 9}},
                        "value": "Subsection heading",
                    }
                ],
                "selector_ids": {},
            }
        ]

    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents::
    :depth: 1

===================
Heading of the page
===================

.. collapsible::
    :heading: Collapsible heading
    :sub_heading: Subheading

    ~~~~~~~~~~~~~~~
    This is content
    ~~~~~~~~~~~~~~~
""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert page.ast.options.get("headings") == [
            {
                "depth": 2,
                "id": "collapsible-heading",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 8}},
                        "value": "Collapsible heading",
                    }
                ],
                "selector_ids": {},
            }
        ]


def test_collapsible_ref() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """

This is a page heading
======================

.. _ref_to_heading:

Section heading
---------------
            

.. _ref_to_collapsible:

.. collapsible::
    :heading: Collapsible heading

    This is a child paragraph of collapsible

    There is another heading
    ~~~~~~~~~~~~~~~~~~~~~~~~

There should be a link to collapsible :ref:`ref_to_collapsible`.

There should be a link to section heading :ref:`ref-to-heading`.

"""
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
  <section>
    <heading id="this-is-a-page-heading"><text>This is a page heading</text></heading>
    <target domain="std" name="label" html_id="std-label-ref_to_heading">
      <target_identifier ids="['ref_to_heading']"><text>Section heading</text></target_identifier>
    </target>
    <section>
      <heading id="section-heading"><text>Section heading</text></heading>
      <target domain="std" name="label" html_id="std-label-ref_to_collapsible">
        <target_identifier ids="['ref_to_collapsible']"><text>Collapsible heading</text></target_identifier>
      </target>
      <directive domain="mongodb" name="collapsible" heading="Collapsible heading" id="collapsible-heading">
        <section>
            <paragraph><text>This is a child paragraph of collapsible</text></paragraph>
            <section>
            <heading id="there-is-another-heading"><text>There is another heading</text></heading>
            </section>
        </section>
      </directive>
      <paragraph><text>There should be a link to collapsible </text>
        <ref_role domain="std" name="label" target="ref_to_collapsible"
          fileid="['index', 'std-label-ref_to_collapsible']"><text>Collapsible heading</text></ref_role><text>.</text>
      </paragraph>
      <paragraph><text>There should be a link to section heading </text>
        <ref_role domain="std" name="label" target="ref-to-heading"><text>ref-to-heading</text></ref_role><text>.</text>
      </paragraph>
    </section>
  </section>
</root>
""",
        )


def test_wayfinding() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. wayfinding::
   
   .. wayfinding-description::

      Wayfinding for mongosh

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: c

.. wayfinding::

   .. wayfinding-description::

      Wayfinding for mongosh 2

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: scala
""",
            Path(
                "source/includes/included_wayfinding.rst"
            ): """
.. wayfinding::
   
   .. wayfinding-description::

      Wayfinding for mongosh

   .. wayfinding-option:: https://www.mongodb.com/docs/
      :id: c
""",
            Path(
                "source/nested_wayfinding.txt"
            ): """
:orphan:

=================
Nested Wayfinding
=================

.. note::

   .. include:: /includes/included_wayfinding.rst
""",
            Path(
                "source/valid_wayfinding.txt"
            ): """
:orphan:

================
Valid Wayfinding
================

.. include:: /includes/included_wayfinding.rst
""",
        }
    ) as result:
        assert [type(x) for x in result.diagnostics[FileId("index.txt")]] == [
            DuplicateDirective
        ]
        assert [
            type(x)
            for x in result.diagnostics[FileId("includes/included_wayfinding.rst")]
        ] == [NestedDirective]
        assert len(result.diagnostics[FileId("valid_wayfinding.txt")]) == 0


def test_method_selector() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
============
Landing page
============
            
.. include:: /includes/included_method_selector.rst
         
.. method-selector::

   .. method-option::
      :id: cli

      .. collapsible::
         :heading: Collapsible 1
         :sub_heading: Subheading 1
      
         Collapsible 1 content.

      .. collapsible::
         :heading: Collapsible 2
         :sub_heading: Subheading 2

         Collapsible 2 content.
   
   .. method-option::
      :id: mongosh

      .. collapsible::
         :heading: Collapsible 1
         :sub_heading: Subheading 1
      
         Collapsible 1 content.

      .. collapsible::
         :heading: Collapsible 2
         :sub_heading: Subheading 2

         Collapsible 2 content.
""",
            Path(
                "source/includes/included_method_selector.rst"
            ): """
.. method-selector::
   
   .. method-option::
      :id: driver

      .. method-description::
         
         This is an optional description for drivers. Go to the `docs homepage <https://mongodb.com/docs/>`__ for more info.
      
         .. tabs-selector:: drivers

      .. collapsible::
         :heading: Collapsible 1
         :sub_heading: Subheading 1
      
         Collapsible 1 content.

      .. collapsible::
         :heading: Collapsible 2
         :sub_heading: Subheading 2

         Collapsible 2 content.

         .. tabs-drivers::
         
            .. tab::
               :tabid: c

               C tab content.
            
            .. tab::
               :tabid: cpp

               C++ tab content.
    
   .. method-option::
      :id: ui

      .. collapsible::
         :heading: Collapsible 1
         :sub_heading: Subheading 1
      
         Collapsible 1 content.

      .. collapsible::
         :heading: Collapsible 2
         :sub_heading: Subheading 2

         Collapsible 2 content.
   
   .. method-option::
      :id: compass

      .. collapsible::
         :heading: Collapsible 1
         :sub_heading: Subheading 1
      
         Collapsible 1 content.

      .. collapsible::
         :heading: Collapsible 2
         :sub_heading: Subheading 2

         Collapsible 2 content.
""",
            Path(
                "source/valid_method_selector.txt"
            ): """
:orphan:

=====================
Valid Method Selector
=====================

.. include:: /includes/included_method_selector.rst
""",
            Path(
                "source/testing_tabs_selector.txt"
            ): """
:orphan:

=====================
Testing Tabs Selector
=====================

.. tabs-selector:: drivers

.. method-selector::
   
   .. method-option::
      :id: driver

      .. method-description::
         
         This is an optional description for drivers. Go to the `docs homepage <https://mongodb.com/docs/>`__ for more info.

      Foo

      .. tabs-drivers::

         .. tab::
            :tabid: c

            C tab

         .. tab::
            :tabid: cpp

            C++ tab
    
   .. method-option::
      :id: ui

      Bar
""",
        }
    ) as result:
        assert [type(x) for x in result.diagnostics[FileId("index.txt")]] == [
            DuplicateDirective
        ]
        assert result.pages[FileId("index.txt")].ast.options.get("has_method_selector")
        assert [
            type(x) for x in result.diagnostics[FileId("testing_tabs_selector.txt")]
        ] == [UnexpectedDirectiveOrder]
        assert len(result.diagnostics[FileId("valid_method_selector.txt")]) == 0

        target_option_field = "has_method_selector"
        assert result.pages[FileId("index.txt")].ast.options.get(
            target_option_field, False
        )
        assert result.pages[FileId("valid_method_selector.txt")].ast.options.get(
            target_option_field, False
        )


def test_method_selector_headings() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents::
    :depth: 2

===================
Heading of the page
===================

Subsection heading
------------------

.. method-selector::

   .. method-option::
      :id: driver

      WHAT
      ~~~~

      .. method-description::

         This is an optional description. Learn more about drivers at `MongoDB Documentation <https://www.mongodb.com/docs/drivers/>`__.

      This is content in the Driver method haha.

   .. method-option::
      :id: cli

      This is a heading
      ~~~~~~~~~~~~~~~~~

      .. method-description::

         This is a description under the heading for cli.
      
      This is content in the CLI method haha.

   .. method-option::
      :id: mongosh

      Foo
      
""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert (page.ast.options.get("headings")) == [
            {
                "depth": 2,
                "id": "subsection-heading",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 9}},
                        "value": "Subsection heading",
                    }
                ],
                "selector_ids": {},
            },
            {
                "depth": 3,
                "id": "what",
                "selector_ids": {"method-option": "driver"},
                "title": [
                    {
                        "position": {"start": {"line": 17}},
                        "type": "text",
                        "value": "WHAT",
                    }
                ],
            },
            {
                "depth": 3,
                "id": "this-is-a-heading",
                "selector_ids": {"method-option": "cli"},
                "title": [
                    {
                        "position": {"start": {"line": 29}},
                        "type": "text",
                        "value": "This is a heading",
                    }
                ],
            },
        ]


def test_tab_headings() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents:: On this page
   :depth: 3

Title here
==========

.. tabs::
         
    .. tab:: tabs1
        :tabid: tabs1

        Heading here
        ------------
        This is content in tab1.

        .. tabs::

            .. tab:: tabby
                :tabid: tabby

                This is another headinge!
                ~~~~~~~~~~~~~~~~~~~~~~~~~

                Text ext text
      
""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert (page.ast.options.get("headings")) == [
            {
                "depth": 2,
                "id": "heading-here",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 13}},
                        "value": "Heading here",
                    }
                ],
                "selector_ids": {"tab": "tabs1"},
            },
            {
                "depth": 3,
                "id": "this-is-another-headinge-",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 22}},
                        "value": "This is another headinge!",
                    }
                ],
                "selector_ids": {"tab": "tabs1", "children": {"tab": "tabby"}},
            },
        ]


def test_composable_headings() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
.. contents:: On this page
   :local:
   :depth: 3

======================
This is the page title
======================
   
.. composable-tutorial::
   :options: interface, language
   :defaults: driver, nodejs
         
   .. selected-content::
      :selections: driver, nodejs

      This is a title under selected content
      --------------------------------------

      This is another heading!
      ~~~~~~~~~~~~~~~~~~~~~~~~~
      
""",
        }
    ) as result:
        test_file_id = FileId("index.txt")
        page = result.pages[test_file_id]
        diagnostics = result.diagnostics[test_file_id]
        assert len(diagnostics) == 0
        assert page.ast.options.get("headings") == [
            {
                "depth": 2,
                "id": "this-is-a-title-under-selected-content",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 17}},
                        "value": "This is a title under selected content",
                    }
                ],
                "selector_ids": {
                    "selected-content": {"interface": "driver", "language": "nodejs"}
                },
            },
            {
                "depth": 3,
                "id": "this-is-another-heading-",
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 20}},
                        "value": "This is another heading!",
                    }
                ],
                "selector_ids": {
                    "selected-content": {"interface": "driver", "language": "nodejs"}
                },
            },
        ]


def test_multi_page_tutorials() -> None:
    test_page_template = """
.. multi-page-tutorial::
   :time-required: 3
   :show-next-top:

=========
Test Page
=========

Words.

"""

    mock_filenames = [
        "tutorial/create-new-cluster.txt",
        "tutorial/create-serverless-instance.txt",
        "tutorial/create-global-cluster.txt",
        "tutorial/create-atlas-account.txt",
        "tutorial/deploy-free-tier-cluster.txt",
        "tutorial/create-mongodb-user-for-cluster.txt",
        "tutorial/connect-to-your-cluster.txt",
        "tutorial/insert-data-into-your-cluster.txt",
    ]
    mock_files: Dict[PurePath, Any] = {}
    for filename in mock_filenames:
        mock_files[PurePath(f"source/{filename}")] = test_page_template

    mock_files[
        PurePath("snooty.toml")
    ] = """
name = "test_multi_page_tutorials"
title = "MongoDB title"

toc_landing_pages = [
    "/create-connect-deployments",
    "/create-database-deployment",
    "/getting-started",
    "/foo",
]

multi_page_tutorials = [
    "/create-database-deployment",
    "/getting-started",
]
"""
    mock_files[
        PurePath("source/index.txt")
    ] = """
========
Homepage
========

Words!!!

.. toctree::
   :titlesonly:
      
   Getting Started </getting-started>
   Create & Connect Deployments </create-connect-deployments>
   Foo </foo>

"""

    # Handles nested TOC case
    mock_files[
        PurePath("source/create-connect-deployments.txt")
    ] = """
==============================
Create and Connect Deployments
==============================

Words.

.. toctree::
   :titlesonly:

   Create a Cluster </create-database-deployment>

"""
    mock_files[
        PurePath("source/create-database-deployment.txt")
    ] = """
.. toctree::
   :titlesonly:
      
   Cluster </tutorial/create-new-cluster>
   Serverless Instance </tutorial/create-serverless-instance>
   Global Cluster </tutorial/create-global-cluster>

==========================
Create Database Deployment
==========================

Words.

"""

    # Handles root TOC case
    mock_files[
        PurePath("source/getting-started.txt")
    ] = """
===============
Getting Started
===============

Words.

.. toctree::
   :titlesonly:

   Create an Account </tutorial/create-atlas-account>
   Deploy a Free Cluster </tutorial/deploy-free-tier-cluster>
   Manage Database Users </tutorial/create-mongodb-user-for-cluster>
   Connect to the Cluster </tutorial/connect-to-your-cluster>
   Insert and View a Document </tutorial/insert-data-into-your-cluster>

"""

    # Control; not intended to be included as MTP
    mock_files[
        PurePath("source/foo.txt")
    ] = """
===
Foo
===

Words!

"""

    with make_test(mock_files) as result:
        # Ensure handler adds settings to page options
        for filename in mock_filenames:
            mtp_options = result.pages[FileId(filename)].ast.options.get(
                "multi_page_tutorial_settings", None
            )
            assert isinstance(mtp_options, Dict)
            assert mtp_options.get("time_required", 0) > 0
            assert mtp_options.get("show_next_top", False)

        # Ensure metadata has a record of all multi-page tutorials
        multi_page_tutorials = result.metadata.get("multiPageTutorials", None)
        assert isinstance(multi_page_tutorials, Dict)
        assert multi_page_tutorials == {
            "getting-started": {
                "total_steps": 5,
                "slugs": [
                    "tutorial/create-atlas-account",
                    "tutorial/deploy-free-tier-cluster",
                    "tutorial/create-mongodb-user-for-cluster",
                    "tutorial/connect-to-your-cluster",
                    "tutorial/insert-data-into-your-cluster",
                ],
            },
            "create-database-deployment": {
                "total_steps": 3,
                "slugs": [
                    "tutorial/create-new-cluster",
                    "tutorial/create-serverless-instance",
                    "tutorial/create-global-cluster",
                ],
            },
        }


def test_footnote_id_numbers() -> None:
    with make_test(
        {
            Path(
                "source/includes/testing-footnotes-inside-includes.rst"
            ): """
This is content within an include for a footnote related to [#footnote-inside-includes]_ .
""",
            Path(
                "source/index.txt"
            ): """
=================
Testing Footnotes
=================

Two within same content block
-----------------------------

This is a paragraph with a footnote to [#footnote-same-block]_ . Here is another sentence
with another reference to the [#footnote-same-block]_ footnote.

.. [#footnote-same-block]

   Footnote within same content block.

Inside of includes
------------------

.. include:: /includes/testing-footnotes-inside-includes.rst

.. include:: /includes/testing-footnotes-inside-includes.rst

.. include:: /includes/testing-footnotes-inside-includes.rst

.. include:: /includes/testing-footnotes-inside-includes.rst

.. [#footnote-inside-includes]

   Footnotes inside of the same includes files, but different instances.

Numbered footnotes
------------------

This is a paragraph with a footnote to [1]_ . Here is another sentence
with another reference to the [1]_ footnote.

This is a paragraph with a footnote to [2]_ . Here is another sentence
with another reference to the [3]_ footnote.

This is a paragraph with a footnote to [3]_ . Here is another sentence
with another reference to the [2]_ footnote [1]_.

.. [1] Footnote 1?

.. [2] Footnote 2?

.. [3] 
   
   Footnote 3?
""",
        }
    ) as result:
        test_fileid = FileId("index.txt")
        page = result.pages[test_fileid]
        diagnostics = result.diagnostics[test_fileid]
        assert len(diagnostics) == 0
        check_ast_testing_string(
            page.ast,
            """
<root fileid="index.txt">
	<section>
		<heading id="testing-footnotes"><text>Testing Footnotes</text></heading>
		<section>
			<heading id="two-within-same-content-block"><text>Two within same content block</text></heading>
			<paragraph>
				<text>This is a paragraph with a footnote to </text>
				<footnote_reference id="id1" refname="footnote-same-block"></footnote_reference>
				<text> . Here is another sentence
with another reference to the </text>
				<footnote_reference id="id2" refname="footnote-same-block"></footnote_reference>
				<text> footnote.</text>
			</paragraph>
			<footnote id="footnote-same-block" name="footnote-same-block">
				<paragraph>
					<text>Footnote within same content block.</text>
				</paragraph>
			</footnote>
		</section>
		<section>
			<heading id="inside-of-includes"><text>Inside of includes</text></heading>
			<directive name="include">
				<text>/includes/testing-footnotes-inside-includes.rst</text>
				<root fileid="includes/testing-footnotes-inside-includes.rst">
					<paragraph>
						<text>This is content within an include for a footnote related to </text>
						<footnote_reference id="id3" refname="footnote-inside-includes"></footnote_reference>
						<text> .</text>
					</paragraph>
				</root>
			</directive>
			<directive name="include">
				<text>/includes/testing-footnotes-inside-includes.rst</text>
				<root fileid="includes/testing-footnotes-inside-includes.rst">
					<paragraph>
						<text>This is content within an include for a footnote related to </text>
						<footnote_reference id="id4" refname="footnote-inside-includes"></footnote_reference>
						<text> .</text>
					</paragraph>
				</root>
			</directive>
			<directive name="include">
				<text>/includes/testing-footnotes-inside-includes.rst</text>
				<root fileid="includes/testing-footnotes-inside-includes.rst">
					<paragraph>
						<text>This is content within an include for a footnote related to </text>
						<footnote_reference id="id5" refname="footnote-inside-includes"></footnote_reference>
						<text> .</text>
					</paragraph>
				</root>
			</directive>
			<directive name="include">
				<text>/includes/testing-footnotes-inside-includes.rst</text>
				<root fileid="includes/testing-footnotes-inside-includes.rst">
					<paragraph>
						<text>This is content within an include for a footnote related to </text>
						<footnote_reference id="id6" refname="footnote-inside-includes"></footnote_reference>
						<text> .</text>
					</paragraph>
				</root>
			</directive>
			<footnote id="footnote-inside-includes" name="footnote-inside-includes">
				<paragraph>
					<text>Footnotes inside of the same includes files, but different instances.</text>
				</paragraph>
			</footnote>
		</section>
		<section>
			<heading id="numbered-footnotes"><text>Numbered footnotes</text></heading>
			<paragraph>
				<text>This is a paragraph with a footnote to </text>
				<footnote_reference id="id7" refname="1"><text>1</text></footnote_reference>
				<text> . Here is another sentence
with another reference to the </text>
				<footnote_reference id="id8" refname="1"><text>1</text></footnote_reference>
				<text> footnote.</text>
			</paragraph>
			<paragraph>
				<text>This is a paragraph with a footnote to </text>
				<footnote_reference id="id9" refname="2"><text>2</text></footnote_reference>
				<text> . Here is another sentence
with another reference to the </text>
				<footnote_reference id="id10" refname="3"><text>3</text></footnote_reference>
				<text> footnote.</text>
			</paragraph>
			<paragraph>
				<text>This is a paragraph with a footnote to </text>
				<footnote_reference id="id11" refname="3">
					<text>3</text>
				</footnote_reference>
				<text> . Here is another sentence
with another reference to the </text>
				<footnote_reference id="id12" refname="2">
					<text>2</text>
				</footnote_reference>
				<text> footnote </text>
				<footnote_reference id="id13" refname="1">
					<text>1</text>
				</footnote_reference>
				<text>.</text>
			</paragraph>
			<footnote id="id10" name="1"><paragraph><text>Footnote 1?</text></paragraph></footnote>
			<footnote id="id11" name="2"><paragraph><text>Footnote 2?</text></paragraph></footnote>
			<footnote id="id12" name="3"><paragraph><text>Footnote 3?</text></paragraph></footnote>
		</section>
	</section>
</root>
""",
        )


def test_default_tabs() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
===================
Heading of the page
===================

.. tabs-selector:: drivers
   :default-tabid: python

.. tabs-drivers::

   .. tab::
      :tabid: c

      C

   .. tab::
      :tabid: nodejs

      Node.js

   .. tab::
      :tabid: python

      Python
""",
            Path(
                "source/no-default.txt"
            ): """
=================
No Default Tab ID
=================

.. tabs-selector:: drivers

.. tabs-drivers::

   .. tab::
      :tabid: c

      C

   .. tab::
      :tabid: nodejs

      Node.js

   .. tab::
      :tabid: python

      Python
""",
        },
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert (page.ast.options.get("default_tabs")) == {"drivers": "python"}

        # Ensure previously set default tabs are reset on the next page
        no_default_page = result.pages[FileId("no-default.txt")]
        assert (no_default_page.ast.options.get("default_tabs")) == None


def test_default_tabs_not_present() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
===================
Heading of the page
===================

.. tabs-selector:: drivers
   :default-tabid: no-language

.. tabs-drivers::

   .. tab::
      :tabid: c

      C

   .. tab::
      :tabid: nodejs

      Node.js

   .. tab::
      :tabid: python

      Python
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 1
        assert isinstance(diagnostics[0], UnknownDefaultTabId)


def test_composables() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
===================
Heading of the page
===================

.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-provider
   :defaults: driver, nodejs, repl, gcp

   .. selected-content::
      :selections: driver, nodejs, repl, gcp

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - Node
      Deployment Type - Replication
      """
        }
    ) as result:
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
            <root fileid="index.txt" has_composable_tutorial="True"><section><heading id="heading-of-the-page"><text>Heading of the page</text></heading><directive domain="mongodb" name="composable-tutorial" composable_options="[{'value': 'interface', 'text': 'Interface', 'default': 'driver', 'dependencies': [], 'selections': [{'value': 'driver', 'text': 'Driver'}]}, {'value': 'language', 'text': 'Language', 'default': 'nodejs', 'dependencies': [{'interface': 'driver'}], 'selections': [{'value': 'nodejs', 'text': 'Node.js'}]}, {'value': 'cluster-topology', 'text': 'Cluster Topology', 'default': 'repl', 'dependencies': [], 'selections': [{'value': 'repl', 'text': 'Replica Set'}]}, {'value': 'cloud-provider', 'text': 'Cloud Provider', 'default': 'gcp', 'dependencies': [], 'selections': [{'value': 'gcp', 'text': 'GCP'}]}]"><directive domain="mongodb" name="selected-content" selections="{'interface': 'driver', 'language': 'nodejs', 'cluster-topology': 'repl', 'cloud-provider': 'gcp'}"><paragraph><text>This content will only be shown when the selections are as follows:
Interface - Drivers
Language - Node
Deployment Type - Replication</text></paragraph></directive></directive></section></root>
                                 """,
        )


def test_composable_collisions() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
===================
Heading of the page
===================

.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-provider
   :defaults: driver, nodejs, repl, gcp

   .. selected-content::
      :selections: driver, nodejs, repl, gcp

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - Node
      Deployment Type - Replication

.. method-selector::

   .. method-option::
      :id: driver

      WHAT
      ~~~~

   .. method-option::
      :id: cli

      WHAT
      ~~~~

.. composable-tutorial::
   :options: interface, language, cluster-topology, cloud-provider
   :defaults: driver, nodejs, repl, gcp

   .. selected-content::
      :selections: driver, nodejs, repl, gcp

      This content will only be shown when the selections are as follows:
      Interface - Drivers
      Language - Node
      Deployment Type - Replication
""",
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("index.txt")]
        assert len(diagnostics) == 2
        assert isinstance(diagnostics[0], DuplicateDirective)
        assert isinstance(diagnostics[1], UnexpectedDirectiveOrder)


def test_dismissible_skills_card() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
===================
Heading of the page
===================

.. dismissible-skills-card::
   :skill: WOW Lightsaber Skill
   :url: https://learn.mongodb.com/courses/crud-operations-in-mongodb

""",
        }
    ) as result:
        page = result.pages[FileId("index.txt")]
        assert (page.ast.options.get("dismissible_skills_card")) == {
            "skill": "WOW Lightsaber Skill",
            "url": "https://learn.mongodb.com/courses/crud-operations-in-mongodb",
        }


def test_reserved_dirs() -> None:
    with make_test(
        {
            Path(
                "source/index.txt"
            ): """
========
Homepage
========

txt files inside of code-examples directories should not be parsed as reStructuredText.

.. literalinclude:: /code-examples/test.txt

.. literalinclude:: /includes/code-examples/test.txt

rst files inside of code-examples directories are okay to parse.

.. include:: /includes/code-examples/foo.rst

""",
            Path(
                "source/code-examples.txt"
            ): """
:orphan:

==================
Code Examples Page
==================

This page exists to make sure that pages titled code-examples are okay to have.

""",
            Path(
                "source/code-examples/test.txt"
            ): """
This is a code example and should not be captured as a page.
""",
            Path(
                "source/includes/code-examples/test.txt"
            ): """
This is another code example, but nested in a subdirectory, and should not be captured as a page.
""",
            Path(
                "source/includes/code-examples/foo.rst"
            ): """
This file makes sure that rst files nested in a code-examples subdirectory is okay.

.. warning::

   This is a test.

""",
        }
    ) as result:
        # txt files nested under code-examples directories should not be parsed as reStructuredText
        assert len(result.pages) == 3
        assert result.pages.get(FileId("code-examples/test.txt")) == None
        assert result.pages.get(FileId("includes/code-examples/test.txt")) == None

        # Allow rst files under code-examples to be parsed
        assert result.pages[FileId("includes/code-examples/foo.rst")]

        # Allow code-examples.txt files to be parsed
        assert result.pages[FileId("code-examples.txt")]

        assert len(result.diagnostics[FileId("index.txt")]) == 0
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
<root fileid="index.txt">
    <section>
        <heading id="homepage"><text>Homepage</text></heading>
        <paragraph><text>txt files inside of code-examples directories should not be parsed as reStructuredText.</text></paragraph>
        <directive name="literalinclude">
            <text>/code-examples/test.txt</text>
            <code copyable="True">
                This is a code example and should not be captured as a page.
            </code>
        </directive>
        <directive name="literalinclude">
            <text>/includes/code-examples/test.txt</text>
            <code copyable="True">
                This is another code example, but nested in a subdirectory, and should not be captured as a page.
            </code>
        </directive>
        <paragraph><text>rst files inside of code-examples directories are okay to parse.</text></paragraph>
        <directive name="include">
            <text>/includes/code-examples/foo.rst</text>
            <root fileid="includes/code-examples/foo.rst">
                <paragraph><text>This file makes sure that rst files nested in a code-examples subdirectory is okay.</text></paragraph>
                <directive name="warning">
                    <paragraph><text>This is a test.</text></paragraph>
                </directive>
            </root>
        </directive>
    </section>
</root>""",
        )

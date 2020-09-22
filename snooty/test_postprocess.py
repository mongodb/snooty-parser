"""An alternative and more granular approach to writing postprocessing tests.
   Eventually most postprocessor tests should probably be moved into this format."""

from pathlib import Path
from .util_test import make_test, check_ast_testing_string, ast_to_testing_string
from .types import FileId


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
<root>
    <target domain="std" name="label" html_id="std-label-a-MixedCase-Label">
        <target_identifier ids="['a-MixedCase-Label']"><text>Main Heading</text></target_identifier>
    </target>
    <section>
        <heading id="main-heading"><text>Main Heading</text></heading>
        <paragraph><ref_role domain="std" name="label" target="a-mixedcase-label"></ref_role></paragraph>
        <paragraph>
            <ref_role domain="std" name="label" target="a-MixedCase-Label" fileid="['index', 'std-label-a-MixedCase-Label']">
                <text>Main Heading</text>
            </ref_role>
        </paragraph>
    </section>
</root>
        """,
        )


def test_language_selector() -> None:
    with make_test(
        {
            Path(
                "source/tabs.txt"
            ): """
.. language-selector::

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
        assert len(result.diagnostics[FileId("tabs.txt")]) == 0
        page = result.pages[FileId("tabs.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root languages="['shell', 'python']">
<directive name="language-selector" />
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="shell">
<paragraph><text>Shell</text></paragraph>
</directive>
<directive name="tab" tabid="python">
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
.. language-selector::

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
            "nodejs" in diagnostic.message
            and "c" in diagnostic.message
            and "python" in diagnostic.message
            for diagnostic in result.diagnostics[FileId("tabs-two.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("tabs-two.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root languages="['c', 'nodejs']">
<directive name="language-selector" />
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="c">
<paragraph><text>C</text></paragraph>
</directive>
<directive name="tab" tabid="nodejs">
<paragraph><text>Node.js</text></paragraph>
</directive>
</directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="c">
<paragraph><text>C</text></paragraph>
</directive>
</directive>
<directive name="tabs" hidden="True" tabset="drivers">
<directive name="tab" tabid="python">
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
.. language-selector::
"""
        }
    ) as result:
        assert [
            "Expected tabs" in diagnostic.message
            for diagnostic in result.diagnostics[FileId("tabs-three.txt")]
        ] == [True], "Incorrect diagnostics raised"
        page = result.pages[FileId("tabs-three.txt")]
        print(ast_to_testing_string(page.ast))
        check_ast_testing_string(
            page.ast,
            """
<root>
<directive name="language-selector" />
</root>
            """,
        )

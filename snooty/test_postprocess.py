"""An alternative and more granular approach to writing postprocessing tests.
   Eventually most postprocessor tests should probably be moved into this format."""

from pathlib import Path
from .util_test import make_test, check_ast_testing_string, ast_to_testing_string
from .types import FileId

# ensure that broken links still generate titles
def test_broken_link() -> None:
     with make_test(
        {
        Path("source/param.txt"): """
=========
$title
=========

.. parameter:: $title 

The :parameter:`title` stuff works 


"""
        }
    ) as result:
        page = result.pages[FileId("param.txt")]
        check_ast_testing_string(
                    page.ast,
                    """
<root>
    <section>
        <heading id="title">
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

# def test_case_sensitive_labels() -> None:
#     with make_test(
#         {
#             Path(
#                 "source/index.txt"
#             ): """
# .. _a-MixedCase-Label:

# ============
# Main Heading
# ============

# :ref:`a-mixedcase-label`

# :ref:`a-MixedCase-Label`
# """
#         }
#     ) as result:
#         assert [
#             "a-mixedcase-label" in diagnostic.message
#             for diagnostic in result.diagnostics[FileId("index.txt")]
#         ] == [True], "Incorrect diagnostics raised"
#         page = result.pages[FileId("index.txt")]
#         print(ast_to_testing_string(page.ast))
#         check_ast_testing_string(
#             page.ast,
#             """
# <root>
#     <target domain="std" name="label" html_id="std-label-a-MixedCase-Label">
#         <target_identifier ids="['a-MixedCase-Label']"><text>Main Heading</text></target_identifier>
#     </target>
#     <section>
#         <heading id="main-heading"><text>Main Heading</text></heading>
#         <paragraph><ref_role domain="std" name="label" target="a-mixedcase-label"></ref_role></paragraph>
#         <paragraph>
#             <ref_role domain="std" name="label" target="a-MixedCase-Label" fileid="['index', 'std-label-a-MixedCase-Label']">
#                 <text>Main Heading</text>
#             </ref_role>
#         </paragraph>
#     </section>
# </root>
#         """,
#         )


# def test_same_page_target_resolution() -> None:
#     with make_test(
#         {
#             Path(
#                 "source/program1.txt"
#             ): """
# =========
# Program 1
# =========

# .. program:: program1

# .. option:: --verbose

#    Verbose

# .. include:: /includes/fact.rst
# """,
#             Path(
#                 "source/program2.txt"
#             ): """
# =========
# Program 2
# =========

# .. program:: program2

# .. option:: --verbose

#    Verbose

# .. include:: /includes/fact.rst
# """,
#             Path(
#                 "source/includes/fact.rst"
#             ): """
# :option:`--verbose`

# :option:`program1 --verbose`

# :option:`program2 --verbose`
# """,
#         }
#     ) as result:
#         assert not [
#             diagnostics for diagnostics in result.diagnostics.values() if diagnostics
#         ], "Should not raise any diagnostics"
#         page = result.pages[FileId("program1.txt")]
#         check_ast_testing_string(
#             page.ast,
#             """
# <root><section>
#     <heading id="program-1"><text>Program 1</text></heading>

#     <target domain="std" name="program" html_id="std-program-program1">
#         <directive_argument>
#             <literal><text>program1</text></literal>
#         </directive_argument>
#         <target_identifier ids="['program1']"><text>program1</text></target_identifier>
#     </target>

#     <target domain="std" name="option" html_id="std-option-program1.--verbose">
#         <directive_argument><literal><text>--verbose</text></literal></directive_argument>
#         <target_identifier ids="['--verbose', 'program1.--verbose']"><text>program1 --verbose</text></target_identifier>
#         <paragraph><text>Verbose</text></paragraph>
#     </target>

#     <directive name="include">
#         <text>/includes/fact.rst</text>
#         <paragraph>
#             <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
#                 <literal><text>program1 --verbose</text></literal>
#             </ref_role>
#         </paragraph>

#         <paragraph>
#             <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
#                 <literal><text>program1 --verbose</text></literal>
#             </ref_role>
#         </paragraph>

#         <paragraph>
#             <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
#                 <literal><text>program2 --verbose</text></literal>
#             </ref_role>
#         </paragraph>
#     </directive>
# </section></root>
#         """,
#         )

#         page = result.pages[FileId("program2.txt")]
#         check_ast_testing_string(
#             page.ast,
#             """
# <root><section>
#     <heading id="program-2"><text>Program 2</text></heading>

#     <target domain="std" name="program" html_id="std-program-program2">
#         <directive_argument>
#             <literal><text>program2</text></literal>
#         </directive_argument>
#         <target_identifier ids="['program2']"><text>program2</text></target_identifier>
#     </target>

#     <target domain="std" name="option" html_id="std-option-program2.--verbose">
#         <directive_argument><literal><text>--verbose</text></literal></directive_argument>
#         <target_identifier ids="['--verbose', 'program2.--verbose']"><text>program2 --verbose</text></target_identifier>
#         <paragraph><text>Verbose</text></paragraph>
#     </target>

#     <directive name="include">
#         <text>/includes/fact.rst</text>
#         <paragraph>
#             <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
#                 <literal><text>program2 --verbose</text></literal>
#             </ref_role>
#         </paragraph>

#         <paragraph>
#             <ref_role domain="std" name="option" target="program1.--verbose" fileid="['program1', 'std-option-program1.--verbose']">
#                 <literal><text>program1 --verbose</text></literal>
#             </ref_role>
#         </paragraph>

#         <paragraph>
#             <ref_role domain="std" name="option" target="program2.--verbose" fileid="['program2', 'std-option-program2.--verbose']">
#                 <literal><text>program2 --verbose</text></literal>
#             </ref_role>
#         </paragraph>
#     </directive>
# </section></root>
#         """,
#         )

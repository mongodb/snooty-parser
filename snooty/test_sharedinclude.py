from pathlib import Path

from .diagnostics import CannotOpenFile, ConfigurationProblem, SubstitutionRefError
from .types import FileId
from .util_test import check_ast_testing_string, make_test


def test_sharedinclude() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test"
sharedinclude_root = "https://raw.githubusercontent.com/10gen/docs-shared/test/"
""",
            Path(
                "source/index.txt"
            ): """
.. sharedinclude:: test/sample-item.rst

   .. replacement:: name

      Heli

   .. replacement:: block

      .. note::

         Huzzah!
""",
        }
    ) as result:
        assert result.diagnostics == {
            FileId("index.txt"): [],
            FileId("sharedinclude/test/sample-item.rst"): [],
        }
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
<root fileid="index.txt">
    <directive name="sharedinclude">
        <text>sharedinclude/test/sample-item.rst</text>
        <directive name="replacement"><text>name</text><paragraph><text>Heli</text></paragraph></directive>
        <directive name="replacement"><text>block</text><directive name="note"><paragraph><text>Huzzah!</text></paragraph></directive></directive>

        <root fileid="sharedinclude/test/sample-item.rst">
            <paragraph>
                <text>Hello </text><substitution_reference name="name"><text>Heli</text></substitution_reference><text>, this is a shared item!</text>
            </paragraph>
            <directive name="important">
                <text>This heading is important.</text>
                <paragraph><text>Have you drunk enough water today?</text></paragraph>
            </directive>
            <substitution_reference name="block">
                <directive name="note">
                    <paragraph><text>Huzzah!</text></paragraph>
                </directive>
            </substitution_reference>
        </root>
    </directive>
</root>
""",
        )


def test_sharedinclude_bad_file() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test"
sharedinclude_root = "https://raw.githubusercontent.com/10gen/docs-shared/test/"
""",
            Path(
                "source/index.txt"
            ): """
.. sharedinclude:: gooblygoobly.rst
""",
        }
    ) as result:
        assert {
            f: [type(d) for d in diagnostics]
            for f, diagnostics in result.diagnostics.items()
        } == {FileId("index.txt"): [CannotOpenFile]}


def test_sharedinclude_missed_replacement() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test"
sharedinclude_root = "https://raw.githubusercontent.com/10gen/docs-shared/test/"
""",
            Path(
                "source/index.txt"
            ): """
.. sharedinclude:: test/sample-item.rst

   .. replacement:: name

      Heli
""",
        }
    ) as result:
        assert {
            f: [type(d) for d in diagnostics]
            for f, diagnostics in result.diagnostics.items()
        } == {
            FileId("index.txt"): [],
            FileId("sharedinclude/test/sample-item.rst"): [SubstitutionRefError],
        }


def test_sharedinclude_missed_configuration() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test"
""",
            Path(
                "source/index.txt"
            ): """
.. sharedinclude:: test/sample-item.rst
""",
        }
    ) as result:
        assert {
            f: [type(d) for d in diagnostics]
            for f, diagnostics in result.diagnostics.items()
        } == {
            FileId("index.txt"): [ConfigurationProblem],
        }

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..diagnostics import (
    Diagnostic,
    ErrorParsingYAMLFile,
    FailedToInheritRef,
    UnmarshallingError,
)
from ..n import FileId
from ..page import Page
from ..parser import EmbeddedRstParser
from ..types import ProjectConfig
from ..util_test import check_ast_testing_string, make_test
from .extracts import GizaExtractsCategory


def test_extract() -> None:
    root_path = Path("test_data/test_gizaparser")
    project_config = ProjectConfig(root_path, "")
    category = GizaExtractsCategory(project_config)

    fileid = FileId("includes/extracts-test.yaml")
    parent_fileid = FileId("includes/extracts-test-parent.yaml")

    def add_main_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(fileid)
        category.add(fileid, text, extracts)
        assert len(parse_diagnostics) == 1
        assert parse_diagnostics[0].severity == Diagnostic.Level.error
        assert parse_diagnostics[0].start == (21, 0)
        assert len(extracts) == 5
        return parse_diagnostics

    def add_parent_file() -> List[Diagnostic]:
        extracts, text, parse_diagnostics = category.parse(parent_fileid)
        category.add(parent_fileid, text, extracts)
        assert len(parse_diagnostics) == 0
        assert len(extracts) == 1
        return parse_diagnostics

    all_diagnostics: Dict[FileId, List[Diagnostic]] = {}
    all_diagnostics[fileid] = add_main_file()
    all_diagnostics[parent_fileid] = add_parent_file()

    assert len(category) == 2
    _, giza_node = next(category.reify_all_files(all_diagnostics))

    def create_page(filename: Optional[str]) -> Tuple[Page, EmbeddedRstParser]:
        page = Page.create(fileid, filename, "")
        return (page, EmbeddedRstParser(project_config, page, all_diagnostics[fileid]))

    pages = category.to_pages(fileid, create_page, giza_node.data)
    assert [page.fake_full_fileid().as_posix() for page in pages] == [
        "includes/extracts/installation-directory-rhel.rst",
        "includes/extracts/broken-inherit.rst",
        "includes/extracts/another-file.rst",
        "includes/extracts/missing-substitution.rst",
    ]

    check_ast_testing_string(
        pages[0].ast,
        """<root fileid="includes/extracts-test.yaml">
    <directive name="extract">
        <paragraph>
            <text>By default, MongoDB stores its data files in</text>
            <literal><text>/var/lib/mongo</text></literal>
            <text> and its\nlog files in </text>
            <literal><text>/var/log/mongodb</text></literal><text>.</text>
        </paragraph>
    </directive>
</root>""",
    )

    check_ast_testing_string(
        pages[3].ast,
        """
<root fileid="includes/extracts-test.yaml">
    <directive name="extract"><paragraph><text>Substitute</text></paragraph></directive>
</root>
""",
    )

    # XXX: We need to track source file information for each property.
    # Line number 1 here should correspond to parent_path, not path.
    assert set(d.start[0] for d in all_diagnostics[fileid]) == set((21, 13, 1))


def test_inheritance() -> None:
    with make_test(
        {
            Path(
                "source/includes/extracts-test.yaml"
            ): """
ref: create-resource-lock
content: |

  {{operation}} obtains an exclusive lock on the
  specified collection or view for the duration of the operation.

replacement:
  operation: "``create``"
---
ref: createCollection-resource-lock
source:
  file: extracts-test.yaml
  ref: create-resource-lock
replacement:
  operation: "``db.createCollection()``"
---
ref: createView-resource-lock
source:
  file: extracts-test.yaml
  ref: create-resource-lock
replacement:
  operation: "``db.createView()``"
"""
        }
    ) as result:
        assert not result.diagnostics[FileId("includes/extracts-test.yaml")]


def test_external_cycle() -> None:
    with make_test(
        {
            Path(
                "source/includes/extracts-test1.yaml"
            ): """
ref: test1
inherit:
  file: extracts-test2.yaml
  ref: test2
...
""",
            Path(
                "source/includes/extracts-test2.yaml"
            ): """
ref: test2
inherit:
  file: extracts-test1.yaml
  ref: test1
...
""",
        }
    ) as result:
        assert {k: [type(d) for d in v] for k, v in result.diagnostics.items()} == {
            FileId("includes/extracts-test2.yaml"): [FailedToInheritRef],
            FileId("includes/extracts-test1.yaml"): [FailedToInheritRef],
        }


def test_partial_unmarshaling_error() -> None:
    with make_test(
        {
            Path(
                "source/includes/extracts-test1.yaml"
            ): """
ref: bypassDocumentValidation-db.collection.aggregate
inherit:
  ref: _bypassDocValidation
  file: extracts-bypassDocumentValidation-base.yaml
replacement:
  role: ":method:`db.collection.aggregate()`"
  interface: "method"
post: |
  Document validation only occurs if you are using the
  :pipeline:`$out` operator in your aggregation operation.
---
ref: bypassDocumentValidation-aggregate
content: "Okay"
...
"""
        }
    ) as result:
        assert list(result.pages.keys()) == [
            FileId("includes/extracts/bypassDocumentValidation-aggregate.rst")
        ]
        assert {k: [type(d) for d in v] for k, v in result.diagnostics.items()} == {
            FileId("includes/extracts-test1.yaml"): [UnmarshallingError]
        }


def test_single_unmarshaling_error() -> None:
    with make_test(
        {
            Path(
                "source/includes/extracts-test1.yaml"
            ): """
ref: bypassDocumentValidation-db.collection.aggregate
inherit:
  ref: _bypassDocValidation
  file: extracts-bypassDocumentValidation-base.yaml
replacement:
  role: ":method:`db.collection.aggregate()`"
  interface: "method"
post: |
  Document validation only occurs if you are using the
  :pipeline:`$out` operator in your aggregation operation.
...
"""
        }
    ) as result:
        assert list(result.pages.keys()) == []
        assert {k: [type(d) for d in v] for k, v in result.diagnostics.items()} == {
            FileId("includes/extracts-test1.yaml"): [UnmarshallingError]
        }


def test_parse_error() -> None:
    with make_test(
        {
            Path(
                "source/includes/extracts-test1.yaml"
            ): """
ref: bypassDocumentValidation
content: "not okay
"""
        }
    ) as result:
        assert list(result.pages.keys()) == []
        assert {k: [type(d) for d in v] for k, v in result.diagnostics.items()} == {
            FileId("includes/extracts-test1.yaml"): [ErrorParsingYAMLFile]
        }

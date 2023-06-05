from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import DefaultDict, Dict, List

from .diagnostics import (
    ConstantNotDeclared,
    Diagnostic,
    GitMergeConflictArtifactFound,
    UnmarshallingError,
)
from .n import FileId, SerializableType
from .page import Page
from .parser import Project, ProjectBackend
from .target_database import TargetDatabase
from .types import BuildIdentifierSet, ProjectConfig
from .util_test import check_ast_testing_string, make_test

build_identifiers: BuildIdentifierSet = {"commit_hash": "123456", "patch_id": "789"}


@dataclass
class Backend(ProjectBackend):
    metadata: Dict[str, SerializableType] = field(default_factory=dict)
    pages: Dict[FileId, Page] = field(default_factory=dict)
    updates: List[FileId] = field(default_factory=list)
    diagnostics: DefaultDict[FileId, List[Diagnostic]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        self.diagnostics[path].extend(diagnostics)

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        self.pages[page_id] = page
        self.updates.append(page_id)

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        self.metadata.update(field)

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        pass

    def flush(self) -> None:
        pass


def test_merge_conflict() -> None:
    project_path = Path("test_data/merge_conflict")
    project_config, _ = ProjectConfig.open(project_path)
    file_path = Path("test_data/merge_conflict/source/index.txt")
    _, project_diagnostics = project_config.read(file_path)

    assert isinstance(
        project_diagnostics[-1], GitMergeConflictArtifactFound
    ) and project_diagnostics[-1].start == (68, 0)
    assert isinstance(
        project_diagnostics[-2], GitMergeConflictArtifactFound
    ) and project_diagnostics[-2].start == (35, 0)


def test_bad_project() -> None:
    backend = Backend()
    Project(Path("test_data/bad_project"), backend, build_identifiers)
    fileid = FileId("snooty.toml")
    assert list(backend.diagnostics.keys()) == [fileid]
    diagnostics = backend.diagnostics[fileid]
    assert len(diagnostics) == 1
    assert isinstance(diagnostics[0], ConstantNotDeclared)


def test_missing_deprecated_versions() -> None:
    backend = Backend()
    project = Project(Path("test_data/test_project"), backend, build_identifiers)
    project.build()
    assert "deprecated_versions" not in backend.metadata


def test_not_a_project() -> None:
    backend = Backend()
    project = Project(Path("test_data/not_a_project"), backend, build_identifiers)
    project.build()


def test_get_ast() -> None:
    backend = Backend()
    project = Project(Path("test_data/get-preview"), backend, build_identifiers)
    project.build()
    ast = project.get_page_ast(
        Path("test_data/get-preview/source/index.txt").absolute()
    )
    check_ast_testing_string(
        ast,
        """<root fileid="index.txt">
        <section>
        <heading id="index"><text>Index</text></heading>
        <paragraph><text>Test.</text></paragraph>
        <directive name="include"><text>/includes/steps/test.rst</text>
            <root fileid="includes/steps-test.yaml">
            <directive name="procedure" style="normal"><directive name="step"><section><heading id="identify-the-privileges-granted-by-a-role">
            <text>Identify the privileges granted by a role.</text></heading>
            <paragraph><text>this is a test step.</text></paragraph></section></directive></directive>
            </root>
        </directive>
        <directive name="include"><text>/includes/extracts/test.rst</text>
            <root fileid="includes/extracts-test.yaml">
                <directive name="extract">
                    <paragraph><text>test extract</text></paragraph>
                </directive>
            </root>
        </directive>
        <directive name="include">
            <text>/includes/release/pin-version-intro.rst</text>
            <root fileid="includes/release-pinning.yaml">
                <directive name="release_specification">
                    <paragraph><text>To install a specific release, you must specify each component package
individually along with the version number, as in the
following example:</text></paragraph>
                </directive>
            </root>
        </directive></section></root>""",
    )


def test_start_from_child_directory() -> None:
    backend = Backend()
    project = Project(
        Path("test_data/test_project/source/images"), backend, build_identifiers
    )
    assert project.config.root == Path("test_data/test_project").absolute()


def test_recursive_source_constants() -> None:
    with make_test(
        {
            PurePath(
                "snooty.toml"
            ): """
name = "recursive_source_constants"

[constants]
major-version = 4
minor-version = 3
patch-version = 2
version = "{+major-version+}.{+minor-version+}"
full-version = "{+version+}.{+patch-version+}"
""",
            PurePath("source/index.txt"): """{+full-version+}""",
        }
    ) as result:
        assert not result.diagnostics[FileId("index.txt")]
        check_ast_testing_string(
            result.pages[FileId("index.txt")].ast,
            """
<root fileid="index.txt"><paragraph><text>4.3.2</text></paragraph></root>
""",
        )


def test_target_wipe() -> None:
    backend = Backend()
    with Project(
        Path("test_data/test_postprocessor"), backend, {}, watch=False
    ) as project:
        project.build()
        with project._lock:
            query_result = project._project.targets["std:label:global-writes-zones"][0]
            assert isinstance(query_result, TargetDatabase.InternalResult)
            assert query_result.result[0] == "index"

        project.update(
            Path("test_data/test_postprocessor/source/index.txt").resolve(),
            ".. _gooblygooblygoo:\n",
        )
        project.postprocess()
        with project._lock:
            assert not project._project.targets["std:label:global-writes-zones"]
            query_result = project._project.targets["std:label:gooblygooblygoo"][0]
            assert isinstance(query_result, TargetDatabase.InternalResult)
            assert query_result.result[0] == "index"


def test_invalid_data() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): r"""
name = "invalid_data"

[data]
source_page_template = "https://github.com/mongodb/docs/blob/master/source/%s.txt"
invalid = {foo = "bar"}
""",
            Path("source/index.txt"): r"",
        }
    ) as result:
        assert [type(d) for d in result.diagnostics[FileId("snooty.toml")]] == [
            UnmarshallingError
        ]

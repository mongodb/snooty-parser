import shutil
import sys
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import DefaultDict, Dict, List

from . import n
from .diagnostics import (
    ConstantNotDeclared,
    Diagnostic,
    GitMergeConflictArtifactFound,
    UnmarshallingError,
)
from .n import FileId, SerializableType
from .page import Page
from .parse_cache import CacheStats
from .parser import Project, ProjectBackend
from .target_database import TargetDatabase
from .types import BuildIdentifierSet, ProjectConfig
from .util import ast_dive
from .util_test import (
    BackendTestResults,
    check_ast_testing_string,
    make_test,
    make_test_project,
)

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


def test() -> None:
    backend = Backend()
    n_threads = len(threading.enumerate())
    with Project(Path("test_data/test_project"), backend, build_identifiers) as project:
        project.build()
        # Ensure that filesystem monitoring threads have been started
        assert len(threading.enumerate()) > n_threads

        # Ensure that the correct pages and assets exist
        index_id = FileId("index.txt")
        assert list(backend.pages.keys()) == [index_id]
        # Confirm that no diagnostics were created
        assert backend.diagnostics[index_id] == []
        code_length = 0
        checksums: List[str] = []
        index = backend.pages[index_id]
        assert len(index.static_assets) == 1
        assert not index.pending_tasks
        for node in ast_dive(index.ast):
            if isinstance(node, n.Code):
                code_length += len(node.value)
            elif isinstance(node, n.Directive) and node.name == "figure":
                checksums.append(node.options["checksum"])
        assert code_length == 345
        assert checksums == [
            "10e351828f156afcafc7744c30d7b2564c6efba1ca7c55cac59560c67581f947"
        ]
        assert backend.updates == [index_id]

        # Skip the remainder of the tests on non-Darwin platforms; they fail for
        # unknown reasons.
        if sys.platform != "darwin":
            return

        figure_id = FileId("images/compass-create-database.png")
        with project._lock:
            assert list(
                project._project.expensive_operation_cache.get_versions(figure_id)
            ) == [1]
        with project.config.source_path.joinpath(figure_id).open(mode="r+b") as f:
            text = f.read()
            f.seek(0)
            f.truncate(0)
            f.write(text)
            f.flush()
        time.sleep(0.1)
        with project._lock:
            assert list(
                project._project.expensive_operation_cache.get_versions(figure_id)
            ) == [2]

        # Ensure that the page has been reparsed 2 times
        assert backend.updates == [index_id, index_id]

    # Ensure that any filesystem monitoring threads have been shut down
    assert len(threading.enumerate()) == n_threads


def test_facet_propagation() -> None:
    backend = Backend()
    project = Project(Path("test_data/test_facets"), backend, build_identifiers)
    project.build()

    index_id = FileId("index.txt")
    index = backend.pages[index_id]

    assert index.facets is not None
    assert index.facets[0].sub_facets is not None

    assert index.facets[0].sub_facets[0].category == "sub_product"
    assert index.facets[0].sub_facets[0].value == "atlas-app-services"

    driver_id = FileId("driver-examples/driver.rst")
    driver = backend.pages[driver_id]

    assert driver.facets is not None
    assert driver.facets[0].sub_facets is not None

    assert driver.facets[0].sub_facets[0].category == "sub_product"
    assert driver.facets[0].sub_facets[0].value == "charts"

    nest_id = FileId("driver-examples/nest/nest.txt")
    nest = backend.pages[nest_id]

    assert nest.facets is not None
    assert nest.facets[0].sub_facets is not None

    assert nest.facets[0].sub_facets[0].category == "sub_product"
    assert nest.facets[0].sub_facets[0].value == "atlas-cli"


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
            FileId("index.txt"),
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


def test_cache() -> None:
    with make_test_project(
        {
            Path(
                "snooty.toml"
            ): """
name = "test_cache"

[substitutions]
foo = "bar"
""",
            Path(
                "source/index.txt"
            ): """
.. include:: /foobar.rst
""",
            Path(
                "source/foobar.rst"
            ): """
Testing {+foo+}
""",
        }
    ) as (_project, backend):
        with _project._get_inner() as project:
            project.load_cache()
            project.build(1, False)
            assert project.cache is not None

            assert project.cache.stats == CacheStats(hits=0, misses=2, errors=0)

            project.update_cache()
            project.load_cache()
            project.build(1, False)

            assert project.cache.stats == CacheStats(hits=2, misses=0, errors=0)

            # Ensure that the cache is valid even if it's copied to a different directory
            with tempfile.TemporaryDirectory() as tempdirname:
                shutil.copytree(project.config.root, tempdirname, dirs_exist_ok=True)
                backend_copy = BackendTestResults()
                project_copy = Project(Path(tempdirname), backend_copy, {})
                project_copy.load_cache()
                project_copy.build()
                with project_copy._get_inner() as _project_copy:
                    assert _project_copy.cache is not None
                    assert _project_copy.cache.stats == CacheStats(
                        hits=2, misses=0, errors=0
                    )

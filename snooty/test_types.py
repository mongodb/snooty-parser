from pathlib import Path, PurePath
from .types import (
    Diagnostic,
    ParserDiagnostic,
    UnexpectedIndentation,
    ProjectConfig,
    StaticAsset,
    Page,
    FileId,
)
import pytest


def test_project() -> None:
    path = Path("test_data/bad_project")
    project_config, project_diagnostics = ProjectConfig.open(path)
    assert len(project_diagnostics) == 1
    assert project_config.constants == {
        "version": "3.4",
        "package_title": "3.4.tar.gz",
        "invalid": "\u200b",
    }

    assert project_config.substitution_nodes == {}
    assert project_config.substitutions == {"guides-short": "MongoDB Guides"}

    path = Path("test_data/empty_project")
    project_config, project_diagnostics = ProjectConfig.open(path)
    assert project_config.constants == {}

    # Test missing project behavior
    project_config, project_diagnostics = ProjectConfig.open(Path(".").resolve())
    assert project_config.name == "unnamed"
    assert project_config.title == "untitled"
    assert len(project_diagnostics) == 0


# this is basically what i need to rewrite
def test_diagnostics() -> None:
    diagnostic = UnexpectedIndentation("foo", (0, 0), 10)
    assert isinstance(diagnostic, UnexpectedIndentation)
    assert isinstance(diagnostic, ParserDiagnostic)
    assert diagnostic.severity == Diagnostic.Level.error
    assert diagnostic.start == (0, 0)
    assert diagnostic.end[0] == 10 and diagnostic.end[1] > 100

    # Make sure attempts to access abstract Diagnostic base class
    # results in TypeError
    with pytest.raises(TypeError):
        Diagnostic("foo", (0, 0), 10).severity


def test_static_asset() -> None:
    path = Path("test_data/compass-explain-plan-with-index-raw-json.png")
    asset = StaticAsset.load(FileId("foo"), path)
    assert (
        asset.get_checksum()
        == "e8d907020488a0b0ba070ae3eeb86aae2713a61cc5bb28346c023cb505cced3c"
    )
    asset2 = StaticAsset.load(FileId("foo"), path)
    asset3 = StaticAsset.load(FileId("bar"), path)

    assert asset == asset2 != asset3

    # Make sure that assets are hashed correctly
    collection = set((asset, asset2))
    assert len(collection) == 1
    collection = set((asset, asset3))
    assert len(collection) == 2


def test_page() -> None:
    page = Page.create(Path("foo.rst"), None, "")
    assert page.fake_full_path() == PurePath("foo.rst")

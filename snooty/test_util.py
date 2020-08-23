import os
import pytest
import sys
import time
import watchdog.events
from pathlib import Path, PurePath
from typing import List, Tuple
from . import util


def test_reroot_path() -> None:
    relative, absolute = util.reroot_path(
        PurePath("/foo/bar/baz.rst"), PurePath("/foo/dir/test.txt"), Path("foo")
    )
    assert absolute.is_absolute()
    assert relative == PurePath("foo/bar/baz.rst")
    assert util.reroot_path(
        PurePath("../bar/baz.rst"), PurePath("foo/dir/test.txt"), Path("foo")
    )[0] == PurePath("foo/bar/baz.rst")


def test_option_string() -> None:
    assert util.option_string("Test") == "Test"
    # No input or blank input should raise a ValueError
    try:
        util.option_string(" ")
    except ValueError:
        pass


def test_option_bool() -> None:
    assert util.option_bool("tRuE") == True
    assert util.option_bool("FaLsE") == False
    # No input or blank input should raise a ValueError
    try:
        util.option_bool(" ")
    except ValueError:
        pass


def test_option_flag() -> None:
    assert util.option_flag("") == True
    # Specifying an argument should raise a ValueError
    try:
        util.option_flag("test")
    except ValueError:
        pass


def test_get_files() -> None:
    assert set(util.get_files(PurePath("test_data"), (".toml",))) == {
        Path("test_data/snooty.toml"),
        Path("test_data/bad_project/snooty.toml"),
        Path("test_data/empty_project/snooty.toml"),
        Path("test_data/test_project/snooty.toml"),
        Path("test_data/test_postprocessor/snooty.toml"),
        Path("test_data/merge_conflict/snooty.toml"),
        Path("test_data/test_project_embedding_includes/snooty.toml"),
        Path("test_data/get-preview/snooty.toml"),
        Path("test_data/test_devhub/snooty.toml"),
        Path("test_data/test_intersphinx/snooty.toml"),
        Path("test_data/test_landing/snooty.toml"),
        Path("test_data/test_parser_failure/snooty.toml"),
    }


def test_add_doc_target_ext() -> None:
    # Set up target filenames
    root = Path("root")
    docpath = PurePath("path/to/doc/")
    targets = [
        "dottedfilename",
        "dotted.filename",
        "dotted.file.name",
        "d.o.t.t.e.d.f.i.l.e.n.a.m.e",
    ]

    # What we want the resulting target paths to be
    path_to_file = root.joinpath(docpath.parent)
    resolved_targets = [
        path_to_file.joinpath(Path("dottedfilename.txt")).resolve(),
        path_to_file.joinpath(Path("dotted.filename.txt")).resolve(),
        path_to_file.joinpath(Path("dotted.file.name.txt")).resolve(),
        path_to_file.joinpath(Path("d.o.t.t.e.d.f.i.l.e.n.a.m.e.txt")).resolve(),
    ]

    # Compare resulting target paths from add_doc_target_ext()
    test_results = [
        util.add_doc_target_ext(target, docpath, root) for target in targets
    ]
    assert test_results == resolved_targets


@pytest.mark.skipif(
    sys.platform != "darwin" or "GITHUB_RUN_ID" in os.environ,
    reason="file watching has very different behavior on different systems; it's hard to test",
)
def test_file_watcher() -> None:
    events: List[Tuple[str, str]] = []

    def handle(ev: watchdog.events.FileSystemEvent) -> None:
        if ev.is_directory:
            return
        events.append((ev.event_type, ev.src_path))

    try:
        os.unlink("test_data/__test1")
    except FileNotFoundError:
        pass
    try:
        os.unlink("test_data/__test2")
    except FileNotFoundError:
        pass

    try:
        with util.FileWatcher(handle) as watcher:
            watcher.watch_file(Path("test_data/__test1"))
            watcher.watch_file(Path("test_data/__test1"))
            watcher.watch_file(Path("test_data/__test1"))
            assert len(watcher) == 1
            watcher.end_watch(Path("test_data/__test1"))
            time.sleep(0.1)
            with open("test_data/__test1", "w") as f:
                f.write("f")
                time.sleep(0.1)
            with open("test_data/__test1", "w") as f:
                f.write("f")
                time.sleep(0.1)
            with open("test_data/__test2", "w") as f:
                f.write("f")
                time.sleep(0.1)
            watcher.end_watch(Path("test_data/__test1"))
            assert len(watcher) == 1
            watcher.end_watch(Path("test_data/__test1"))
            assert len(watcher) == 0
            watcher.end_watch(Path("test_data/__test1"))
            assert len(watcher) == 0
            time.sleep(0.1)
            with open("test_data/__test1", "w") as f:
                f.write("f")
                time.sleep(0.1)

        assert events == [
            ("created", "test_data/__test1"),
            ("modified", "test_data/__test1"),
            ("modified", "test_data/__test1"),
        ]
    finally:
        try:
            os.unlink("test_data/__test1")
        except FileNotFoundError:
            pass
        try:
            os.unlink("test_data/__test2")
        except FileNotFoundError:
            pass


def test_make_id() -> None:
    assert util.make_html5_id("bin.weird_example-1") == "bin.weird_example-1"
    assert util.make_html5_id("a test#") == "a-test-"

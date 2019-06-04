import os
import pytest
import sys
import time
import watchdog.events
from pathlib import Path, PurePath
from typing import Callable, List, Tuple, Type
from . import util


def expect_exception(f: Callable[[], None], exception_ty: Type[Exception]) -> None:
    """Assert that the given function f raises the given exception type."""
    try:
        f()
    except exception_ty:
        return
    except Exception as err:
        raise AssertionError(f"Expected {exception_ty.__name__}; got {err}")

    raise AssertionError(f"Expected {exception_ty.__name__} to be raised")


def test_reroot_path() -> None:
    relative, absolute = util.reroot_path(
        PurePath("/foo/bar/baz.rst"), PurePath("/foo/dir/test.txt"), Path("foo")
    )
    assert absolute.is_absolute()
    assert relative == PurePath("foo/bar/baz.rst")
    assert util.reroot_path(
        PurePath("../bar/baz.rst"), PurePath("foo/dir/test.txt"), Path("foo")
    )[0] == PurePath("foo/bar/baz.rst")


def test_get_files() -> None:
    assert set(util.get_files(PurePath("test_data"), (".toml",))) == {
        Path("test_data/snooty.toml"),
        Path("test_data/bad_project/snooty.toml"),
        Path("test_data/empty_project/snooty.toml"),
        Path("test_data/test_project/snooty.toml"),
    }


@pytest.mark.skipif(
    sys.platform != "darwin",
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

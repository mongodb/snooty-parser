import os
import sys
import threading
import time
from pathlib import Path, PurePath, PurePosixPath
from typing import Tuple

import pytest

from . import util


def test_reroot_path() -> None:
    relative, absolute = util.reroot_path(
        PurePosixPath("/test_data/bar/baz.rst"),
        PurePath("/test_data/dir/test.txt"),
        Path("test_data"),
    )
    assert absolute.is_absolute()
    assert relative.parts == ("test_data", "bar", "baz.rst")

    relative, absolute = util.reroot_path(
        PurePosixPath("../bar/baz.rst"),
        PurePath("test_data/dir/test.txt"),
        Path("test_data"),
    )
    assert relative.parts == ("test_data", "bar", "baz.rst")


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
    # The test_data/getfiles path tests how we handle symbolic links. To wit,
    # we ensure that we don't fail on loops; files with the same resolved path
    # only report once; and that we enter symlinks.

    reference_set = {
        Path("test_data/getfiles/files1/1.toml"),
        Path("test_data/getfiles/files1/2.toml"),
        Path("test_data/getfiles/files1/loop1/loop1.toml"),
        Path("test_data/getfiles/files1/loop2/loop2.toml"),
    }

    # Either subdirectory or dup are acceptable, but not both
    assert set(util.get_files(Path("test_data/getfiles/files1"), (".toml",))) in [
        reference_set.union({Path("test_data/getfiles/files1/subdirectory/5.toml")}),
        reference_set.union({Path("test_data/getfiles/files1/dup/5.toml")}),
    ]


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


def test_make_id() -> None:
    assert util.make_html5_id("bin.weird_example-1") == "bin.weird_example-1"
    assert util.make_html5_id("a test#") == "a-test-"


@pytest.mark.skipif(
    "GITHUB_RUN_ID" in os.environ,
    reason="this test is timing-sensitive and doesn't work well in CI",
)
def test_worker() -> None:
    initial_switch_interval = sys.getswitchinterval()

    try:
        sys.setswitchinterval(0.0001)

        def start(event: threading.Event, x: Tuple[int, bool]) -> int:
            """Return x[0] + 1. If x[1] is true, sleep for a long time after the cancellation check.
            This is a pretty fragile timing test."""
            start_time = time.perf_counter()
            while (time.perf_counter() - start_time) <= 0.1:
                if event.is_set():
                    raise util.CancelledException()

            if x[1]:
                time.sleep(100.0)
            return x[0] + 1

        worker = util.WorkerLauncher("worker-test", start)
        assert worker.run_and_wait((1, False)) == 2

        # Test implicit cancellation
        start_time = time.perf_counter()
        worker.run((1, True))
        time.sleep(0.01)
        assert worker.run_and_wait((2, False)) == 3
        assert (time.perf_counter() - start_time) < 0.5

        # Test explicit cancellation
        start_time = time.perf_counter()
        worker.run((1, True))
        worker.cancel()
        worker.run((2, False))
        assert worker.run_and_wait((2, False)) == 3
        assert (time.perf_counter() - start_time) < 0.5

        # Test the case where two threads run the worker
        lock = threading.Lock()
        total = 0

        def run_worker() -> None:
            nonlocal total

            result = worker.run((1, False)).get()
            if isinstance(result, int):
                with lock:
                    total += 1

        threads = []
        for i in range(10):
            thread = threading.Thread(target=run_worker)
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    finally:
        sys.setswitchinterval(initial_switch_interval)

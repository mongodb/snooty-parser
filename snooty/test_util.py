from pathlib import Path, PurePath, PurePosixPath

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

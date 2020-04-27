import builtins
from typing import Any, List
from .types import FileId
from .diagnostics import InvalidLiteralInclude, InvalidURL, UnknownSubstitution
from . import main
import os


def test_backend() -> None:
    messages: List[str] = []

    def test_print(*values: Any, **kwargs: Any) -> None:
        messages.extend(str(val) for val in values)

    backend = main.Backend()
    orig_print = builtins.print
    builtins.print = test_print
    test_diagnostics = [
        InvalidLiteralInclude("an error", 10, 12),
        InvalidURL((10, 0), (12, 30)),
        UnknownSubstitution("a warning", 10),
    ]
    try:
        backend.on_diagnostics(FileId("foo/bar.rst"), test_diagnostics[0:2])
        backend.on_diagnostics(FileId("foo/foo.rst"), test_diagnostics[2:])
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print

    assert messages == [
        "ERROR(foo/bar.rst:10ish): an error",
        "ERROR(foo/bar.rst:10ish): Invalid URL",
        "WARNING(foo/foo.rst:10ish): a warning",
    ]

    # test returning diagnostic messages as JSON
    backend = main.Backend()
    messages.clear()
    builtins.print = test_print
    os.environ["DiagnosticsOutput"] = "JSON"
    try:
        backend.on_diagnostics(FileId("foo/bar.rst"), test_diagnostics[0:2])
        backend.on_diagnostics(FileId("foo/foo.rst"), test_diagnostics[2:])
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print

    for index, item in enumerate(messages):
        diag_dict = eval(item)["diagnostic"]
        assert diag_dict["message"] == test_diagnostics[index].message
        assert diag_dict["start"] == str(test_diagnostics[index].start[0])
        assert diag_dict["severity"] == test_diagnostics[index].severity_string.upper()

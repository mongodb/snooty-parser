import builtins
from typing import Any, List
from .types import FileId
from .diagnostics import InvalidLiteralInclude, InvalidURL, UnknownSubstitution
from . import main
import os
import json


def test_backend() -> None:
    messages: List[str] = []

    def test_print(*values: Any, **kwargs: Any) -> None:
        messages.extend(str(val) for val in values)

    backend = main.Backend()
    orig_print = builtins.print
    builtins.print = test_print
    test_diagnostics = [
        InvalidLiteralInclude("invalid literal include error", 10, 12),
        InvalidURL((10, 0), (12, 30)),
        UnknownSubstitution("unknown substitution warning", 10),
    ]
    try:
        backend.on_diagnostics(FileId("foo/bar.rst"), test_diagnostics[0:2])
        backend.on_diagnostics(FileId("foo/foo.rst"), test_diagnostics[2:])
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print

    assert messages == [
        "ERROR(foo/bar.rst:10ish): invalid literal include error",
        "ERROR(foo/bar.rst:10ish): Invalid URL",
        "WARNING(foo/foo.rst:10ish): unknown substitution warning",
    ]

    # test returning diagnostic messages as JSON
    backend = main.Backend()
    messages.clear()
    builtins.print = test_print
    os.environ["DiagnosticsOutput"] = "JSON"
    try:
        backend.on_diagnostics(
            FileId("foo/bar.rst"),
            test_diagnostics[0:2]
        )
        backend.on_diagnostics(
            FileId("foo/foo.rst"), test_diagnostics[2:]
        )
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print

    assert [json.loads(message) for message in messages] == [
    {'diagnostic': {'severity': 'ERROR', 'start': '10', 'message': test_diagnostics[0].message, 'path': 'foo/bar.rst'}},
    {'diagnostic': {'severity': 'ERROR', 'start': '10', 'message': test_diagnostics[1].message, 'path': 'foo/bar.rst'}},
    {'diagnostic': {'severity': 'WARNING', 'start': '10', 'message': test_diagnostics[2].message, 'path': 'foo/foo.rst'}}
    ]
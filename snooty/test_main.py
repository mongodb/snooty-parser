import builtins
from typing import Any, List
from .types import FileId
from .diagnostics import InvalidLiteralInclude, InvalidURL, UnknownSubstitution
from . import main


def test_backend() -> None:
    messages: List[str] = []

    def test_print(*values: Any, **kwargs: Any) -> None:
        messages.extend(str(val) for val in values)

    backend = main.Backend()
    orig_print = builtins.print
    builtins.print = test_print
    try:
        backend.on_diagnostics(
            FileId("foo/bar.rst"),
            [InvalidLiteralInclude("an error", 10, 12), InvalidURL((10, 0), (12, 30))],
        )
        backend.on_diagnostics(
            FileId("foo/foo.rst"), [UnknownSubstitution("a warning", 10)]
        )
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print
    print(messages)
    assert messages == [
        "ERROR(foo/bar.rst:10ish): an error",
        "ERROR(foo/bar.rst:10ish): Invalid URL",
        "WARNING(foo/foo.rst:10ish): a warning",
    ]

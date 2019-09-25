import builtins
from typing import Any, List
from .types import Diagnostic, FileId
from . import backends


def test_backend() -> None:
    messages: List[str] = []

    def test_print(*values: Any, **kwargs: Any) -> None:
        messages.extend(str(val) for val in values)

    backend = backends.Backend()
    orig_print = builtins.print
    builtins.print = test_print
    try:
        backend.on_diagnostics(
            FileId("foo/bar.rst"),
            [
                Diagnostic.error("an error", 10, 12),
                Diagnostic.error("another error", (10, 0), (12, 30)),
            ],
        )
        backend.on_diagnostics(
            FileId("foo/foo.rst"), [Diagnostic.warning("a warning", 10)]
        )
        assert backend.total_warnings == 3
    finally:
        builtins.print = orig_print

    assert messages == [
        "ERROR(foo/bar.rst:10ish): an error",
        "ERROR(foo/bar.rst:10ish): another error",
        "WARNING(foo/foo.rst:10ish): a warning",
    ]

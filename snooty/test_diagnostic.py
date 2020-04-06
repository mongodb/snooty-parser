from .diagnostics import Diagnostic, UnexpectedIndentation, ParserDiagnostic
import pytest


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

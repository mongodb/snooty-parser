"""Tests for the restricted unpickler (CWE-502 mitigation)."""

import gzip
import os
import pickle

from .safe_unpickler import SafeUnpickler, safe_loads


def test_safe_loads_blocks_os_system() -> None:
    """Verify that __reduce__ gadgets targeting os.system are blocked."""

    class Exploit:
        def __reduce__(self):  # type: ignore[override]
            return (os.system, ("echo SHOULD_NOT_RUN",))

    payload = pickle.dumps(Exploit())
    try:
        safe_loads(payload)
        assert False, "safe_loads should have raised UnpicklingError"
    except pickle.UnpicklingError as exc:
        assert "os.system" in str(exc)
        assert "CWE-502" in str(exc)


def test_safe_loads_blocks_subprocess() -> None:
    """Verify that subprocess-based gadgets are blocked."""
    import subprocess

    class Exploit:
        def __reduce__(self):  # type: ignore[override]
            return (subprocess.call, (["echo", "SHOULD_NOT_RUN"],))

    payload = pickle.dumps(Exploit())
    try:
        safe_loads(payload)
        assert False, "safe_loads should have raised UnpicklingError"
    except pickle.UnpicklingError as exc:
        assert "subprocess" in str(exc)


def test_safe_loads_allows_builtins() -> None:
    """Verify that standard Python builtins can be deserialized."""
    data = {"key": "value", "nums": [1, 2, 3], "flag": True}
    payload = pickle.dumps(data)
    result = safe_loads(payload)
    assert result == data


def test_safe_loads_allows_snooty_types() -> None:
    """Verify that snooty's own types are allowed through the unpickler."""
    from .parse_cache import CacheData

    cache = CacheData(specifier=("0.20.20.dev", "abc", "def"))
    payload = pickle.dumps(cache)
    result = safe_loads(payload)
    assert isinstance(result, CacheData)
    assert result.specifier == ("0.20.20.dev", "abc", "def")


def test_safe_loads_with_gzip() -> None:
    """Verify safe_loads works on gzip-compressed data (the real code path)."""
    data = {"test": True}
    compressed = gzip.compress(pickle.dumps(data))
    result = safe_loads(gzip.decompress(compressed))
    assert result == data

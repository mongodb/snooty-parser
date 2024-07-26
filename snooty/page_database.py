from __future__ import annotations

import pickle
import pickletools
import queue
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from . import parse_cache, util
from .diagnostics import Diagnostic
from .n import FileId
from .page import Page
from .postprocess import Postprocessor, PostprocessorResult
from .target_database import TargetDatabase


@dataclass
class SerializedPageData:
    parsed: Dict[FileId, Tuple[Page, FileId, List[Diagnostic]]]
    orphan_diagnostics: Dict[FileId, List[Diagnostic]]


class PageDatabase:
    """A database of FileId->Page mappings that ensures the postprocessing pipeline
    is run correctly. Raw parsed pages are added, flush() is called, then postprocessed
    pages can be accessed.

    All methods are thread-safe, but data returned should not be mutated by more than one
    thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._parsed: Dict[FileId, Tuple[Page, FileId, List[Diagnostic]]] = {}
        self._orphan_diagnostics: Dict[FileId, List[Diagnostic]] = {}
        self.__cached = PostprocessorResult({}, {}, {}, TargetDatabase())
        self.__changed_pages: Set[FileId] = set()

        def start(
            cancellation_token: threading.Event,
            args: Postprocessor,
        ) -> PostprocessorResult:
            with self._lock:
                if not self.__changed_pages:
                    return self.__cached

                with util.PerformanceLogger.singleton().start("copy"):
                    copied_pages = {}
                    for k in sorted(self._parsed.keys()):
                        v = self._parsed[k]
                        if cancellation_token.is_set():
                            raise util.CancelledException()

                        copied_pages[k] = util.fast_deep_copy(v[0])

            with util.PerformanceLogger.singleton().start("postprocessing"):
                result = args.run(copied_pages, cancellation_token)

            with self._lock:
                self.__cached = result
                self.__changed_pages.clear()

            return result

        self.worker: util.WorkerLauncher[Postprocessor, PostprocessorResult] = (
            util.WorkerLauncher("postprocessor", start)
        )

    def set_orphan_diagnostics(self, key: FileId, value: List[Diagnostic]) -> None:
        """Some diagnostics can't be associated with a parsed Page because of underlying
        problems like invalid YAML syntax. These are orphan diagnostics, and we need
        to track them too."""
        with self._lock:
            self._orphan_diagnostics[key] = value

    def __setitem__(
        self, key: FileId, value: Tuple[Page, FileId, List[Diagnostic]]
    ) -> None:
        """Set a raw parsed page."""
        with self._lock:
            self._parsed[key] = value
            self.__changed_pages.add(key)

    def get(self, key: FileId) -> Optional[Page]:
        try:
            return self[key]
        except KeyError:
            return None

    def __getitem__(self, key: FileId) -> Page:
        """If the postprocessor has been run since modifications were made, fetch a postprocessed page."""
        with self._lock:
            assert not self.__changed_pages
            return self.__cached.pages[key]

    def __contains__(self, key: FileId) -> bool:
        """Check if a given page exists in the parsed set."""
        with self._lock:
            return key in self._parsed

    def __delitem__(self, key: FileId) -> None:
        with self._lock:
            try:
                del self._parsed[key]
            except KeyError:
                pass

            try:
                del self._orphan_diagnostics[key]
            except KeyError:
                pass

            self.__changed_pages.add(key)

    def add_to_cache(self, cache: parse_cache.CacheData) -> None:
        with self._lock:
            for data in self._parsed.values():
                page, fileid, diagnostics = data
                cache.set_page(page, diagnostics)

            for fileid, diagnostics in self._orphan_diagnostics.items():
                cache.set_orphan_diagnostics(fileid, diagnostics)

    def __eq__(self, other: object) -> bool:
        if type(self) != type(other):
            return False

        assert isinstance(other, PageDatabase)

        with self._lock:
            with other._lock:
                return (
                    self._parsed == other._parsed
                    and self._orphan_diagnostics == other._orphan_diagnostics
                )

    def merge_diagnostics(
        self, *others: Dict[FileId, List[Diagnostic]]
    ) -> Dict[FileId, List[Diagnostic]]:
        with self._lock:
            result: Dict[FileId, List[Diagnostic]] = {
                v[1]: list(v[2]) for v in self._parsed.values()
            }

            for key, diagnostics in self._orphan_diagnostics.items():
                if key in result:
                    result[key].extend(diagnostics)
                else:
                    result[key] = list(diagnostics)

        all_keys: Set[FileId] = set()
        for other in others:
            all_keys.update(other.keys())

        for key in all_keys:
            try:
                lst = result[key]
            except KeyError:
                lst = []
                result[key] = lst
            for other in others:
                try:
                    lst.extend(other[key])
                except KeyError:
                    pass

        return result

    def flush(
        self, postprocessor_factory: Callable[[], Postprocessor]
    ) -> queue.Queue[Tuple[Optional[PostprocessorResult], Optional[Exception]]]:
        """Run the postprocessor if and only if any pages have changed, and return postprocessing results."""
        postprocessor = postprocessor_factory()
        return self.worker.run(postprocessor)

    def flush_and_wait(
        self, postprocessor_factory: Callable[[], Postprocessor]
    ) -> PostprocessorResult:
        result, exception = self.flush(postprocessor_factory).get()
        if exception:
            raise exception
        assert result is not None
        return result

    def cancel(self) -> None:
        self.worker.cancel()

    def persist(self) -> bytes:
        with self._lock:
            pickled = pickle.dumps(
                SerializedPageData(self._parsed, self._orphan_diagnostics)
            )

        return pickletools.optimize(pickled)

    @classmethod
    def from_persisted(cls, pickled: bytes) -> PageDatabase:
        unpickled = pickle.loads(pickled)
        assert isinstance(unpickled, SerializedPageData)

        db = PageDatabase()
        db._parsed = unpickled.parsed
        db._orphan_diagnostics = unpickled.orphan_diagnostics
        db.__changed_pages = set(db._parsed.keys())
        return db

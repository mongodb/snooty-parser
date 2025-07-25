from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import enum
import gzip
import hashlib
import io
import logging
import os
import pickle
import queue
import re
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import formatdate
from os.path import exists
from pathlib import Path, PurePath, PurePosixPath
from time import mktime
from typing import (
    Any,
    Callable,
    ClassVar,
    Container,
    Dict,
    Generic,
    Hashable,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    TextIO,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import requests
import tomli

from snooty.diagnostics import Diagnostic, NestedProject, UnexpectedNodeType
from snooty.n import FileId, TocTreeDirectiveEntry

from . import n, tinydocutils

logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_K = TypeVar("_K", bound=Hashable)
_R = TypeVar("_R")
PAT_INVALID_ID_CHARACTERS = re.compile(r"[^\w_\.\-]")
PAT_URI = re.compile(r"^(?P<schema>[a-z]+)://")
SOURCE_FILE_EXTENSIONS = {".txt", ".rst", ".yaml"}
RST_EXTENSIONS = {".txt", ".rst"}
RESERVED_DIRS = {"code-examples"}
EXT_FOR_PAGE = ".txt"
EMPTY_BLAKE2B = hashlib.blake2b(b"").hexdigest()
SNOOTY_TOML = "snooty.toml"
PACKAGE_ROOT_STRING = sys.modules["snooty"].__file__
assert PACKAGE_ROOT_STRING is not None
PACKAGE_ROOT = Path(PACKAGE_ROOT_STRING).resolve().parent
if PACKAGE_ROOT.is_file():
    PACKAGE_ROOT = PACKAGE_ROOT.parent


@dataclass
class FileCacheMapping:
    dependencies: Optional[Dict[FileId, Optional[str]]] = dataclasses.field(
        default_factory=dict
    )

    def __setitem__(self, key: FileId, value: Optional[str]) -> None:
        if self.dependencies is not None:
            self.dependencies[key] = value

    def check_cache(self, handler: Callable[[FileId], str]) -> bool:
        """Check each element of this dependency list against a handler method's expectations."""
        if self.dependencies is not None:
            for fileid, file_hash in self.dependencies.items():
                if handler(fileid) != file_hash:
                    return False

            return True

        return False

    def mark_uncacheable(self) -> None:
        """This file's contents depend on a remote asset that cannot be easily assessed, and
        might as well be re-parsed."""
        self.dependencies = None


def reroot_path(
    filename: PurePosixPath, docpath: PurePath, project_root: Path
) -> Tuple[n.FileId, Path]:
    """Files within a project may refer to other files. Return a canonical path
    relative to the project root."""

    if filename.is_absolute():
        rel_fn = n.FileId(*filename.parts[1:])
    else:
        rel_fn = n.FileId(*docpath.parent.joinpath(filename).parts).collapse_dots()
    return rel_fn, project_root.joinpath(rel_fn).resolve()


def is_relative_to(a: Path, b: Path) -> bool:
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


def get_files(
    root: Path,
    extensions: Container[str],
    must_be_relative_to: Optional[Path] = None,
    diagnostics: Optional[Dict[FileId, List[Diagnostic]]] = None,
) -> Iterator[Path]:
    """Recursively iterate over files underneath the given root, yielding
    only filenames with the given extensions. Symlinks are followed, but
    any given concrete directory is only scanned once.

    By default, directories above the given root in the filesystem are not
    scanned, but this can be overridden with the must_be_relative_to parameter."""
    root_resolved = root.resolve()
    seen: Set[Path] = set()

    if must_be_relative_to is None:
        must_be_relative_to = root_resolved

    for base, dirs, files in os.walk(root, followlinks=True):
        base_resolved = Path(base).resolve()
        if not is_relative_to(base_resolved, must_be_relative_to):
            # Prevent a race between our checking if a symlink is valid, and our
            # actually entering it.
            continue

        # Preserve both the actual resolved path and the directory name
        dirs_set = dict(((base_resolved.joinpath(d).resolve(), d) for d in dirs))

        nested_set = set()
        for d_path, d_name in dirs_set.items():
            dir_snooty_path = d_path / SNOOTY_TOML
            if exists(dir_snooty_path):
                nested_set.add(dir_snooty_path)
                if diagnostics is not None:
                    rel_path = PurePath(os.path.relpath(dir_snooty_path, root))
                    diagnostics[FileId(rel_path)] = [NestedProject(d_name, 0)]
        # Only recurse into directories which are within our prefix
        dirs[:] = [
            d_name
            for d_path, d_name in ((k, v) for k, v in dirs_set.items() if k not in seen)
            if is_relative_to(
                base_resolved.joinpath(d_path).resolve(), must_be_relative_to
            )
            and not d_path / SNOOTY_TOML in nested_set
        ]

        seen.update(dirs_set)

        for name in files:
            ext = os.path.splitext(name)[1]
            if ext not in extensions:
                continue

            path = Path(os.path.join(base, name))
            # Detect and ignore symlinks outside of our jail
            if is_relative_to(
                path.resolve(), must_be_relative_to
            ) and not is_txt_in_reserved_dir(path):
                yield path


def ast_dive(ast: n.Node) -> Iterator[n.Node]:
    """Yield each node in an AST in no particular order."""
    children: List[n.Node] = []
    if isinstance(ast, n.Parent):
        children.extend(ast.children)
    children.extend(getattr(ast, "argument", []))
    yield ast
    for child in children:
        yield from ast_dive(child)


def add_doc_target_ext(target: str, docpath: PurePath, project_root: Path) -> Path:
    """Given the target file of a doc role, add the appropriate extension and return full file path"""
    # Add .txt to end of doc role target path
    target_path = PurePosixPath(target)
    # Adding the current suffix first takes into account dotted targets
    new_suffix = target_path.suffix + ".txt"
    target_path = target_path.with_suffix(new_suffix)

    _, resolved_target_path = reroot_path(target_path, docpath, project_root)
    return resolved_target_path


def option_bool(argument: Optional[str]) -> bool:
    """
    Check for a valid boolean option return it. If no argument is given,
    treat it as a flag, and return True.
    """
    if argument and argument.strip():
        output = tinydocutils.directives.choice(argument, ("true", "false"))
        return output == "true"
    return True


def option_string(argument: Optional[str]) -> Optional[str]:
    """
    Check for a valid string option and return it. If no argument is given,
    raise ``ValueError``.
    """
    if argument and argument.strip():
        return argument
    raise ValueError("Must supply string argument to option")


def option_flag(argument: Optional[str]) -> bool:
    """
    Variant of the docutils flag handler.
    Check for a valid flag option (no argument) and return ``True``.
    (Directive option conversion function.)

    Raise ``ValueError`` if an argument is found.
    """
    if argument and argument.strip():
        raise ValueError('no argument is allowed; "%s" supplied' % argument)
    return True


def split_domain(name: str) -> Tuple[str, str]:
    """Split a fully-qualified reStructuredText directive or role name into
    its (domain, name) pair.

    For example, "mongodb:ref" becomes ("mongodb", "ref"), while simply
    "ref" becomes ("", "ref").
    """
    parts = name.split(":", 1)
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], parts[1]


def split_option_str(argument: str) -> List[str]:
    if argument and argument.strip():
        return re.split(r"\s*,\s*", argument.strip())
    raise ValueError("Must supply string argument to option")


def fast_deep_copy(v: _T) -> _T:
    """Time-efficiently create deep copy of trusted data.
    This implementation currently invokes pickle, so should NOT be called on untrusted objects.
    """
    return cast(_T, pickle.loads(pickle.dumps(v)))


def make_html5_id(orig: str) -> str:
    """Turn an ID into a valid HTML5 element ID."""
    clean_id = PAT_INVALID_ID_CHARACTERS.sub("-", orig)
    if not clean_id:
        clean_id = "unnamed"
    return clean_id


class PerformanceLogger:
    _singleton: Optional["PerformanceLogger"] = None

    def __init__(self) -> None:
        self._times: Dict[str, List[float]] = defaultdict(list)

    @contextmanager
    def start(self, name: str) -> Iterator[None]:
        start_time = time.perf_counter()
        try:
            yield None
        finally:
            self._times[name].append(time.perf_counter() - start_time)

    def times(self) -> Dict[str, float]:
        return {k: min(v) for k, v in self._times.items()}

    def print(self, file: TextIO = sys.stdout) -> None:
        times = self.times()
        title_column_width = max(len(x) for x in times.keys())
        for name, entry_time in times.items():
            print(f"{name:{title_column_width}} {entry_time:.2f}", file=file)

    @classmethod
    def singleton(cls) -> "PerformanceLogger":
        assert cls._singleton is not None
        return cls._singleton


PerformanceLogger._singleton = PerformanceLogger()


class HTTPCache:
    _singleton: ClassVar[Optional["HTTPCache"]] = None
    DEFAULT_CACHE_DIR: ClassVar[Path] = Path.home().joinpath(".cache", "snooty")

    @classmethod
    def initialize(cls, caching: bool = True) -> None:
        cls._singleton = cls(cls.DEFAULT_CACHE_DIR if caching else None)

    @classmethod
    def singleton(cls) -> "HTTPCache":
        if cls._singleton is None:
            cls._singleton = cls(cls.DEFAULT_CACHE_DIR)

        return cls._singleton

    def __init__(self, cache_dir: Optional[Path]) -> None:
        self.cache_dir = cache_dir

    def get(
        self, url: str, cache_interval: Optional[datetime.timedelta] = None
    ) -> bytes:
        logger.debug(
            f"Fetching: {url} from cache_dir {self.cache_dir.as_posix() if self.cache_dir else '<no-cache>'}"
        )

        cache_interval = (
            datetime.timedelta(hours=1) if cache_interval is None else cache_interval
        )

        url_netloc = urllib.parse.urlparse(url).netloc
        is_raw_gh_content_url = url_netloc == "raw.githubusercontent.com"
        target_url = (
            f"https://populate-data-extension.netlify.app/.netlify/functions/fetch-url?url={url}"
            if is_raw_gh_content_url
            else url
        )

        if self.cache_dir is None:
            res = requests.get(target_url)
            res.raise_for_status()
            return res.content

        # Make our user's cache directory if it doesn't exist
        filename = urllib.parse.quote(target_url, safe="")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        inventory_path = self.cache_dir.joinpath(filename)

        # Only re-request if more than an hour old
        request_headers: Dict[str, str] = {}
        mtime: Optional[datetime.datetime] = None
        try:
            mtime = datetime.datetime.fromtimestamp(inventory_path.stat().st_mtime)
        except FileNotFoundError:
            pass

        if mtime is not None:
            if (datetime.datetime.now() - mtime) < cache_interval:
                return inventory_path.read_bytes()

            request_headers["If-Modified-Since"] = formatdate(
                mktime(mtime.timetuple()), usegmt=True
            )

        res = requests.get(target_url, headers=request_headers)

        res.raise_for_status()
        if res.status_code == 304:
            return inventory_path.read_bytes()

        atomic_write(inventory_path, res.content, self.cache_dir)

        return res.content


def atomic_write(path: Path, data: bytes, temp_dir: Path) -> None:
    """Atomically write a file."""
    try:
        tempf = tempfile.NamedTemporaryFile(dir=temp_dir)
        tempf.write(data)
        os.replace(tempf.name, path)
    finally:
        try:
            tempf.close()
        except FileNotFoundError:
            pass


class CancelledException(Exception):
    pass


class WorkerLauncher(Generic[_T, _R]):
    """Concurrency abstraction that launches a thread with a specific callable, passing in a
    cancellation Event and a user-supplied argument. The callable's return value is fed into
    a results Queue.

    The input argument is cloned using pickle before launch, and so does not need to be protected.

    If the run() method is called while the thread is ongoing, it is cancelled (and blocks until
    the worker raises WorkerCanceled) and restarted.

    This class's methods are thread-safe"""

    def __init__(
        self,
        name: str,
        target: Callable[[threading.Event, _T], _R],
    ) -> None:
        self.name = name
        self.target = target

        self._lock = threading.Lock()
        self.__thread: Optional[threading.Thread] = None
        self.__cancel = threading.Event()

    def run(self, arg: _T) -> queue.Queue[Tuple[Optional[_R], Optional[Exception]]]:
        """Cancel any current thread of execution; block until it is cancelled; and re-launch the worker."""
        self.cancel()

        result_queue: queue.Queue[Tuple[Optional[_R], Optional[Exception]]] = (
            queue.Queue(1)
        )

        def inner() -> None:
            try:
                result = self.target(self.__cancel, arg)

                # This is only going to happen if the callable never checks the cancelation Event
                if self.__cancel.is_set():
                    raise CancelledException()

                result_queue.put((result, None))
            except Exception as exception:
                result_queue.put((None, exception))

        thread = threading.Thread(name=self.name, target=inner, daemon=True)
        with self._lock:
            self.__thread = thread
        thread.start()

        return result_queue

    def run_and_wait(self, arg: _T) -> _R:
        result, exception = self.run(arg).get()
        if exception:
            raise exception

        return cast(_R, result)

    def cancel(self) -> None:
        """Instruct the worker to raise WorkerCanceled and abort execution."""
        with self._lock:
            if self.__thread and self.__thread.is_alive():
                self.__cancel.set()
                self.__thread.join()

        self.__cancel.clear()


class NodeDeserializer:
    node_types: List[Type[n.Node]] = [
        n.BlockSubstitutionReference,
        n.Code,
        n.Comment,
        n.DefinitionList,
        n.DefinitionListItem,
        n.Directive,
        n.DirectiveArgument,
        n.Emphasis,
        n.Field,
        n.FieldList,
        n.Footnote,
        n.FootnoteReference,
        n.Heading,
        n.InlineTarget,
        n.Label,
        n.Line,
        n.LineBlock,
        n.ListNode,
        n.ListNodeItem,
        n.Literal,
        n.NamedReference,
        n.Paragraph,
        n.Reference,
        n.RefRole,
        n.Role,
        n.Root,
        n.Section,
        n.Strong,
        n.SubstitutionDefinition,
        n.SubstitutionReference,
        n.Table,
        n.Target,
        n.TargetIdentifier,
        n.Text,
        n.Transition,
    ]
    node_classes: Dict[str, Type[n.Node]] = {
        node_class.type: node_class for node_class in node_types
    }

    @classmethod
    def deserialize(
        cls,
        node: n.SerializedNode,
        node_type: Type[n._N],
        diagnostics: List[Diagnostic],
    ) -> n._N:
        filtered_fields: Dict[str, Any] = {}

        for field in dataclasses.fields(node_type):
            # We don't need "span" to be present here since we need to hardcode it as the first argument of Node
            if field.name == "span":
                continue

            placeholder_span = (0,)
            node_value = node.get(field.name)
            has_nested_children = field.name == "children" and issubclass(
                node_type, n.Parent
            )
            has_nested_argument = field.name == "argument" and issubclass(
                node_type, n.Directive
            )
            if isinstance(node_value, List) and (
                has_nested_children or has_nested_argument
            ):
                deserialized_children: List[n.Node] = []

                for child in node_value:

                    if not isinstance(child, dict):
                        continue

                    child_type: str = child.get("type", "")
                    child_node_type = cls.node_classes.get(child_type)

                    if child_node_type:
                        if (
                            child_node_type == n.Directive
                            and child.get("name") == "toctree"
                        ):
                            child_node_type = n.TocTreeDirective

                        deserialized_children.append(
                            cls.deserialize(child, child_node_type, diagnostics)
                        )
                    else:
                        diagnostics.append(UnexpectedNodeType(child_type, None, 0))
                        continue

                filtered_fields[field.name] = deserialized_children
            elif field.type == FileId and isinstance(node_value, str):
                filtered_fields[field.name] = field.type(node_value)
            elif field.name == "entries":
                deserialized_entries: List[n.TocTreeDirectiveEntry] = []

                if isinstance(node_value, List):
                    for entry in node_value:
                        if not isinstance(entry, dict):
                            continue

                        title = entry.get("title")
                        slug = entry.get("slug")

                        if not title or not slug:
                            continue

                        entryNode = TocTreeDirectiveEntry(title, None, slug, None)
                        deserialized_entries.append(entryNode)

                    filtered_fields[field.name] = deserialized_entries
            else:
                # Ideally, we validate that the data types of the fields match the data types of the JSON node,
                # but that requires a more verbose and time-consuming process. For now, we assume data types are correct.
                filtered_fields[field.name] = node_value

        deserialized_node = node_type(placeholder_span, **filtered_fields)

        # Finalize any needed node types and their fields
        if isinstance(deserialized_node, n.Heading) and not deserialized_node.id:
            deserialized_node.id = make_html5_id(deserialized_node.get_text().lower())

        return deserialized_node


def bundle(
    filename: PurePath, members: Iterable[Tuple[str, Union[str, bytes]]]
) -> bytes:
    if filename.suffixes[-2:] != [".tar", ".gz"] and filename.suffixes[-1] != ".tar":
        raise ValueError(f"Unknown bundling format: {filename.as_posix()}")

    output_file = io.BytesIO()
    with tarfile.open(None, "w", output_file, format=tarfile.PAX_FORMAT) as tf:
        # Sort the members list by filename to ensure repeatable bundles
        sorted_members = sorted(members, key=lambda x: x[0])

        for member_name, member_data in sorted_members:
            if isinstance(member_data, str):
                member_data = bytes(member_data, "utf-8")
            member_file = io.BytesIO(member_data)
            tar_info = tarfile.TarInfo(name=member_name)
            tar_info.size = len(member_data)
            tar_info.mtime = 0
            tar_info.mode = 0o644
            tf.addfile(tar_info, member_file)

    result = output_file.getvalue()

    # We want repeatable bundles, but the tarfile interface doesn't allow us to override its gzip timestamp.
    # So we have to do this separately and waste a bunch of extra RAM. Oh well. There are other ways to feed
    # this kitty, but this function isn't meant to be used for large amounts of data, so this is fine.
    if filename.suffix == ".gz":
        result = gzip.compress(result, mtime=0.0)

    return result


class QueueDict(Generic[_K, _T]):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._data: Dict[_K, _T] = {}

    def put(
        self, key: _K, value: _T, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        with self._lock:
            if key in self._data:
                self._data[key] = value
                return

            self._data[key] = value
            self._not_empty.notify()

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Tuple[_K, _T]:
        with self._not_empty:
            while not len(self._data):
                self._not_empty.wait()

            result = next(iter(self._data.items()))
            del self._data[result[0]]

        return result


def damerau_levenshtein_distance(a: str, b: str) -> int:
    """Derived from Wikipedia, the best possible source for an algorithm:
    https://en.wikipedia.org/w/index.php?title=Damerau%E2%80%93Levenshtein_distance&oldid=1050388400#Distance_with_adjacent_transpositions
    """
    # Strings are 1-indexed, and d is -1-indexed.

    da = {ch: 0 for ch in set(a).union(b)}

    width = len(a) + 2
    height = len(b) + 2
    d = [0] * width * height

    def matrix_set(x: int, y: int, value: int) -> None:
        d[(width * (y + 1)) + (x + 1)] = value

    def matrix_get(x: int, y: int) -> int:
        return d[(width * (y + 1)) + (x + 1)]

    maxdist = len(a) + len(b)
    matrix_set(-1, -1, maxdist)

    for i in range(0, len(a) + 1):
        matrix_set(i, -1, maxdist)
        matrix_set(i, 0, i)

    for j in range(0, len(b) + 1):
        matrix_set(-1, j, maxdist)
        matrix_set(0, j, j)

    for i in range(1, len(a) + 1):
        db = 0
        for j in range(1, len(b) + 1):
            k = da[b[j - 1]]
            l = db
            if a[i - 1] == b[j - 1]:
                cost = 0
                db = j
            else:
                cost = 1
            matrix_set(
                i,
                j,
                min(
                    matrix_get(i - 1, j - 1) + cost,  # substitution
                    matrix_get(i, j - 1) + 1,  # insertion
                    matrix_get(i - 1, j) + 1,  # deletion
                    matrix_get(k - 1, l - 1)
                    + (i - k - 1)
                    + 1
                    + (j - l - 1),  # transposition
                ),
            )
        da[a[i - 1]] = i

    return matrix_get(len(a), len(b))


def lines_contain(haystack: Iterable[str], needle: str) -> Iterator[int]:
    """Check if a sequence of lines contains a specific needle, where the needle
    is surrounded only by non-word characters. If there's a match, yield the index
    of the line where the match succeeded. Repeat for each line."""
    pat = re.compile(rf"^\W*{re.escape(needle)}\W*$")
    yield from (idx for idx, line in enumerate(haystack) if pat.match(line))


def structural_hash(obj: object) -> bytes:
    """Compute a hash of a nested set of dataclasses and primitive types. We form a kind of simple
    serialization format in the process -- it's just here to prevent ambiguity. Structural hashes
    are subject to change and are not stable across releases.

    Fields in dataclasses with metadata value of "nohash" are skipped."""
    # blake2b160 should be more than enough
    hasher = hashlib.blake2b(digest_size=20)
    if isinstance(obj, (int, str, float, PurePath)):
        hasher.update(bytes("P" + str(obj), "utf-8"))
    elif dataclasses.is_dataclass(obj):
        fields = dataclasses.fields(obj)
        hasher.update(bytes(f"O{len(fields)}\x20", "utf-8"))
        for field in sorted(fields, key=lambda x: x.name):
            if not field.metadata.get("nohash"):
                hasher.update(bytes(f"F{len(field.name)}\x20{field.name}", "utf-8"))
                hasher.update(structural_hash(getattr(obj, field.name)))
    elif isinstance(obj, (collections.abc.Sequence, collections.abc.Set)):
        hasher.update(bytes(f"L{len(obj)}\x20", "utf-8"))
        for member in obj:
            child_hash = structural_hash(member)
            hasher.update(bytes(f"E{len(child_hash)}\x20", "utf-8"))
            hasher.update(child_hash)
    elif isinstance(obj, collections.abc.Mapping):
        hasher.update(bytes(f"M{len(obj)}\x20", "utf-8"))
        for key, member in obj.items():
            child_hash = structural_hash(member)
            hasher.update(
                bytes(f"E{len(key)}\x20{key}\x20{len(child_hash)}\x20", "utf-8")
            )
            hasher.update(child_hash)
    elif isinstance(obj, enum.Enum):
        hasher.update(bytes(str(obj), "utf-8"))
    elif obj is None:
        hasher.update(b"N")
    else:
        raise TypeError("Unhashable type", obj)

    return hasher.digest()


class TOMLDecodeErrorWithSourceInfo(tomli.TOMLDecodeError):
    def __init__(self, message: str, lineno: int) -> None:
        super().__init__(message)
        self.lineno = lineno


def parse_toml_and_add_line_info(text: str) -> Dict[str, Any]:
    """The normal toml parsing libraries in Python do not report line number in any
    structured way upon TOMLDecodeError.

    Wrap tomli.loads() and parse out source information from any raised
    TOMLDecodeError so that line numbers can be accessed via the exception's
    lineno attribute."""
    try:
        return tomli.loads(text)
    except tomli.TOMLDecodeError as err:
        message = str(err)
        match = re.search(r"\(at line ([0-9]+), column ([0-9]+)\)", message)
        if match is not None:
            raise TOMLDecodeErrorWithSourceInfo(
                message, int(match.groups()[0])
            ) from err

        if message.endswith("at end of document)"):
            # Report the line number of the final line in the file, 1-indexed
            raise TOMLDecodeErrorWithSourceInfo(message, text.count("\n") + 1) from err

        raise err


def is_txt_in_reserved_dir(path: Path) -> bool:
    if path.suffix != ".txt":
        return False

    # Exclude checking files that have a reserved dir name AS the filename
    path_parts = path.parts[:-1]
    for part in path_parts:
        if part in RESERVED_DIRS:
            return True

    return False

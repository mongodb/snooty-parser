import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Set

from . import n
from .diagnostics import Diagnostic
from .n import FileId
from .target_database import EmptyProjectInterface, ProjectInterface
from .types import Facet, StaticAsset
from .util import FileCacheMapping


class PendingTask:
    """A thunk which will be executed in the main process after the full tree is
    constructed. This should primarily be used to execute tasks which may need
    to mutate state from the main process (e.g. caches or dependency graphs)."""

    def __init__(self, node: n.Node) -> None:
        self.node = node

    def __call__(
        self, diagnostics: List[Diagnostic], project: ProjectInterface
    ) -> None:
        """Perform an action in the main process once the tree has been built."""
        pass


@dataclass
class Page:
    fileid: FileId
    output_filename: str
    source: str
    ast: n.Root
    blake2b: str
    dependencies: FileCacheMapping = field(default_factory=FileCacheMapping)
    static_assets: Set[StaticAsset] = field(default_factory=set)
    pending_tasks: List[PendingTask] = field(default_factory=list)
    facets: Optional[List[Facet]] = field(default=None)
    category: Optional[str] = field(default=None)

    @classmethod
    def create(
        self,
        fileid: FileId,
        output_filename: Optional[str],
        source: str,
        ast: Optional[n.Root] = None,
    ) -> "Page":
        if output_filename is None:
            output_filename = fileid.name

        if ast is None:
            ast = n.Root((0,), [], fileid, {})

        return Page(
            fileid,
            output_filename,
            source,
            ast,
            hashlib.blake2b(bytes(source, "utf-8")).hexdigest(),
        )

    def fake_full_fileid(self) -> FileId:
        """Return a fictitious path (hopefully) uniquely identifying this output artifact."""
        if self.category:
            if self.category == "ast":
                return FileId(self.output_filename)

            # Giza wrote out yaml file artifacts under a directory. e.g. steps-foo.yaml becomes
            # steps/foo.rst
            return self.fileid.parent.joinpath(
                FileId(self.category), self.output_filename
            )
        return self.fileid

    def finish(
        self, diagnostics: List[Diagnostic], project: Optional[ProjectInterface] = None
    ) -> None:
        """Finish all pending tasks for this page. This should be run in the main process."""
        for task in self.pending_tasks:
            task(
                diagnostics, project if project is not None else EmptyProjectInterface()
            )

        self.pending_tasks.clear()

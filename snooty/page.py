from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import List, Optional, Set

from . import n
from .diagnostics import CannotOpenFile, Diagnostic
from .n import FileId
from .target_database import EmptyProjectInterface, ProjectInterface
from .types import StaticAsset


class PendingFigure:
    """Add an image's checksum."""

    def __init__(self, node: n.Directive, asset: StaticAsset) -> None:
        self.node: n.Directive = node
        self.asset = asset

    def __call__(
        self, diagnostics: List[Diagnostic], project: ProjectInterface, page: "Page"
    ) -> None:
        """Compute this figure's checksum and store it in our node."""
        cache = project.expensive_operation_cache

        # Use the cached checksum if possible. Note that this does not currently
        # update the underlying asset: if the asset is used by the current backend,
        # the image will still have to be read.
        if self.node.options is None:
            self.node.options = {}
        options = self.node.options
        entry = cache[(self.asset.fileid, 0)]
        if entry is not None:
            assert isinstance(entry, str)
            options["checksum"] = entry
            return

        try:
            checksum = self.asset.get_checksum()
            options["checksum"] = checksum
            cache[(self.asset.fileid, 0)] = checksum
        except OSError as err:
            diagnostics.append(
                CannotOpenFile(self.asset.path, err.strerror, self.node.start[0])
            )
            page.static_assets.remove(self.asset)


@dataclass
class Page:
    source_path: Path
    output_filename: str
    source: str
    ast: n.Root
    static_assets: Set[StaticAsset] = field(default_factory=set)
    pending_tasks: List[PendingFigure] = field(default_factory=list)
    category: Optional[str] = None

    @classmethod
    def create(
        self,
        source_path: Path,
        output_filename: Optional[str],
        source: str,
        ast: Optional[n.Root] = None,
    ) -> "Page":
        if output_filename is None:
            output_filename = source_path.name

        if ast is None:
            ast = n.Root((0,), [], FileId(source_path), {})

        return Page(source_path, output_filename, source, ast)

    def fake_full_path(self) -> PurePath:
        """Return a fictitious path (hopefully) uniquely identifying this output artifact."""
        if self.category:
            # Giza wrote out yaml file artifacts under a directory. e.g. steps-foo.yaml becomes
            # steps/foo.rst
            return self.source_path.parent.joinpath(
                PurePath(self.category), self.output_filename
            )
        return self.source_path

    def finish(
        self, diagnostics: List[Diagnostic], project: Optional[ProjectInterface] = None
    ) -> None:
        """Finish all pending tasks for this page. This should be run in the main process."""
        for task in self.pending_tasks:
            task(
                diagnostics,
                project if project is not None else EmptyProjectInterface(),
                self,
            )

        self.pending_tasks.clear()

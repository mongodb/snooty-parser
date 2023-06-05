from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Optional, Set

from . import n
from .n import FileId
from .types import StaticAsset


@dataclass
class Page:
    source_path: Path
    output_filename: str
    source: str
    ast: n.Root
    static_assets: Set[StaticAsset] = field(default_factory=set)
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

from dataclasses import dataclass
from typing import Dict, List, Optional
from ..flutter import checked
from ..types import SerializableType

"""Models for giza's published_branches files.

These files define which branches should be built for the site, and allow for labeling branches
as published, active, stable, or upcoming. They also populate data for the version selection dropdown
on the docs front-end.
"""


@checked
@dataclass
class PublishedBranchesVersion:
    published: List[str]
    active: List[str]
    stable: Optional[str]
    upcoming: Optional[str]

    def serialize(self) -> SerializableType:
        node: Dict[str, SerializableType] = {}

        if self.published:
            node["published"] = self.published

        if self.active:
            node["active"] = self.active

        if self.stable:
            node["stable"] = self.stable

        if self.upcoming:
            node["upcoming"] = self.upcoming

        return node


@checked
@dataclass
class PublishedBranchesGitBranches:
    manual: Optional[str]
    published: List[str]

    def serialize(self) -> SerializableType:
        node: Dict[str, SerializableType] = {}

        if self.manual:
            node["manual"] = self.manual

        if self.published:
            node["published"] = self.published

        return node


@checked
@dataclass
class PublishedBranchesGit:
    branches: PublishedBranchesGitBranches

    def serialize(self) -> SerializableType:
        branches_node: Dict[str, SerializableType] = {}

        branches_node["branches"] = self.branches.serialize()

        return branches_node


@checked
@dataclass
class PublishedBranches:
    version: PublishedBranchesVersion
    git: PublishedBranchesGit

    def serialize(self) -> SerializableType:
        published_branches_node: Dict[str, SerializableType] = {}

        published_branches_node["version"] = self.version.serialize()
        published_branches_node["git"] = self.git.serialize()

        return published_branches_node

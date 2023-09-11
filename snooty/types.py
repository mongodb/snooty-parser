import hashlib
import logging
import os.path
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import (
    Any,
    ClassVar,
    Container,
    Dict,
    Iterable,
    List,
    Match,
    MutableSequence,
    Optional,
    Tuple,
    Union,
)

import tomli
from typing_extensions import Protocol

from . import n, specparser, taxonomy, util
from .diagnostics import (
    CannotOpenFile,
    ConstantNotDeclared,
    Diagnostic,
    GitMergeConflictArtifactFound,
    MissingFacet,
    UnmarshallingError,
)
from .flutter import LoadError, check_type, checked
from .n import FileId, SerializableType

FileSource = Union[Path, str]
PAT_VARIABLE = re.compile(r"{\+([\w-]+)\+}")
PAT_GIT_MARKER = re.compile(r"^<<<<<<< .*?^=======\n.*?^>>>>>>>", re.M | re.S)
BuildIdentifierSet = Dict[str, Optional[str]]
logger = logging.getLogger(__name__)


class EmbeddedRstParser(Protocol):
    def parse_block(self, text: str, lineno: int) -> MutableSequence[n.Node]:
        ...

    def parse_inline(self, text: str, lineno: int) -> MutableSequence[n.InlineNode]:
        ...


def normalize_target(target: str) -> str:
    """Normalize targets to allow easy matching against the target
    database: normalize whitespace."""
    return re.sub(r"\s+", " ", target)


class SnootyError(Exception):
    pass


@dataclass
class StaticAsset:
    # "key" must *exactly* match an identifier with which this asset is referred to in source text.
    key: str

    fileid: FileId
    path: Path
    upload: bool
    _checksum: Optional[str]
    _data: Optional[bytes]

    def __hash__(self) -> int:
        return hash(self.fileid)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StaticAsset) and self.fileid == other.fileid

    def get_checksum(self) -> str:
        self.__load()
        assert self._checksum is not None
        return self._checksum

    def can_upload(self) -> bool:
        """Return True iff the file exists and it's of a file type which should be uploaded
        (e.g. an image)."""
        try:
            self.__load()
        except OSError:
            return False

        return self.upload

    @property
    def data(self) -> bytes:
        self.__load()
        assert self._data is not None
        return self._data

    @classmethod
    def load(
        cls, key: str, fileid: FileId, path: Path, upload: bool = False
    ) -> "StaticAsset":
        return cls(key, fileid, path, upload, None, None)

    def __load(self) -> None:
        if self._data is None:
            self._data = self.path.read_bytes()
            self._checksum = hashlib.blake2b(self._data, digest_size=32).hexdigest()


@dataclass
class ParsedBannerConfig:
    targets: List[str]
    node: n.Directive


@dataclass
class Facet:
    category: str
    value: str
    sub_facets: Optional[List["Facet"]] = None

    def __lt__(self, other: "Facet") -> bool:
        return self.category < other.category

    def __gt__(self, other: "Facet") -> bool:
        return self.category > other.category

    def __le__(self, other: "Facet") -> bool:
        return self.category <= other.category

    def __ge__(self, other: "Facet") -> bool:
        return self.category >= other.category

    def serialize(self) -> n.SerializedNode:
        result: n.SerializedNode = {
            "category": self.category,
            "value": self.value,
            "sub_facets": None,
        }
        if self.sub_facets:
            result["sub_facets"] = [
                sub_facet.serialize() for sub_facet in self.sub_facets
            ]
        return result


@checked
@dataclass
class BannerConfig:
    targets: List[str]
    variant: str = field(default="info")
    value: str = field(default="")


@checked
@dataclass
class ManPageConfig:
    file: str
    title: str
    section: int


@checked
@dataclass
class BundleConfig:
    manpages: Optional[str] = field(default=None)


@checked
@dataclass
class AssociatedProduct:
    name: str
    versions: Optional[List[str]] = field(default=None)

    def serialize(self) -> SerializableType:
        return {"name": self.name, "versions": self.versions}


@checked
@dataclass
class ProjectConfig:
    root: Path = field(metadata={"nohash": True})
    name: str
    fail_on_diagnostics: bool = field(default=False)
    default_domain: Optional[str] = field(default=None)
    title: str = field(default="untitled")
    eol: bool = field(default=False)
    canonical: Optional[str] = field(default=None)
    source: str = field(default="source")
    banners: List[BannerConfig] = field(default_factory=list)
    constants: Dict[str, Union[str, int, float]] = field(default_factory=dict)
    deprecated_versions: Optional[Dict[str, List[str]]] = field(default=None)
    intersphinx: List[str] = field(default_factory=list)
    sharedinclude_root: Optional[str] = field(default=None)
    substitutions: Dict[str, str] = field(default_factory=dict)
    toc_landing_pages: List[str] = field(default_factory=list)
    page_groups: Dict[str, List[str]] = field(default_factory=dict)
    manpages: Dict[str, ManPageConfig] = field(default_factory=dict)
    bundle: BundleConfig = field(default_factory=BundleConfig)
    data: Dict[str, object] = field(default_factory=dict)
    associated_products: List[AssociatedProduct] = field(default_factory=list)

    # banner_nodes contains parsed banner nodes with target data
    banner_nodes: List[ParsedBannerConfig] = field(
        default_factory=list, metadata={"nohash": True}
    )

    # substitution_nodes contains a parsed representation of the substitutions member, and is populated on Project initialization.
    substitution_nodes: Dict[str, List[n.InlineNode]] = field(
        default_factory=dict, metadata={"nohash": True}
    )

    CONFIG_FILEID: ClassVar[FileId] = FileId("../snooty.toml")

    @property
    def source_path(self) -> Path:
        return self.root.joinpath(self.source)

    @property
    def config_path(self) -> Path:
        return self.root.joinpath("snooty.toml")

    def get_fileid(self, path: PurePath) -> FileId:
        # Getting passed a FileId would always indicate a type error, but unfortunately FileId inherits from PurePath.
        assert not isinstance(path, n.FileId)

        result = PurePath(os.path.relpath(path, self.source_path))
        # Ensure that we transform any Windows-style paths into a Posix-style FileId
        return FileId(*result.parts)

    @classmethod
    def open(cls, root: Path) -> Tuple["ProjectConfig", List[Diagnostic]]:
        path = root
        diagnostics: List[Diagnostic] = []
        while path.parent != path:
            try:
                with path.joinpath("snooty.toml").open("rb") as f:
                    data = tomli.load(f)
                    data["root"] = path
                    result, parsed_diagnostics = check_type(
                        ProjectConfig, data
                    ).render_constants()

                    parsed_diagnostics.extend(cls.validate_data(result.data))

                    return result, parsed_diagnostics
            except FileNotFoundError:
                pass
            except LoadError as err:
                diagnostics.append(UnmarshallingError(str(err), 0))

            path = path.parent

        return cls(root, name="unnamed"), diagnostics

    def render_constants(self) -> Tuple["ProjectConfig", List[Diagnostic]]:
        if not self.constants:
            return self, []
        constants: Dict[str, Union[str, int, float]] = {}
        all_diagnostics: List[Diagnostic] = []
        for k, v in self.constants.items():
            result, diagnostics = self._substitute(str(v), constants)
            all_diagnostics.extend(diagnostics)
            constants[k] = result

        self.constants = constants
        return self, all_diagnostics

    def read(
        self, path: Union[n.FileId, Path], text: Optional[str] = None
    ) -> Tuple[str, List[Diagnostic]]:
        if text is None:
            if isinstance(path, n.FileId):
                path = self.source_path / path

            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as err:
                error_line = path.read_bytes()[: err.start].count(b"\n")
                return ("", [CannotOpenFile(None, str(err), error_line)])

        text, diagnostics = self.substitute(text)
        match_found = PAT_GIT_MARKER.finditer(text)

        if match_found:
            for match in match_found:
                lineno = text.count("\n", 0, match.start())
                diagnostics.append(GitMergeConflictArtifactFound(None, lineno))

        return (text, diagnostics)

    def get_full_path(self, fileid: FileId) -> Path:
        return self.source_path.joinpath(fileid)

    def get_files_by_extension(self, extensions: Container[str]) -> Iterable[FileId]:
        yield from (
            self.get_fileid(path)
            for path in util.get_files(self.source_path, (".yaml",), self.root)
        )

    @staticmethod
    def validate_facets(
        facets: Optional[List[Facet]],
        category_value_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> Tuple[Optional[List[Facet]], List[Diagnostic]]:
        diagnostics: List[Diagnostic] = []
        validated_facets: List[Facet] = []

        if not facets:
            return None, diagnostics

        if category_value_pairs is None:
            category_value_pairs = []

        for facet in facets:
            pair = (facet.category, facet.value)
            curr_value_pairs = [pair] + category_value_pairs
            try:
                taxonomy.TaxonomySpec.validate_key_value_pairs(curr_value_pairs)

                (
                    validated_sub_facets,
                    validation_diagnostics,
                ) = ProjectConfig.validate_facets(facet.sub_facets, curr_value_pairs)

                validated_facet = Facet(
                    category=facet.category,
                    value=facet.value,
                    sub_facets=validated_sub_facets,
                )

                validated_facets.append(validated_facet)
                diagnostics += validation_diagnostics
            except KeyError:
                diagnostics.append(MissingFacet(f"{facet.category}:{facet.value}", 0))

        # we don't want to return an empty list if
        # there are no valid facets. This prevents us from having
        # a sub_facets property with an empty list as a value
        if len(validated_facets) == 0:
            return None, diagnostics

        return validated_facets, diagnostics

    @staticmethod
    def parse_facet(unparsed_facet: Dict[str, Any]) -> Facet:
        try:
            facet = Facet(**unparsed_facet)
            if facet.sub_facets:
                facet.sub_facets = [
                    ProjectConfig.parse_facet(f) for f in unparsed_facet["sub_facets"]
                ]
        except Exception as e:
            logger.error(e)

        return facet

    @staticmethod
    def load_facets_from_file(
        path: Path,
    ) -> Tuple[List[Facet], List[Diagnostic]]:
        diagnostics: List[Diagnostic] = []
        validated_facets: List[Facet] = []

        try:
            with path.open("rb") as f:
                data = tomli.load(f)["facets"]
                facets = [ProjectConfig.parse_facet(facet) for facet in data]
                (
                    validated_facets_result,
                    validation_diagnostics,
                ) = ProjectConfig.validate_facets(facets)
                validated_facets = validated_facets_result or []
                diagnostics += validation_diagnostics
        except FileNotFoundError as err:
            diagnostics.append(CannotOpenFile(path, str(err), 0))
        except LoadError as err:
            diagnostics.append(UnmarshallingError(str(err), 0))
        return validated_facets, diagnostics

    @staticmethod
    def merge_facets(
        parent_facets: List[Facet], child_facets: List[Facet]
    ) -> List[Facet]:
        """
        This method merges two facet lists together.
        The child facet list will override categories of
        the parent facet list if that categories exists in both lists.
        Otherwise, if the parent facet list contains categories that do not
        exist in the child, they will be included in the merged result

        e.g.
            parent_facets = [{ category: "target_product", value: "drivers" }, { category: "programming_language", value: "scala" }]
            child_facets = [{ category: "target_product", value: "atlas" }]

            merged_facets = [{ category: "target_product", value: "atlas" }, { category: "programming_language", value: "scala" }]
        """
        merged_facets: List[Facet] = child_facets

        child_categories = set([f.category for f in child_facets])
        parent_categories = set([f.category for f in parent_facets])

        extra_categories = parent_categories - child_categories

        for facet in parent_facets:
            if facet.category in extra_categories:
                merged_facets.append(facet)

        return merged_facets

    @staticmethod
    def _substitute(
        source: str, constants: Dict[str, Union[str, int, float]]
    ) -> Tuple[str, List[Diagnostic]]:
        diagnostics: List[Diagnostic] = []

        def handle_match(match: Match[str]) -> str:
            """Replace a given placeholder match with a value from the project
            configuration. Log a warning if it's not defined."""
            variable_name = match.group(1)
            try:
                return str(constants[variable_name])
            except KeyError:
                lineno = source.count("\n", 0, match.start())
                diagnostics.append(ConstantNotDeclared(variable_name, lineno))

            # Return a zero-width space to avoid breaking syntax
            return "\u200b"

        return PAT_VARIABLE.sub(handle_match, source), diagnostics

    def substitute(self, source: str) -> Tuple[str, List[Diagnostic]]:
        """Substitute all placeholders within a string."""
        return self._substitute(source, self.constants)

    @staticmethod
    def validate_data(data: Dict[str, object]) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        permitted_fields = specparser.Spec.get().data_fields
        for key in data:
            if key not in permitted_fields:
                diagnostics.append(
                    UnmarshallingError(f'Data field "{key}" not permitted', 0)
                )

        return diagnostics

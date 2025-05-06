"""Parser for a TOML spec file containing definitions of all supported reStructuredText
directives and roles, and what types of data each should expect."""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

import tomli
from typing_extensions import Protocol

from snooty.diagnostics import Diagnostic, UnknownOptionId

from . import tinydocutils, util
from .flutter import check_type, checked

#: Types of formatting that can be applied to a role.
FormattingType = Enum("FormattingType", ("strong", "monospace", "emphasis"))

#: How the target should be preprocessed.
TargetType = Enum("TargetType", ("plain", "callable", "cmdline_option"))

#: Types of formatting to which date directives must conform.
DateFormattingType = Enum("DateFormattingType", ("iso_8601"))

_T = TypeVar("_T", "Directive", "Role", "RstObject")
_V = TypeVar("_V")
SPEC_VERSION = 0
StringOrStringlist = Union[List[str], str, None]
PrimitiveType = Enum(
    "PrimitiveType",
    (
        "integer",
        "nonnegative_integer",
        "path",
        "uri",
        "string",
        "length",
        "boolean",
        "flag",
        "linenos",
    ),
)
PrimitiveRoleType = Enum("PrimitiveRoleType", ("text", "explicit_title"))

#: docutils option validation function for each of the above primitive types
VALIDATORS: Dict[PrimitiveType, Callable[[Any], Any]] = {
    PrimitiveType.integer: int,
    PrimitiveType.nonnegative_integer: tinydocutils.directives.nonnegative_int,
    PrimitiveType.path: util.option_string,
    PrimitiveType.uri: tinydocutils.directives.uri,
    PrimitiveType.string: util.option_string,
    PrimitiveType.length: tinydocutils.directives.length_or_percentage_or_unitless,
    PrimitiveType.boolean: util.option_bool,
    PrimitiveType.flag: util.option_flag,
    PrimitiveType.linenos: util.option_string,
}

logger = logging.getLogger(__name__)

#: Option types can be a primitive type (PrimitiveType), an enum
#: defined in the spec, or a union of those.
ArgumentType = Union[List[Union[PrimitiveType, str]], PrimitiveType, str, None]


class MissingDict(Dict[str, _V]):
    pass


class MissingList(List[ArgumentType]):
    pass


class _HasNameAndDomain(Protocol):
    domain: Optional[str]
    name: str


@checked
@dataclass
class DateType:
    """Configuration for a directive that specifies a date"""

    date: DateFormattingType = field(default=DateFormattingType.iso_8601)


@checked
@dataclass
class Meta:
    """Meta information about the file as a whole."""

    version: int


@checked
@dataclass
class DirectiveOption:
    type: ArgumentType
    required: bool = field(default=False)


@checked
@dataclass
class MethodSelectorOption:
    id: str
    title: str


@checked
@dataclass
class TabDefinition:
    id: str
    title: str


@checked
@dataclass
class WayfindingOption:
    id: str
    language: str
    title: str
    show_first: bool = field(default=False)


@checked
@dataclass
class LinkRoleType:
    """Configuration for a role which links to a specific URL template."""

    link: str
    ensure_trailing_slash: Optional[bool]
    format: Set[FormattingType] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.link.count("%s") != 1:
            raise ValueError(
                f"Link definitions in rstspec.toml need to contain a single '%s' placeholder: {self.link}"
            )


@checked
@dataclass
class RefRoleType:
    """Configuration for a role which links to an optionally namespaced target."""

    domain: Optional[str]
    name: str
    tag: Optional[str]
    format: Set[FormattingType] = field(
        default_factory=lambda: {FormattingType.monospace}
    )


@checked
@dataclass
class Composable:
    """Composable object with id, title, default, and options"""

    id: str
    title: str
    default: Optional[str]
    dependencies: Optional[List[Dict[str, str]]]
    options: List[TabDefinition]


#: Spec definition of a role: this can be either a PrimitiveRoleType, or
#: an object requiring additional configuration.
RoleType = Union[PrimitiveRoleType, LinkRoleType, RefRoleType]


@checked
@dataclass
class Directive:
    """Declaration of a reStructuredText directive (block content)."""

    inherit: Optional[str]
    help: Optional[str]
    example: Optional[str]
    content_type: Optional[StringOrStringlist]
    argument_type: Union[DirectiveOption, ArgumentType]
    required_context: Optional[str]
    domain: Optional[str]
    deprecated: bool = field(default=False)
    options: Dict[str, Union[DirectiveOption, ArgumentType]] = field(
        default_factory=MissingDict
    )
    fields: List[ArgumentType] = field(default_factory=MissingList)
    name: str = field(default="")
    rstobject: "Optional[RstObject]" = field(default=None)

    # Add a required_options attribute for quickly enumerating options that must exist
    # This is a little hacky, but is the best we can do in Python 3.7 using dataclasses.
    def __post_init__(self) -> None:
        self.__required_options = frozenset(
            k
            for k, v in self.options.items()
            if isinstance(v, DirectiveOption) and v.required
        )

    @property
    def required_options(self) -> FrozenSet[str]:
        return self.__required_options


@checked
@dataclass
class Role:
    """Declaration of a reStructuredText role (inline content)."""

    inherit: Optional[str]
    help: Optional[str]
    example: Optional[str]
    type: Optional[RoleType]
    domain: Optional[str]
    deprecated: bool = field(default=False)
    name: str = field(default="")
    rstobject: "Optional[RstObject]" = field(default=None)


# A target consists of the following parts:
# domain (e.g. "std" or "mongodb")
# ":"
# role (e.g. "label" or "authaction")
# prefix (e.g. "bin" or a program name)
# "."
# target
@checked
@dataclass
class RstObject:
    """Declaration of a reStructuredText object, defining both a Directive
    as well as a Role that links to that directive."""

    inherit: Optional[str]
    help: Optional[str]
    domain: Optional[str]
    prefix: str = field(default="")
    type: TargetType = field(default=TargetType.plain)
    deprecated: bool = field(default=False)
    name: str = field(default="")
    fields: List[ArgumentType] = field(default_factory=MissingList)
    options: Dict[str, Union[DirectiveOption, ArgumentType]] = field(
        default_factory=MissingDict
    )
    format: Set[FormattingType] = field(
        default_factory=lambda: {FormattingType.monospace}
    )

    def create_directive(self) -> Directive:
        return Directive(
            inherit=None,
            help=self.help,
            example=None,
            content_type="block",
            argument_type=DirectiveOption(type="string", required=True),
            required_context=None,
            domain=self.domain,
            deprecated=self.deprecated,
            options=self.options,
            fields=[],
            name=self.name,
            rstobject=self,
        )

    def create_role(self) -> Role:
        return Role(
            inherit=None,
            help=self.help,
            example=None,
            type=RefRoleType(self.domain, self.name, self.prefix, format=self.format),
            domain=self.domain,
            deprecated=self.deprecated,
            name=self.name,
            rstobject=self,
        )


@checked
@dataclass
class BuildSettings:
    cache_url_prefix: Optional[str] = field(default=None)


@checked
@dataclass
class Spec:
    """The spec root."""

    meta: Meta
    build: BuildSettings = field(default_factory=BuildSettings)
    enum: Dict[str, List[str]] = field(default_factory=dict)
    directive: Dict[str, Directive] = field(default_factory=dict)
    role: Dict[str, Role] = field(default_factory=dict)
    rstobject: Dict[str, RstObject] = field(default_factory=dict)
    method_selector: Dict[str, List[MethodSelectorOption]] = field(default_factory=dict)
    tabs: Dict[str, List[TabDefinition]] = field(default_factory=dict)
    wayfinding: Dict[str, List[WayfindingOption]] = field(default_factory=dict)
    data_fields: List[str] = field(default_factory=list)
    composables: List[Composable] = field(default_factory=list)
    merged: bool = False

    SPEC: ClassVar[Optional[Spec]] = None

    @classmethod
    def loads(cls, data: str) -> "Spec":
        """Load a spec from a string."""
        root = check_type(cls, tomli.loads(data))
        if root.meta.version != SPEC_VERSION:
            raise ValueError(f"Unknown spec version: {root.meta.version}")

        # Inform each section element of its name and domain
        sections: Sequence[Mapping[str, _HasNameAndDomain]] = (
            root.directive,
            root.role,
            root.rstobject,
        )
        for section in sections:
            for key, value in section.items():
                domain, value.name = util.split_domain(key)
                if domain:
                    value.domain = domain

        root._resolve_inheritance()

        return root

    def strip_prefix_from_name(self, rstobject_id: str, title: str) -> str:
        rstobject = self.rstobject.get(rstobject_id, None)
        if rstobject is None:
            return title

        candidate = f"{rstobject.prefix}."
        if title.startswith(candidate):
            return title[len(candidate) :]

        return title

    def get_validator(
        self, option_spec: Union[DirectiveOption, ArgumentType]
    ) -> Callable[[str], object]:
        """Return a validation function for a given argument type. This function will take in a
        string, and either throw an exception or return an output value."""
        if isinstance(option_spec, DirectiveOption):
            option_spec = option_spec.type

        if isinstance(option_spec, list):
            child_validators = [self.get_validator(spec) for spec in option_spec]

            def validator(argument: str) -> object:
                for child_validator in child_validators:
                    try:
                        result = child_validator(argument)
                    except Exception:
                        continue
                    else:
                        return result

                options = ", ".join(str(x) for x in option_spec)
                raise ValueError(f"Expected one of {options}; got {argument}")

            return validator
        elif isinstance(option_spec, PrimitiveType):
            return VALIDATORS[option_spec]
        elif isinstance(option_spec, str) and option_spec == "iso_8601":

            def validator(argument: str) -> object:
                # Error is thrown if format is wrong
                datetime.fromisoformat(argument)
                return argument

            return validator
        elif isinstance(option_spec, str) and option_spec in self.enum:
            return lambda argument: tinydocutils.directives.choice(
                argument, self.enum[option_spec]
            )

        raise ValueError(f'Unknown directive argument type "{option_spec}"')

    def _resolve_inheritance(self) -> None:
        """Spec entries can inherit from other entries; resolve this.

        Not all fields are implicitly inherited: only fields with a default value
        of None or MissingDict are inherited. This means that, for example content_type
        is inherited, but as of this writing, deprecated is not."""
        self._resolve_category(self.directive)
        self._resolve_category(self.role)
        self._resolve_category(self.rstobject)

    @staticmethod
    def _resolve_category(inheritable_index: Dict[str, _T]) -> None:
        """Resolve inheritance within a tree of inheritable dataclasses."""
        resolved: Set[str] = set()
        pending: Set[str] = set()

        def resolve_value(key: str, inheritable: _T) -> _T:
            """Resolve a single inheritable dataclass."""
            if key in pending:
                raise ValueError(f"Inheritance cycle detected while resolving {key}")

            if key in resolved:
                return inheritable

            if inheritable.inherit is not None:
                pending.add(key)
                try:
                    base = resolve_value(
                        inheritable.inherit, inheritable_index[inheritable.inherit]
                    )
                except KeyError:
                    msg = f"Cannot inherit from non-existent directive {inheritable.inherit}"
                    raise ValueError(msg)

                inheritable = dataclasses.replace(
                    base,
                    **{
                        k: v
                        for k, v in dataclasses.asdict(inheritable).items()
                        if v is not None
                        and not isinstance(v, (MissingDict, MissingList))
                    },
                )
                inheritable_index[key] = inheritable
                pending.remove(key)

            resolved.add(key)
            return inheritable

        for key, inheritable in inheritable_index.items():
            resolve_value(key, inheritable)

    @classmethod
    def _merge_composables(
        cls, spec: Spec, custom_composables: List[Dict[str, Any]]
    ) -> Tuple[Spec, List[Diagnostic]]:
        res: List[Composable] = []
        diagnostics: List[Diagnostic] = []

        custom_composable_by_id = {
            composable["id"]: composable for composable in custom_composables
        }

        for defined_composable in spec.composables:
            custom_composable = custom_composable_by_id.pop(defined_composable.id, None)
            merged_title = (
                custom_composable["title"]
                if custom_composable
                else defined_composable.title
            )

            # merge all the options
            defined_options = {
                option.id: option for option in defined_composable.options
            }
            custom_options = (
                {option["id"]: option for option in custom_composable["options"]}
                if custom_composable
                else {}
            )

            merged_options = []
            for option_id in set(defined_options.keys()) | set(custom_options.keys()):
                if option_id in custom_options:
                    custom_option = custom_options[option_id]
                    merged_options.append(
                        TabDefinition(custom_option["id"], custom_option["title"])
                    )
                else:
                    merged_options.append(defined_options[option_id])

            merged_dependencies = (
                custom_composable["dependencies"]
                if custom_composable and "dependencies" in custom_composable
                else defined_composable.dependencies
            )

            merged_default = (
                custom_composable["default"]
                if custom_composable and "default" in custom_composable
                else defined_composable.default
            )
            default_option = next(
                (
                    option
                    for option in merged_options
                    if merged_default and option.id == merged_default
                ),
                None,
            )
            if merged_default and not default_option:
                diagnostics.append(
                    UnknownOptionId(
                        "Spec composables default",
                        merged_default,
                        [option.title for option in merged_options],
                        0,
                    )
                )
            res.append(
                Composable(
                    defined_composable.id,
                    merged_title,
                    merged_default,
                    merged_dependencies,
                    merged_options,
                )
            )

        for composableObj in custom_composable_by_id.values():
            res.append(
                Composable(
                    composableObj["id"],
                    composableObj["title"],
                    composableObj["default"] if "default" in composableObj else None,
                    (
                        composableObj["dependencies"]
                        if "dependencies" in composableObj
                        else None
                    ),
                    list(
                        map(
                            lambda option: TabDefinition(option["id"], option["title"]),
                            composableObj["options"],
                        )
                    ),
                )
            )

        spec.composables = res
        return (spec, diagnostics)

    @classmethod
    def initialize(cls, text: str, configPath: Optional[Path]) -> "Spec":
        cls.SPEC = Spec.loads(text)
        if configPath:
            project_config = tomli.loads(configPath.read_text(encoding="utf-8"))
            # NOTE: would like to check_type but circular imports
            # this is already verified earlier in the process
            spec, diagnostics = cls._merge_composables(
                cls.SPEC, project_config["composables"] or []
            )
            spec.merged = True
            cls.SPEC = spec
            for diagnostic in diagnostics:
                logger.error(diagnostic)
        return cls.SPEC

    @classmethod
    def get(cls, configPath: Optional[Path]) -> "Spec":
        if cls.SPEC and cls.SPEC.merged:
            return cls.SPEC

        path = util.PACKAGE_ROOT.joinpath("rstspec.toml")
        print("check configPath", configPath)
        spec = cls.initialize(path.read_text(encoding="utf-8"), configPath)

        cls.SPEC = spec
        assert cls.SPEC is not None
        return cls.SPEC

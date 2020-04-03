"""Parser for a TOML spec file containing definitions of all supported reStructuredText
   directives and roles, and what types of data each should expect."""

import dataclasses
import toml
from dataclasses import dataclass, field
from enum import Enum
import docutils.nodes
import docutils.parsers.rst
import docutils.parsers.rst.directives
from .flutter import check_type, checked
from . import util
from typing import (
    cast,
    Any,
    Callable,
    Dict,
    Set,
    Sequence,
    List,
    Optional,
    Union,
    TypeVar,
    Mapping,
)
from typing_extensions import Protocol

#: Types of formatting that can be applied to a role.
FormattingType = Enum("FormattingType", ("strong", "monospace", "emphasis"))

#: How the target should be preprocessed.
TargetType = Enum("TargetType", ("plain", "callable", "cmdline_option"))

#: Types of formatting to which date directives must conform.
DateFormattingType = Enum("DateType", ("iso_8601"))


class _Inheritable(Protocol):
    inherit: Optional[str]


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
class LinkRoleType:
    """Configuration for a role which links to a specific URL template."""

    link: str
    format: Set[FormattingType] = field(default_factory=set)


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


_T = TypeVar("_T", bound=_Inheritable)
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

#: Spec definition of a role: this can be either a PrimitiveRoleType, or
#: an object requiring additional configuration.
RoleType = Union[PrimitiveRoleType, LinkRoleType, RefRoleType]

#: docutils option validation function for each of the above primitive types
VALIDATORS: Dict[PrimitiveType, Callable[[Any], Any]] = {
    PrimitiveType.integer: int,
    PrimitiveType.nonnegative_integer: docutils.parsers.rst.directives.nonnegative_int,
    PrimitiveType.path: str,
    PrimitiveType.uri: docutils.parsers.rst.directives.uri,
    PrimitiveType.string: str,
    PrimitiveType.length: docutils.parsers.rst.directives.length_or_percentage_or_unitless,
    PrimitiveType.boolean: util.option_bool,
    PrimitiveType.flag: util.option_flag,
    PrimitiveType.linenos: str,
}

#: Option types can be a primitive type (PrimitiveType), an enum
#: defined in the spec, or a union of those.
ArgumentType = Union[List[Union[PrimitiveType, str]], PrimitiveType, str, None]


class MissingDict(Dict[str, ArgumentType]):
    pass


@checked
@dataclass
class Meta:
    """Meta information about the file as a whole."""

    version: int


@checked
@dataclass
class Directive:
    """Declaration of a reStructuredText directive (block content)."""

    inherit: Optional[str]
    help: Optional[str]
    example: Optional[str]
    content_type: Optional[StringOrStringlist]
    argument_type: ArgumentType
    required_context: Optional[str]
    domain: Optional[str]
    deprecated: bool = field(default=False)
    options: Dict[str, ArgumentType] = field(default_factory=MissingDict)
    name: str = field(default="")
    rstobject: "Optional[RstObject]" = field(default=None)


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
    format: Set[FormattingType] = field(
        default_factory=lambda: {FormattingType.monospace}
    )

    @property
    def callable(self) -> bool:
        return self.type == TargetType.callable

    def create_directive(self) -> Directive:
        return Directive(
            inherit=None,
            help=self.help,
            example=None,
            content_type="block",
            argument_type="string",
            required_context=None,
            domain=self.domain,
            deprecated=self.deprecated,
            options={},
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
class Spec:
    """The spec root."""

    meta: Meta
    enum: Dict[str, List[str]] = field(default_factory=dict)
    directive: Dict[str, Directive] = field(default_factory=dict)
    role: Dict[str, Role] = field(default_factory=dict)
    rstobject: Dict[str, RstObject] = field(default_factory=dict)

    @classmethod
    def loads(cls, data: str) -> "Spec":
        """Load a spec from a string."""
        root = check_type(cls, toml.loads(data))
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

    def get_validator(self, option_spec: ArgumentType) -> Callable[[str], object]:
        """Return a validation function for a given argument type. This function will take in a
           string, and either throw an exception or return an output value."""
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

                # Assertion to quiet mypy's failing type flow analysis
                assert isinstance(option_spec, list)
                options = ", ".join(str(x) for x in option_spec)
                raise ValueError(f"Expected one of {options}; got {argument}")

            return validator
        elif isinstance(option_spec, PrimitiveType):
            return VALIDATORS[option_spec]
        elif isinstance(option_spec, str) and option_spec in self.enum:
            return lambda argument: docutils.parsers.rst.directives.choice(
                argument, self.enum[cast(str, option_spec)]
            )

        raise ValueError(f'Unknown directive argument type "{option_spec}"')

    def _resolve_inheritance(self) -> None:
        """Directives can inherit from other directives; resolve this."""
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
                        if v is not None and not isinstance(v, MissingDict)
                    },
                )
                inheritable_index[key] = inheritable
                pending.remove(key)

            resolved.add(key)
            return inheritable

        for key, inheritable in inheritable_index.items():
            resolve_value(key, inheritable)

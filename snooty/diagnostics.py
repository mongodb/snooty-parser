import enum
from pathlib import Path, PurePath
from typing import AbstractSet, Dict, List, Optional, Sequence, Tuple, Union

from . import n
from .n import SerializableType


class MakeCorrectionMixin:
    def did_you_mean(self) -> List[str]:
        """Suggest one or more possible corrections to the reStructuredText that this
        diagnostic is about."""
        raise NotImplementedError()


class Diagnostic:
    def __init__(
        self,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        self.message = message

        if isinstance(start, int):
            start_line, start_column = start, 0
        else:
            start_line, start_column = start
        self.start = (start_line, start_column)

        if end is None:
            end_line, end_column = start_line, 1000
        elif isinstance(end, int):
            end_line, end_column = end, 1000
        else:
            end_line, end_column = end
        self.end = (end_line, end_column)

    class Level(enum.IntEnum):
        info = 1
        warning = 2
        error = 3

        @classmethod
        def from_docutils(cls, level: int) -> "Diagnostic.Level":
            level = max(level, cls.info)
            level = min(level, cls.error)
            return cls(level)

    @property
    def severity(self) -> "Diagnostic.Level":
        raise TypeError("Cannot access the severity of an abstract base Diagnostic")

    @property
    def severity_string(self) -> str:
        return self.severity.name.title()

    def serialize(self) -> n.SerializedNode:
        """Create dict containing diagnostic attributes for neatly reporting diagnostics at program completion"""
        diag: Dict[str, SerializableType] = {}
        diag["severity"] = self.severity_string.upper()
        diag["start"] = self.start[0]
        diag["message"] = self.message
        return diag

    def __eq__(self, other: object) -> bool:
        if type(self) != type(other):
            return False

        assert isinstance(other, Diagnostic)

        return (
            self.message == other.message
            and self.start == other.start
            and self.end == other.end
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.message)}, {repr(self.start)})"


class UnexpectedIndentation(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__("Unexpected indentation", start, end)

    def did_you_mean(self) -> List[str]:
        return [".. blockquote::"]


class ExpectedOption(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        option: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'"{name}" missing expected option "{option}"', start, end)


class InvalidURL(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__("Invalid URL", start, end)


class ExpectedPathArg(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'"{name}" expected a path argument', start, end)
        self.name = name


class ExpectedStringArg(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        expectedArg: str,
        receivedArg: Union[str, None],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f'"{name}" expected argument "{expectedArg}", but received "{receivedArg}"',
            start,
            end,
        )
        self.name = name


class UnnamedPage(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        filename: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Page title not found: {filename}", start, end)
        self.filename = filename


class ExpectedImageArg(Diagnostic):
    severity = Diagnostic.Level.error


class ImageSuggested(Diagnostic):
    severity = Diagnostic.Level.info

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'"{name}" expected an image argument', start, end)
        self.name = name


class InvalidField(Diagnostic):
    severity = Diagnostic.Level.error


class GitMergeConflictArtifactFound(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Optional[Path],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Git merge conflict artifact found{' in ' + str(path) if path else ''} on line {str(start)}",
            start,
            end,
        )


class DocUtilsParseError(Diagnostic):
    severity = Diagnostic.Level.warning


class ErrorParsingYAMLFile(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Optional[Path],
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        message = (
            f"Error parsing YAML file {str(path)}: {reason}"
            if path
            else f"Error parsing YAML: {reason}"
        )
        super().__init__(message, start, end)
        self.path = path
        self.reason = reason


class InvalidDirectiveStructure(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        msg: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'Directive "io-code-block" {msg}', start, end)


class InvalidInclude(Diagnostic):
    severity = Diagnostic.Level.error


class InvalidLiteralInclude(Diagnostic):
    severity = Diagnostic.Level.error


class AmbiguousLiteralInclude(Diagnostic):
    severity = Diagnostic.Level.warning


class SubstitutionRefError(Diagnostic):
    severity = Diagnostic.Level.error


class InvalidContextError(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Cannot substitute block elements into an inline context: |{name}|",
            start,
            end,
        )
        self.name = name


class ConstantNotDeclared(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"{name} not defined as a source constant", start, end)
        self.name = name


class InvalidTableStructure(Diagnostic):
    severity = Diagnostic.Level.error


class InvalidNestedTabStructure(Diagnostic):
    severity = Diagnostic.Level.info

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Detect tabs that contain tabs that contain procedures: : "{name}" """,
            start,
            end,
        )
        self.name = name


class MissingOption(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__("'.. option::' must follow '.. program::'", start, end)


class MissingRef(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Missing ref; all {name} must define a ref", start, end)
        self.name = name


class MalformedGlossary(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            "Malformed glossary: glossary must contain only a definition list",
            start,
            end,
        )


class FailedToInheritRef(Diagnostic):
    severity = Diagnostic.Level.error


class RefAlreadyExists(Diagnostic):
    severity = Diagnostic.Level.error


class UnknownSubstitution(Diagnostic):
    severity = Diagnostic.Level.warning


class TargetNotFound(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        target: str,
        candidates: Sequence[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'Target not found: "{name}:{target}"', start, end)
        self.name = name
        self.target = target
        self.candidates = list(candidates)

    def did_you_mean(self) -> List[str]:
        return self.candidates


class AmbiguousTarget(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        target: str,
        candidates: List[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f'Ambiguous target: "{name}:{target}". Locations: {", ".join(candidates)}',
            start,
            end,
        )
        self.name = name
        self.target = target
        self.candidates = candidates


class ChildlessRef(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        target: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f'Reference found without label: "{target}". Be sure to add label text to the :ref: itself OR place the target reference directly before a heading',
            start,
            end,
        )
        self.target = target


class TodoInfo(Diagnostic):
    severity = Diagnostic.Level.info


class UnmarshallingError(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Unmarshalling Error: {reason}", start, end)
        self.reason = reason


class CannotOpenFile(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Optional[PurePath],
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Error opening{' ' + str(path) if path else ''}: {reason}", start, end
        )
        self.path = path
        self.reason = reason


class CannotRenderOpenAPI(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Path,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Failed to render OpenAPI template for {str(path)}: {reason}", start, end
        )
        self.path = path
        self.reason = reason


class MissingTocTreeEntry(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        entry: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Could not locate toctree entry {entry}", start, end)
        self.entry = entry


class InvalidTocTree(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            """Projects with both "toctree" and "ia" directives are not supported""",
            start,
            end,
        )

    def did_you_mean(self) -> List[str]:
        return [".. ia::"]


class MissingAssociatedToc(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        expected_project: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Detected an associated toctree entry at {expected_project}
            which does not exist in an associated_products entry within the snooty.toml.
            Removing this toctree entry.""",
            start,
            end,
        )


class DuplicatedExternalToc(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        duplicated_toc: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Detected a duplicated associated toctree entry at {duplicated_toc}. Removing this toctree entry.",
            start,
            end,
        )


class InvalidIAEntry(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        msg: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Invalid IA entry: {msg}",
            start,
            end,
        )


class InvalidIALinkedData(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        msg: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Unable to link data for IA: {msg}",
            start,
            end,
        )


class UnknownTabset(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        tabset: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Tabset "{tabset}" is not defined in rstspec.toml""", start, end
        )
        self.tabset = tabset


class UnknownTabID(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        tabid: str,
        tabset: str,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""tab id "{tabid}" given in "{tabset}" tabset is unrecognized: {reason}""",
            start,
            end,
        )
        self.tabid = tabid
        self.tabset = tabset
        self.reason = reason


class TabMustBeDirective(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        tab_type: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Tabs or Tab sets may only contain tab directives, but found {tab_type}",
            start,
            end,
        )
        self.tab_type = tab_type


class IncorrectMonospaceSyntax(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        text: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__("Monospace text uses two backticks (``)", start, end)
        self.text = text

    def did_you_mean(self) -> List[str]:
        return [f"``{self.text}``"]


class IncorrectLinkSyntax(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        parts: Tuple[str, str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__("Malformed external link", start, end)
        self.parts = parts

    def did_you_mean(self) -> List[str]:
        return [f"`{self.parts[0]} <{self.parts[1]}>`__"]


class MalformedRelativePath(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        relative_path: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Malformed relative path {relative_path}", start, end)
        self.relative_path = relative_path


class MissingTab(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        tabs: AbstractSet[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        sorted_tabs = sorted(tabs)
        super().__init__(
            f"One or more set of tabs on this page was missing the following tab(s): {sorted_tabs}",
            start,
            end,
        )
        self.tabs = sorted_tabs


class ExpectedTabs(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            "Expected tabs directive when tabs-selector directive in use",
            start,
            end,
        )


class DuplicateDirective(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Directive "{name}" should only appear once per page""",
            start,
            end,
        )
        self.name = name


class RemovedLiteralBlockSyntax(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            "Literal block syntax is unsupported; use a code-block directive instead",
            start,
            end,
        )


class UnsupportedFormat(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        actual: str,
        expected: Sequence[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Unsupported file format: {actual}. Must be one of {','.join(expected)}",
            start,
            end,
        )


class FetchError(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Failed to download file: {message}",
            start,
            end,
        )


class InvalidChild(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        child: str,
        parent: str,
        suggestion: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"{child} is not a valid child of {parent}", start, end)
        self.suggestion = suggestion

    def did_you_mean(self) -> List[str]:
        return [f".. {self.suggestion}::"]


class ConfigurationProblem(Diagnostic):
    severity = Diagnostic.Level.error


class ChapterAlreadyExists(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        chapter_name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'Chapter "{chapter_name}" already exists', start, end)


class InvalidChapter(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Invalid chapter: {message}", start, end)


class MissingChild(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        directive: str,
        expected_child: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f'Directive "{directive}" expects at least one child of type "{expected_child}"; found 0',
            start,
            end,
        )


class GuideAlreadyHasChapter(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        guide_slug: str,
        assigned_chapter: str,
        target_chapter: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Cannot add guide "{guide_slug}" to chapter "{target_chapter}" because the guide is already assigned to chapter "{assigned_chapter}\"""",
            start,
            end,
        )


class IconMustBeDefined(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        icon_role: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"The Icon {icon_role} does not exist",
            start,
            end,
        )


class InvalidOpenApiResponse(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            "OpenAPI Versioning data is malformed. Please contact DOP team.",
            start,
            end,
        )


class InvalidVersion(Diagnostic, MakeCorrectionMixin):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        directive: str,
        api_version: str,
        major_versions: Sequence[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Invalid OpenAPI Version option ({api_version}) specified for directive {directive}""",
            start,
            end,
        )
        self.major_versions = major_versions

    def did_you_mean(self) -> List[str]:
        return list(self.major_versions)


class MissingStructuredDataFields(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        directive_name: str,
        fields: List[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Fields for {directive_name} structured data SEO are partially defined. Missing the following options: {fields}""",
            start,
            end,
        )


class MissingFacet(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        facet_name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"""Facet specified is not a valid facet: {facet_name}""", start, end
        )


class NestedProject(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        nested_project: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"""WARNING! Nested project detected: {nested_project}. Files from this project will not be parsed.""",
            start,
            end,
        )


class ImageSizeUndetermined(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        raw_path: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"""Intrinsic size for image not calculated at path {raw_path}. Image may not be lazy loaded.""",
            start,
            end,
        )


class OrphanedPage(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(self) -> None:
        super().__init__(
            "Page not included in any toctree and not marked :orphan:",
            0,
            None,
        )


class NestedDirective(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        nested_directive: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"""Nesting of {nested_directive} directives prohibited""",
            start,
            end,
        )


class UnknownOptionId(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        directive_name: str,
        invalid_id: str,
        valid_ids: List[str],
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"{directive_name} id {invalid_id} is not valid. Expected one of the following: {valid_ids}",
            start,
            end,
        )


class DuplicateOptionId(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        directive_name: str,
        invalid_id: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"{directive_name} option id {invalid_id} is already used in current context.",
            start,
            end,
        )


class UnexpectedDirectiveOrder(Diagnostic):
    severity = Diagnostic.Level.warning

    def __init__(
        self,
        message: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(f"Unexpected directive order. Expected: {message}", start, end)


class InvalidChildCount(Diagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        parent_name: str,
        child_name: str,
        expected: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ):
        super().__init__(
            f"Unexpected number of {child_name} in {parent_name}. Expected: {expected}",
            start,
            end,
        )

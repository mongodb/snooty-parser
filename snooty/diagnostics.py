import enum
from typing import Tuple, Union
from pathlib import Path


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
        info = 0
        error = 1
        warning = 2

        @classmethod
        def from_docutils(cls, docutils_level: int) -> "Diagnostic.Level":
            level = docutils_level - 1
            level = min(level, cls.warning)
            level = max(level, cls.info)
            return cls(level)

    @property
    def severity(self) -> "Diagnostic.Level":
        raise TypeError("Cannot access the severity of an abstract base Diagnostic")

    @property
    def severity_string(self) -> str:
        return self.severity.name.title()


class ParserDiagnostic(Diagnostic):
    pass


class UnexpectedIndentation(ParserDiagnostic):
    severity = Diagnostic.Level.error


class InvalidURL(ParserDiagnostic):
    severity = Diagnostic.Level.error


# this could captuer 'literal include expected path arg..as well?
class ExpectedPathArg(ParserDiagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        name: Path,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f'"{name}" expected a path argument', start, end)
        self.name = name


class ExpectedImgArg(ParserDiagnostic):
    severity = Diagnostic.Level.error


class ImgExpectedButNotRequired(ParserDiagnostic):
    severity = Diagnostic.Level.warning


class OptionsNotSupported(ParserDiagnostic):
    severity = Diagnostic.Level.error


class GitMergeConflictArtifactFound(ParserDiagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Path,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(
            f"Git merge conflict artifact found in {str(path)} on line {str(start)}",
            start,
            end,
        )
        self.path = path


class DocUtilsParseError(ParserDiagnostic):
    severity = Diagnostic.Level.warning


class ErrorParsingYAMLFile(ParserDiagnostic):
    severity = Diagnostic.Level.error
    def __init__(
        self,
        path: Path,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Error parsing YAML file {str(path)}: {reason}", start, end)
        self.path = path
        self.reason = reason

class SemanticDiagnostic(Diagnostic):
    pass


class InvalidLiteralInclude(SemanticDiagnostic):
    severity = Diagnostic.Level.error


class SubstitutionRefError(SemanticDiagnostic):
    severity = Diagnostic.Level.error


class VariableNotDeclaredConstant(SemanticDiagnostic):
    severity = Diagnostic.Level.error


class InvalidTableStructure(SemanticDiagnostic):
    severity = Diagnostic.Level.error


class MissingOption(SemanticDiagnostic):
    severity = Diagnostic.Level.error


class GizaDiagnostic(SemanticDiagnostic):
    pass


class RefDiagnositc(GizaDiagnostic):
    pass


class MissingRef(RefDiagnositc):
    severity = Diagnostic.Level.error
    def __init__(
        self,
        name: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Missing ref; all {name} must define a ref", start, end)
        self.name = name



class FailedToInheritRef(RefDiagnositc):
    severity = Diagnostic.Level.error


class RefAlreadyExists(RefDiagnositc):
    severity = Diagnostic.Level.error


class UnknownSubstitution(RefDiagnositc):
    severity = Diagnostic.Level.warning


class TargetDiagnostic(SemanticDiagnostic):
    pass


class TargetNotFound(TargetDiagnostic):
    severity = Diagnostic.Level.error


class AmbiguousTarget(TargetDiagnostic):
    severity = Diagnostic.Level.error


class DirectiveDiagnostic(SemanticDiagnostic):
    pass


class TodoInfo(DirectiveDiagnostic):
    severity = Diagnostic.Level.info


class LoadDiagnostic(Diagnostic):
    pass


class ErrorLoadingFile(LoadDiagnostic):
    severity = Diagnostic.Level.error
    def __init__(
        self,
        path: Path,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Error loading {str(path)}: {reason}", start, end)
        self.path = path
        self.reason = reason

class OSDiagnostic(LoadDiagnostic):
    pass


class CannotOpenFile(OSDiagnostic):
    severity = Diagnostic.Level.error

    def __init__(
        self,
        path: Path,
        reason: str,
        start: Union[int, Tuple[int, int]],
        end: Union[None, int, Tuple[int, int]] = None,
    ) -> None:
        super().__init__(f"Error opening {str(path)}: {reason}", start, end)
        self.path = path
        self.reason = reason

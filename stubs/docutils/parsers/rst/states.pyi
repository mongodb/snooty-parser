import docutils.parsers.rst
import docutils.parsers.rst.states
import docutils.statemachine
import docutils.utils
import docutils
from typing import Dict, List, Tuple, Iterable, Sequence, Pattern, Union


def normalize_name(name: str) -> str: ...


class MarkupError(docutils.DataError): ...


class RSTState(docutils.statemachine.State):
    memo: docutils.parsers.rst.states.Struct

    def nested_parse(self,
        block: docutils.statemachine.ViewList,
        input_offset: int,
        node: docutils.nodes.Node,
        match_titles: bool=False) -> None: ...
    def inline_text(self, text: str, lineno: int) -> Tuple[List[docutils.nodes.Node], List[docutils.nodes.Node]]: ...


class Text(RSTState):
    classifier_delimiter: object


class Struct:
    section_level: int


class Body:
    patterns: Dict[str, Pattern[str]] = ...
    def parse_directive_arguments(self,
                                  directive: docutils.parsers.rst.Directive,
                                  arg_block: Iterable[str]) -> Sequence[str]: ...


class Inliner:
    reporter: docutils.utils.Reporter

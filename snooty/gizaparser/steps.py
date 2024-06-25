from dataclasses import dataclass
from typing import Callable, List, MutableSequence, Optional, Sequence, Tuple, Union

from .. import n
from ..diagnostics import Diagnostic
from ..flutter import checked
from ..page import Page
from ..types import EmbeddedRstParser
from .nodes import GizaCategory, GizaFile, HeadingMixin, Inheritable
from .parse import parse


@checked
@dataclass
class Action(HeadingMixin):
    """An action that a user must take."""

    code: Optional[str]
    copyable: Optional[bool]
    content: Optional[str]
    language: Optional[str]
    post: Optional[str]
    pre: Optional[str]

    def render(self, rst_parser: EmbeddedRstParser) -> List[n.Node]:
        all_nodes: List[n.Node] = []
        heading_nodes = self.render_heading(rst_parser)

        if heading_nodes:
            nodes_to_append_children: MutableSequence[n.Node] = []
            section = n.Section((self.line,), nodes_to_append_children)
            section.children = nodes_to_append_children
            all_nodes.append(section)

            nodes_to_append_children.extend(heading_nodes)
        else:
            nodes_to_append_children = all_nodes

        if self.pre:
            result = rst_parser.parse_block(self.pre, self.line)
            nodes_to_append_children.extend(result)

        if self.code:
            nodes_to_append_children.append(
                n.Code(
                    (self.line,),
                    self.language,
                    None,
                    True if self.copyable is None else self.copyable,
                    None,
                    self.code,
                    False,
                    None,
                    None,
                )
            )

        if self.content:
            result = rst_parser.parse_block(self.content, self.line)
            nodes_to_append_children.extend(result)

        if self.post:
            result = rst_parser.parse_block(self.post, self.line)
            nodes_to_append_children.extend(result)

        return all_nodes


@checked
@dataclass
class Step(Inheritable, HeadingMixin):
    stepnum: Optional[int]
    content: Optional[str]
    post: Optional[str]
    pre: Optional[str]
    level: Optional[int]
    optional: Optional[bool]
    edition: Union[List[str], str, None]

    action: Union[List[Action], Action, None]

    def render(self, page: Page, rst_parser: EmbeddedRstParser) -> n.Node:
        children: MutableSequence[n.Node] = []
        root = n.Section((self.line,), children)

        children.extend(self.render_heading(rst_parser))

        if self.pre:
            result = rst_parser.parse_block(self.pre, self.line)
            children.extend(result)

        if self.action:
            actions = [self.action] if isinstance(self.action, Action) else self.action
            for action in actions:
                result = action.render(rst_parser)
                children.extend(result)

        if self.content:
            result = rst_parser.parse_block(self.content, self.line)
            children.extend(result)

        if self.post:
            result = rst_parser.parse_block(self.post, self.line)
            children.extend(result)

        return root


def step_to_page(page: Page, step: Step, rst_parser: EmbeddedRstParser) -> n.Directive:
    rendered = step.render(page, rst_parser)
    directive = n.Directive((step.line,), [], "", "step", [], {})
    directive.children = [rendered]
    return directive


class GizaStepsCategory(GizaCategory[Step]):
    def parse(
        self, path: n.FileId, text: Optional[str] = None
    ) -> Tuple[Sequence[Step], str, List[Diagnostic]]:
        return parse(Step, path, self.project_config, text)

    def _generate_pages(
        self,
        source_fileid: n.FileId,
        page_factory: Callable[[str], Tuple[Page, EmbeddedRstParser]],
        giza_file: GizaFile[Step],
    ) -> List[Page]:
        output_filename = source_fileid.with_suffix(".rst").name
        output_filename = output_filename[len("steps-") :]
        page, rst_parser = page_factory(output_filename)
        page.category = "steps"
        steps_directive = n.Directive((0,), [], "", "procedure", [], {})
        steps_directive.children = [
            step_to_page(page, step, rst_parser) for step in giza_file.data
        ]
        steps_directive.options["style"] = "normal"
        page.ast = n.Root((0,), [], source_fileid, {})
        page.ast.children.append(steps_directive)
        return [page]

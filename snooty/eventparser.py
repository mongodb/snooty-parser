from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import n
from .page import Page
from .types import FileId


class FileIdStack:
    """A stack which tracks file inclusion history, allowing a postprocessor
    pass to know at any point both the page where processing started, as well
    as what file is currently being processed."""

    __slots__ = ("_stack",)

    def __init__(self, initial_stack: Optional[List[FileId]] = None) -> None:
        self._stack: List[FileId] = initial_stack if initial_stack is not None else []

    def pop(self) -> None:
        self._stack.pop()

    def append(self, fileid: FileId) -> None:
        self._stack.append(fileid)

    def clear(self) -> None:
        self._stack.clear()

    @property
    def root(self) -> FileId:
        return self._stack[0]

    @property
    def current(self) -> FileId:
        return self._stack[-1]


class EventParser:
    """Respond to listeners in response to node & page processing events."""

    PAGE_START_EVENT = "page_start"
    PAGE_END_EVENT = "page_end"
    OBJECT_START_EVENT = "object_start"
    OBJECT_END_EVENT = "object_end"

    def __init__(self) -> None:
        self._event_listeners: Dict[str, List[Callable[..., None]]] = defaultdict(list)
        self.fileid_stack = FileIdStack()

    def add_event_listener(self, event: str, listener: Callable[..., None]) -> None:
        """Add a listener to be called when a particular type of event occurs"""
        listeners = self._event_listeners[event]
        listeners.append(listener)

    def fire_page(self, event: str, fileid: FileIdStack, page: Page) -> None:
        """Iterate through all universal listeners and all listeners of the specified type and call them"""
        for listener in self._event_listeners[event]:
            listener(fileid, page)

    def fire_node(self, event: str, fileid: FileIdStack, node: n.Node) -> None:
        """Iterate through all universal listeners and all listeners of the specified type and call them"""
        for listener in self._event_listeners[event]:
            listener(fileid, node)

    def consume(self, d: Iterable[Tuple[FileId, Page]]) -> None:
        """Initializes a parse on the provided key-value map of pages"""
        for filename, page in d:
            self.fire_page(self.PAGE_START_EVENT, FileIdStack([filename]), page)
            self._iterate(page.ast, filename)
            self.fire_page(self.PAGE_END_EVENT, FileIdStack([filename]), page)

            self.fileid_stack.clear()

    def _iterate(self, d: n.Node, filename: FileId) -> None:
        if isinstance(d, n.Root):
            self.fileid_stack.append(d.fileid)

        self.fire_node(self.OBJECT_START_EVENT, self.fileid_stack, d)

        if isinstance(d, n.Parent):
            if isinstance(d, n.DefinitionListItem):
                for child in d.term:
                    self._iterate(child, filename)

            if isinstance(d, n.Directive):
                for arg in d.argument:
                    self._iterate(arg, filename)

            for child in d.children:
                self._iterate(child, filename)

        self.fire_node(self.OBJECT_END_EVENT, self.fileid_stack, d)

        if isinstance(d, n.Root):
            self.fileid_stack.pop()

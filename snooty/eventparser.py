from typing import Any, Callable, Dict, Set, Tuple, Iterable, Union
from .types import FileId, Page
from . import n


class EventListeners:
    """Manage the listener functions associated with an event-based parse operation"""

    def __init__(self) -> None:
        self._universal_listeners: Set[Callable[..., Any]] = set()
        self._event_listeners: Dict[str, Set[Callable[..., Any]]] = {}

    def add_universal_listener(self, listener: Callable[..., Any]) -> None:
        """Add a listener to be called on any event"""
        self._universal_listeners.add(listener)

    def add_event_listener(self, event: str, listener: Callable[..., Any]) -> None:
        """Add a listener to be called when a particular type of event occurs"""
        event = event.upper()
        listeners: Set[Callable[..., Any]] = self._event_listeners.get(event, set())
        listeners.add(listener)
        self._event_listeners[event] = listeners

    def get_event_listeners(self, event: str) -> Set[Callable[..., Any]]:
        """Return all listeners of a particular type"""
        event = event.upper()
        return self._event_listeners.get(event, set())

    def fire(
        self,
        event: str,
        filename: FileId,
        *args: Union[n.Node, Page],
        **kwargs: Union[n.Node, Page],
    ) -> None:
        """Iterate through all universal listeners and all listeners of the specified type and call them"""
        for listener in self.get_event_listeners(event):
            listener(filename, *args, **kwargs)

        for listener in self._universal_listeners:
            listener(filename, *args, **kwargs)


class EventParser(EventListeners):
    """Initialize an event-based parse on a python dictionary"""

    PAGE_START_EVENT = "page_start"
    PAGE_END_EVENT = "page_end"
    OBJECT_START_EVENT = "object_start"
    OBJECT_END_EVENT = "object_end"

    def __init__(self) -> None:
        super(EventParser, self).__init__()

    def consume(self, d: Iterable[Tuple[FileId, Page]]) -> None:
        """Initializes a parse on the provided key-value map of pages"""
        for filename, page in d:
            self._on_page_enter_event(page, filename)
            self._iterate(page.ast, filename)
            self._on_page_exit_event(page, filename)

    def _iterate(self, d: n.Node, filename: FileId) -> None:
        self._on_object_enter_event(d, filename)
        if isinstance(d, n.Parent):
            for child in d.children:
                self._iterate(child, filename)
        self._on_object_exit_event(d, filename)

    def _on_page_enter_event(self, page: Page, filename: FileId) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.PAGE_START_EVENT, filename, page=page)

    def _on_page_exit_event(self, page: Page, filename: FileId) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.PAGE_END_EVENT, filename, page=page)

    def _on_object_enter_event(self, node: n.Node, filename: FileId) -> None:
        """Called when an object is first encountered in tree"""
        self.fire(self.OBJECT_START_EVENT, filename, node=node)

    def _on_object_exit_event(self, node: n.Node, filename: FileId) -> None:
        """Called when an object is first encountered in tree"""
        self.fire(self.OBJECT_END_EVENT, filename, node=node)

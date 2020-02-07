from typing import Any, Callable, cast, Dict, List, Set, Tuple, Iterable, Union
from .types import FileId, Page, SerializableType


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
        *args: Union[SerializableType, Page],
        **kwargs: Union[SerializableType, Page],
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
    ARRAY_START_EVENT = "array_start"
    ELEMENT_EVENT = "element"

    def __init__(self) -> None:
        super(EventParser, self).__init__()

    def consume(self, d: Iterable[Tuple[FileId, Page]]) -> None:
        """Initializes a parse on the provided key-value map of pages"""
        for filename, page in d:
            self._on_page_enter_event(page, filename)
            self._iterate(cast(Dict[str, SerializableType], page.ast), filename)
            self._on_page_exit_event(page, filename)

    def _iterate(self, d: SerializableType, filename: FileId) -> None:
        if isinstance(d, dict):
            self._on_object_enter_event(d, filename)
            for child in d.get("children", ()):
                self._iterate(child, filename)
        elif isinstance(d, list):
            self._on_array_enter_event(d, filename)
            for child in d:
                self._iterate(child, filename)
        else:
            self._on_element_event(d, filename)

    def _on_page_enter_event(
        self,
        page: Page,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType,
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.PAGE_START_EVENT, filename, page=page, *args, **kwargs)

    def _on_page_exit_event(
        self,
        page: Page,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType,
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.PAGE_END_EVENT, filename, page=page, *args, **kwargs)

    def _on_object_enter_event(
        self,
        obj: Dict[str, SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType,
    ) -> None:
        """Called when an object is first encountered in tree"""
        self.fire(self.OBJECT_START_EVENT, filename, obj=obj, *args, **kwargs)

    def _on_array_enter_event(
        self,
        arr: List[SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType,
    ) -> None:
        """Called when an array is first encountered in tree"""
        self.fire(self.ARRAY_START_EVENT, filename, arr=arr, *args, **kwargs)

    def _on_element_event(
        self,
        element: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType,
    ) -> None:
        """Called when an array element is encountered in tree"""
        self.fire(self.ELEMENT_EVENT, filename, element=element, *args, **kwargs)

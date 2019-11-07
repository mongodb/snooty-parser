from typing import Any, Callable, cast, Dict, List, Set
from .types import FileId, Page, SerializableType


class SemanticParser:
    def __init__(self) -> None:
        self.slug_title_mapping: Dict[str, List[SerializableType]] = {}

    def construct_slug_title_mapping(
        self, filename: FileId, *args: SerializableType, **kwargs: SerializableType
    ) -> None:
        obj = cast(Dict[str, SerializableType], kwargs.get("obj"))
        slug = filename.without_known_suffix

        if "includes" in slug or "images" in slug:
            return

        # Save the first heading we encounter to the slug title mapping
        if self.slug_title_mapping.get(slug) is None and obj.get("type") == "heading":
            self.slug_title_mapping[slug] = cast(
                List[SerializableType], obj.get("children")
            )

    def run(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        self.run_event_parser(pages)
        return {"slugToTitle": self.slug_title_mapping}

    def run_event_parser(self, pages: Dict[FileId, Page]) -> None:
        event_parser = EventParser()
        event_parser.add_event_listener("object_start", self.construct_slug_title_mapping)
        event_parser.consume(pages)


class EventListeners:
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
        event = event.upper()
        return self._event_listeners.get(event, set())

    def fire(
        self,
        event: str,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        for listener in self.get_event_listeners(event):
            listener(filename, *args, **kwargs)

        for listener in self._universal_listeners:
            listener(filename, *args, **kwargs)


class EventParser(EventListeners):
    PAGE_START_EVENT = "page_start"
    OBJECT_START_EVENT = "object_start"
    ARRAY_START_EVENT = "array_start"
    PAIR_EVENT = "pair"
    ELEMENT_EVENT = "element"

    def __init__(self) -> None:
        super(EventParser, self).__init__()

    def consume(self, pages: Dict[FileId, Page]) -> None:
        for filename, page in pages.items():
            self._iterate(cast(Dict[str, SerializableType], page.ast), filename)

    def _iterate(self, d: SerializableType, filename: FileId) -> None:
        if isinstance(d, dict):
            self._on_object_enter_event(d, filename)
            for k, v in d.items():
                self._on_pair_event(k, v, filename)
                self._iterate(v, filename)
        elif isinstance(d, list):
            self._on_array_enter_event(d, filename)
            for child in d:
                self._iterate(child, filename)
        else:
            self._on_element_event(d, filename)

    def _on_object_enter_event(
        self,
        obj: Dict[str, SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        self.fire(self.OBJECT_START_EVENT, filename, obj=obj, *args, **kwargs)

    def _on_array_enter_event(
        self,
        arr: List[SerializableType],
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        self.fire(self.ARRAY_START_EVENT, filename, arr=arr, *args, **kwargs)

    def _on_pair_event(
        self,
        key: SerializableType,
        value: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        self.fire(self.PAIR_EVENT, filename, key=key, value=value, *args, **kwargs)

    def _on_element_event(
        self,
        element: SerializableType,
        filename: FileId,
        *args: SerializableType,
        **kwargs: SerializableType
    ) -> None:
        self.fire(self.ELEMENT_EVENT, filename, element=element, *args, **kwargs)

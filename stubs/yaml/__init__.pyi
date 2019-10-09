from .nodes import Node
from .composer import Composer
from .constructor import SafeConstructor
from typing import Any, Callable, Dict, IO, Union


class Loader(Composer, SafeConstructor):
    line: int
    def __init__(self, text: str) -> None: ...
    def add_constructor(self, tag: object, constructor: Callable[['Loader', Node], Dict[str, Any]]) -> None: ...


class SafeLoader(Loader): ...


def safe_load(stream: Union[str, IO[str]]) -> Any: ...

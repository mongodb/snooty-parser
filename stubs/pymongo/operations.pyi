from typing import Any, Dict


class UpdateOne:
    def __init__(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = ...) -> None: ...


class ReplaceOne:
    def __init__(
        self,
        filter: Dict[str, Any],
        replacement: Dict[str, Any],
        upsert: bool = ...) -> None: ...

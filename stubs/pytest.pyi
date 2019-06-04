from typing import Any, Callable, Type


class mark:
    @staticmethod
    def skipif(condition: bool, reason: str = "") -> Callable[..., None]: ...

def raises(exception: Type[Exception]) -> Any: ...

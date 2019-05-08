import docutils.nodes
import docutils.parsers.rst.states
from typing import Any, Callable, Dict, Tuple, Optional, List

def role(role_name: str, language_module: object, lineno: int, reporter: object) -> Tuple[Optional[Callable[..., Any]], List[object]]: ...

def register_local_role(
    name: str,
    role: Callable[[
        str,
        str,
        str,
        int,
        docutils.parsers.rst.states.Inliner,
        Dict[str, object],
        List[object]], Tuple[
                List[docutils.nodes.Node],
                List[docutils.nodes.Node]]]) -> None: ...

from typing import Callable, Dict, List, Any, cast

from .types import FileId, Page, SerializableType


class SemanticParser:
    def __init__(self) -> None:
        pass

    def run(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        # Specify which transformations should be included in semantic postprocessing
        functions: List[Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]] = [
            self.toctree
        ]
        document: Dict[str, SerializableType] = {}

        for fn in functions:
            field: Dict[str, SerializableType] = fn(pages)
            document.update(field)
        return document

    def toctree(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        nodes: List[str] = []
        for fileid in pages:
            page = pages[fileid]
            ast: Dict[str, Any] = cast(Dict[str, Any], page.ast)
            find_toctree_nodes(ast, nodes)
        return {"toctreeNodes": nodes}


def find_toctree_nodes(node: Dict[str, Any], nodes: List[str]) -> None:

    if "children" not in node.keys():
        return

    if node["type"] == "directive":
        if len(node["children"]) == 0 and "entries" in node.keys():
            for toctree_node in node["entries"]:
                nodes.append(toctree_node)

    for child in node["children"]:
        find_toctree_nodes(child, nodes)

from typing import Callable, Dict, List, Any, cast

from .types import FileId, Page, SerializableType
import docutils.nodes


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
<<<<<<< HEAD
        fileid_dict = {}
        root: Dict[str, Any] = {"toctree": []}

        # Construct a {slug: fileid} mapping so that we can retrieve the full file name
        # given a slug. We cannot use the with_suffix method since the type of the slug
        # in find_toctree_nodes(...) is string rather than FileId.
        for fileid in pages:
            page_ast: Dict[str, Any] = cast(Dict[str, Any], pages[fileid].ast)
            slug = fileid.without_known_suffix
            fileid_dict[slug] = fileid

        # Build the toctree
        for fileid in pages:
            child: Dict["str", Any] = {}
            ast: Dict[str, Any] = cast(Dict[str, Any], pages[fileid].ast)
            find_toctree_nodes(fileid, ast, pages, child, fileid_dict)

            # If a toc sub-tree for this page exists, add it to the full tree
            if child:
                child["slug"] = fileid.without_known_suffix
                if "title" not in child:
                    child["title"] = ""
                root["toctree"].append(child)
        return root


def find_toctree_nodes(
    fileid: FileId,
    ast: Dict[str, Any],
    pages: Dict[FileId, Page],
    node: Dict[Any, Any],
    fileid_dict: Dict[str, FileId],
) -> None:
    if "children" not in ast.keys():
        return

    # Search for title
    if "title" not in node and ast["type"] == "section":
        section_child = ast["children"][0]
        for child in section_child["children"]:
            if child["type"] == "text":
                node["title"] = child["value"]

    if ast["type"] == "directive":
        if len(ast["children"]) == 0 and "entries" in ast.keys():
            node["children"] = ast["entries"]
            # Recursively build the tree for each toctree node in this entries list
            for toctree_node in node["children"]:
                if "slug" in toctree_node:
                    # Only recursively build the tree for internal links
                    slug = toctree_node["slug"][1:]
                    idx = slug.find(".")
                    if idx != -1:
                        slug = slug[:idx]
                    new_fileid = fileid_dict[slug]
                    new_ast: Dict[str, Any] = cast(
                        Dict[str, Any], pages[new_fileid].ast
                    )
                    find_toctree_nodes(
                        new_fileid, new_ast, pages, toctree_node, fileid_dict
                    )

    # Locate the correct directive object containing the toctree within this AST
    for child_ast in ast["children"]:
        find_toctree_nodes(fileid, child_ast, pages, node, fileid_dict)
=======
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
>>>>>>> 3b82b2c6e7c18c833593883b7cb14384106a3915

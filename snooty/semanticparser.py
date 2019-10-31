from typing import Callable, Dict, List, Any, cast
from .types import FileId, Page, SerializableType
import docutils.nodes


class SemanticParser:
    def __init__(self) -> None:
        pass

    def run(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        # Specify which transformations should be included in semantic postprocessing
        functions: List[Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]] = [
            self.toctree,
            self.slug_title
        ]
        document: Dict[str, SerializableType] = {}

        for fn in functions:
            field: Dict[str, SerializableType] = fn(pages)
            document.update(field)
        return document

    def slug_title(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        # Function which returns a dictionary of slug-title mappings
        slug_title_dict: Dict[str, SerializableType] = {}
        for file_id, page in pages.items():
            # remove the file extension from the slug
            slug = file_id.without_known_suffix

            # Skip slug-title mapping if the file is an `includes`
            if "includes" in slug or "images" in slug:
                continue

            # Parse for title
            title = ""
            ast: Dict[str, Any] = cast(Dict[str, Any], page.ast)
            title_is_set = False

            if ast is None:
                return {}

            for child in ast["children"]:
                if title_is_set:
                    break
                if child["type"] == "section":
                    for section_child in child["children"]:
                        if title_is_set:
                            break
                        if section_child["type"] == "heading":
                            for heading_child in section_child["children"]:
                                if title_is_set:
                                    break
                                if heading_child["type"] == "text":
                                    title = heading_child["value"]
                                    title_is_set = True
            slug_title_dict[slug] = title

        return {"slugToTitle": slug_title_dict}

    
    def toctree(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
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

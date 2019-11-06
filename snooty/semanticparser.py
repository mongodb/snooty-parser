from typing import Callable, Dict, List, Any, cast
from .types import FileId, Page, SerializableType, ProjectConfig
import re

PAT_FILE_EXTENSIONS = re.compile(r"\.((txt)|(rst)|(yaml))$")


class SemanticParser:
    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config = project_config

    def run(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        # Specify which transformations should be included in semantic postprocessing
        functions: List[Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]] = [
            self.toctree,
            self.slug_title,
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
        toctree: Dict[str, Any] = {"toctree": {}}

        # The toctree must begin at either `contents.txt` or `index.txt`.
        # Generally, repositories will have one or the other; but, if a repo has both,
        # the starting point will be `contents.txt`.
        starting_fileid: FileId = [
            fileid
            for fileid in pages.keys()
            if str(fileid) == "contents.txt" or str(fileid) == "index.txt"
        ][0]

        # Construct a {slug: fileid} mapping so that we can retrieve the full file name
        # given a slug. We cannot use the with_suffix method since the type of the slug
        # in find_toctree_nodes(...) is string rather than FileId.
        for fileid in pages:
            slug = fileid.without_known_suffix
            fileid_dict[slug] = fileid

        slug_title: Dict[str, Any] = cast(Dict[str, Any], self.slug_title(pages))[
            "slugToTitle"
        ]

        # Build the toctree
        root: Dict["str", Any] = {}
        ast: Dict[str, Any] = cast(Dict[str, Any], pages[starting_fileid].ast)
        find_toctree_nodes(starting_fileid, ast, pages, root, fileid_dict, slug_title)

        toctree["toctree"] = root
        toctree["toctree"]["title"] = self.project_config.name
        toctree["toctree"]["slug"] = "/"

        return toctree


# find_toctree_nodes is a helper function for SemanticParser.toctree that recursively builds the toctree
def find_toctree_nodes(
    fileid: FileId,
    ast: Dict[str, Any],
    pages: Dict[FileId, Page],
    node: Dict[Any, Any],
    fileid_dict: Dict[str, FileId],
    slug_title: Dict[str, Any],
) -> None:

    # Base case: create node in toctree
    if "children" not in ast.keys():
        if node:
            node["slug"] = fileid.without_known_suffix
            node["title"] = slug_title[node["slug"]]
        return

    if ast["type"] == "directive":
        if ast["name"] == "toctree" and "entries" in ast.keys():
            if "children" not in node:
                node["children"] = ast["entries"]
            else:
                node["children"].extend(ast["entries"])

            # Recursively build the tree for each toctree node in this entries list
            for toctree_node in node["children"]:
                if "slug" in toctree_node:
                    # Only recursively build the tree for internal links
                    slug = toctree_node["slug"]
                    if slug[0] == "/":
                        slug = slug[1:]
                    if slug[-1] == "/":
                        slug = slug[:-1]

                    # TODO: https://jira.mongodb.org/browse/DOCSP-7595
                    slug = PAT_FILE_EXTENSIONS.sub("", slug)

                    new_fileid = fileid_dict[slug]
                    new_ast: Dict[str, Any] = cast(
                        Dict[str, Any], pages[new_fileid].ast
                    )
                    find_toctree_nodes(
                        new_fileid,
                        new_ast,
                        pages,
                        toctree_node,
                        fileid_dict,
                        slug_title,
                    )

    # Locate the correct directive object containing the toctree within this AST
    for child_ast in ast["children"]:
        find_toctree_nodes(fileid, child_ast, pages, node, fileid_dict, slug_title)

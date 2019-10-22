import os

from typing import Callable, Dict, List, Any, cast

from .types import FileId, Page, SerializableType


class SemanticParser:
    def __init__(self) -> None:
        pass

    def run(self, pages: Dict[FileId, Page]) -> Dict[str, SerializableType]:
        # Specify which transformations should be included in semantic postprocessing
        functions: List[Callable[[Dict[FileId, Page]], Dict[str, SerializableType]]] = [
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
        for file_id in pages:
            page = pages[file_id]
            slug = str(page.source_path)

            # Get the relative path from the absolute paths of the current file and the page
            common_prefix = os.path.commonprefix([page.source_path, os.getcwd()])
            if common_prefix != "":
                slug = os.path.relpath(page.source_path, common_prefix)

                # remove the file extension from the slug
                ext_idx = slug.find(".")
                slug = slug[:ext_idx]

            # Skip slug-title mapping if the file is an `includes`
            if "includes" in slug:
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

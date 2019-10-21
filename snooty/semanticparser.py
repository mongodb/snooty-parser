import os
from typing import Callable, Dict, List
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
            index = pages[file_id]
            slug = str(index.source_path)

            # Get the relative path from the absolute paths of the current file and the index
            common_prefix = os.path.commonprefix([index.source_path, os.getcwd()])
            if common_prefix != "":
                slug = os.path.relpath(index.source_path, common_prefix)

            # Skip slug-title mapping if the file is an `includes`
            if "includes" in slug:
                continue

            # Parse for title
            if "header" not in index.source:
                title = ""
            else:
                token = "header:: "
                idx = index.source.find(token)
                header = index.source[idx:].split("\n")[0]
                title = header[len(token) :]
            slug_title_dict[slug] = title

        return slug_title_dict

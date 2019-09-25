import pymongo
from .types import Page, Diagnostic, FileId
from typing import Any, Dict, List, Iterator, Union
from typing_extensions import Protocol

__all__ = ("Backend", "MongoBackend")

#: A serializable type that allows for binary data
BSONSerializableType = Union[
    None, bool, str, bytes, int, float, Dict[str, Any], List[Any]
]


class StorageEngineCursor(Protocol):
    def __iter__(self) -> Iterator[Dict[str, BSONSerializableType]]:
        ...


class StorageEngineCollection(Protocol):
    def replace_one(
        self,
        filter: Dict[str, BSONSerializableType],
        replacement: Dict[str, BSONSerializableType],
        upsert: bool = True,
    ) -> None:
        ...

    def find(
        self,
        filter: Dict[str, BSONSerializableType],
        project: Dict[str, BSONSerializableType],
        cursor_type: pymongo.cursor.CursorType,
    ) -> StorageEngineCursor:
        ...


class StorageEngineDatabase(Protocol):
    def __getitem__(self, name: str) -> StorageEngineCollection:
        ...


class StorageEngineConnection(Protocol):
    def __getitem__(self, name: str) -> StorageEngineDatabase:
        ...


class Backend:
    """A simple base class for handling documents as snooty parses them."""

    def __init__(self) -> None:
        self.total_warnings = 0

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        for diagnostic in diagnostics:
            # Line numbers are currently... uh, "approximate"
            print(
                "{}({}:{}ish): {}".format(
                    diagnostic.severity_string.upper(),
                    path,
                    diagnostic.start[0],
                    diagnostic.message,
                )
            )
            self.total_warnings += 1

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        pass

    def on_delete(self, page_id: FileId) -> None:
        pass


class MongoBackend(Backend):
    """A backend that accepts a StorageEngineConnection interface, matching a
       subset of the interface of PyMongo."""

    def __init__(self, connection: StorageEngineConnection) -> None:
        super(MongoBackend, self).__init__()
        self.client = connection

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        checksums = list(
            asset.get_checksum() for asset in page.static_assets if asset.can_upload()
        )

        fully_qualified_pageid = "/".join(prefix + [page_id.with_suffix("").as_posix()])
        self.client["snooty"]["documents"].replace_one(
            {"_id": fully_qualified_pageid},
            {
                "_id": fully_qualified_pageid,
                "prefix": prefix,
                "ast": page.ast,
                "source": page.source,
                "static_assets": checksums,
            },
            upsert=True,
        )

        remote_assets = set(
            doc["_id"]
            for doc in self.client["snooty"]["assets"].find(
                {"_id": {"$in": checksums}},
                {"_id": True},
                cursor_type=pymongo.cursor.CursorType.EXHAUST,
            )
        )
        missing_assets = page.static_assets.difference(remote_assets)

        for static_asset in missing_assets:
            if not static_asset.can_upload():
                continue

            self.client["snooty"]["assets"].replace_one(
                {"_id": static_asset.get_checksum()},
                {
                    "_id": static_asset.get_checksum(),
                    "filename": str(static_asset.fileid),
                    "data": static_asset.data,
                },
                upsert=True,
            )

    def on_delete(self, page_id: FileId) -> None:
        pass

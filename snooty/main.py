"""Snooty.

Usage:
  snooty build <source-path> <mongodb-url> [(--commit=<commit_hash> |(--commit=<commit_hash> --patch=<patch_id>))]
  snooty watch <source-path>
  snooty language-server

Options:
  -h --help                 Show this screen.
  --commit=<commit_hash>    Commit hash of build.
  --patch=<patch_id>        Patch ID of build. Must be specified with a commit hash.
"""
import getpass
import logging
import sys
import pymongo
import watchdog.events
import watchdog.observers
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional, Union
from docopt import docopt
from pymongo.operations import IndexModel

from . import language_server
from .parser import Project, RST_EXTENSIONS
from .types import Page, Diagnostic, FileId, SerializableType

PATTERNS = ["*" + ext for ext in RST_EXTENSIONS] + ["*.yaml"]
logger = logging.getLogger(__name__)

PROD_DB = "snooty_prod"
TEST_DB = "snooty_test"
DB = PROD_DB

COLL_DOCUMENTS = "documents"
COLL_METADATA = "metadata"
COLL_ASSETS = "assets"


class ObserveHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, project: Project) -> None:
        super(ObserveHandler, self).__init__(patterns=PATTERNS)
        self.project = project

    def dispatch(self, event: watchdog.events.FileSystemEvent) -> None:
        if event.is_directory:
            return

        # Ignore non-text files; the Project handles changed static assets.
        # Eventually this logic should probably be moved into the Project's
        # filesystem monitor.
        if PurePath(event.src_path).suffix not in {".txt", ".rst", ".yaml"}:
            return

        if event.event_type in (
            watchdog.events.EVENT_TYPE_CREATED,
            watchdog.events.EVENT_TYPE_MODIFIED,
        ):
            logging.info("Rebuilding %s", event.src_path)
            self.project.update(Path(event.src_path))
        elif event.event_type == watchdog.events.EVENT_TYPE_DELETED:
            logging.info("Deleting %s", event.src_path)
            self.project.delete(Path(event.src_path))
        elif isinstance(event, watchdog.events.FileSystemMovedEvent):
            logging.info("Moving %s", event.src_path)
            self.project.delete(Path(event.src_path))
            self.project.update(Path(event.dest_path))
        else:
            assert False


class Backend:
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

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: Dict[str, Optional[str]],
        page_id: FileId,
        page: Page,
    ) -> None:
        pass

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: Dict[str, Optional[str]],
        field: Dict[str, SerializableType],
    ) -> None:
        pass

    def on_delete(
        self, page_id: FileId, build_identifiers: Dict[str, Optional[str]]
    ) -> None:
        pass


class MongoBackend(Backend):
    def __init__(self, connection: pymongo.MongoClient) -> None:
        super(MongoBackend, self).__init__()
        self.client = connection
        self._manage_indexes()

    def _manage_indexes(self) -> None:
        # List of indexes to be created. For now, metadata and documents collections use the same indexes.
        indexes = [
            IndexModel("page_id"),
            IndexModel(
                [("page_id", pymongo.ASCENDING), ("commit_hash", pymongo.ASCENDING)],
                sparse=True,
            ),
            IndexModel(
                [
                    ("page_id", pymongo.ASCENDING),
                    ("commit_hash", pymongo.ASCENDING),
                    ("patch_id", pymongo.ASCENDING),
                ],
                unique=True,
                sparse=True,
            ),
        ]

        self.client[DB][COLL_DOCUMENTS].create_indexes(indexes)
        self.client[DB][COLL_METADATA].create_indexes(indexes)

    def _construct_build_identifiers_filter(
        self, build_identifiers: Dict[str, Optional[str]]
    ) -> Dict[str, Union[str, Dict[str, Any]]]:
        filters: Dict[str, Union[str, Dict[str, Any]]] = {}
        for key, value in build_identifiers.items():
            if value:
                filters[key] = value
            else:
                filters[key] = {"$exists": False}
        return filters

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: Dict[str, Optional[str]],
        page_id: FileId,
        page: Page,
    ) -> None:
        checksums = list(
            asset.get_checksum() for asset in page.static_assets if asset.can_upload()
        )

        fully_qualified_pageid = "/".join(prefix + [page_id.without_known_suffix])

        # Construct filter for retrieving build documents
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": fully_qualified_pageid
        }
        document_filter.update(
            self._construct_build_identifiers_filter(build_identifiers)
        )

        self.client[DB][COLL_DOCUMENTS].replace_one(
            document_filter,
            {
                "page_id": fully_qualified_pageid,
                **{
                    key: value
                    for (key, value) in build_identifiers.items()
                    if value is not None
                },
                "prefix": prefix,
                "filename": page_id.as_posix(),
                "ast": page.ast,
                "source": page.source,
                "static_assets": checksums,
            },
            upsert=True,
        )

        remote_assets = set(
            doc["_id"]
            for doc in self.client[DB][COLL_ASSETS].find(
                {"_id": {"$in": checksums}},
                {"_id": True},
                cursor_type=pymongo.cursor.CursorType.EXHAUST,
            )
        )
        missing_assets = page.static_assets.difference(remote_assets)

        for static_asset in missing_assets:
            if not static_asset.can_upload():
                continue

            self.client[DB][COLL_ASSETS].replace_one(
                {"_id": static_asset.get_checksum()},
                {
                    "_id": static_asset.get_checksum(),
                    "filename": str(static_asset.fileid),
                    "data": static_asset.data,
                },
                upsert=True,
            )

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: Dict[str, Optional[str]],
        field: Dict[str, SerializableType],
    ) -> None:
        property_name = "/".join(prefix)

        # Construct filter for retrieving build documents
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": property_name
        }
        document_filter.update(
            self._construct_build_identifiers_filter(build_identifiers)
        )

        # Write to Atlas if field is not an empty dictionary
        if field:
            self.client[DB][COLL_METADATA].update_one(
                document_filter, {"$set": field}, upsert=True
            )

    def on_delete(
        self, page_id: FileId, build_identifiers: Dict[str, Optional[str]]
    ) -> None:
        pass


def _generate_build_identifiers(
    args: Dict[str, Optional[str]]
) -> Dict[str, Optional[str]]:
    identifiers = {}

    identifiers["commit_hash"] = args["--commit"]
    identifiers["patch_id"] = args["--patch"]

    return identifiers


def main() -> None:
    # docopt will terminate here and display usage instructions if snooty is run improperly
    args = docopt(__doc__)

    logging.basicConfig(level=logging.INFO)

    if args["language-server"]:
        language_server.start()
        return

    url = args["<mongodb-url>"]
    connection = (
        None if not url else pymongo.MongoClient(url, password=getpass.getpass())
    )
    backend = MongoBackend(connection) if connection else Backend()
    assert args["<source-path>"] is not None
    root_path = Path(args["<source-path>"])
    project = Project(root_path, backend, _generate_build_identifiers(args))

    try:
        project.build()

        if args["watch"]:
            observer = watchdog.observers.Observer()
            handler = ObserveHandler(project)
            logger.info("Watching for changes...")
            observer.schedule(handler, str(root_path), recursive=True)
            observer.start()
            observer.join()
    except KeyboardInterrupt:
        pass
    finally:
        if connection:
            print("Closing connection...")
            connection.close()

    if args["build"] and backend.total_warnings > 0:
        sys.exit(1)

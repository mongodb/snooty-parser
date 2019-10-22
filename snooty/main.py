import getpass
import logging
import sys
import pymongo
import re
import watchdog.events
import watchdog.observers
from pathlib import Path, PurePath
from typing import Dict, List

from . import language_server
from .gizaparser.published_branches import PublishedBranches
from .parser import Project, RST_EXTENSIONS
from .types import Page, Diagnostic, FileId, SerializableType

PATTERNS = ["*" + ext for ext in RST_EXTENSIONS] + ["*.yaml"]
PAT_FILE_EXTENSIONS = re.compile(r"\.((txt)|(rst)|(yaml))$")
logger = logging.getLogger(__name__)


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

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        pass

    def on_update_metadata(
        self, prefix: List[str], field: Dict[str, SerializableType]
    ) -> None:
        pass

    def on_delete(self, page_id: FileId) -> None:
        pass

    def on_published_branches(
        self, prefix: List[str], published_branches: PublishedBranches
    ) -> None:
        pass


class MongoBackend(Backend):
    def __init__(self, connection: pymongo.MongoClient) -> None:
        super(MongoBackend, self).__init__()
        self.client = connection

    def on_update(self, prefix: List[str], page_id: FileId, page: Page) -> None:
        checksums = list(
            asset.get_checksum() for asset in page.static_assets if asset.can_upload()
        )

        # Manually strip file extensions so that filenames that contain periods are not truncated
        page_id = page_id.with_name(PAT_FILE_EXTENSIONS.sub("", page_id.name))
        fully_qualified_pageid = "/".join(prefix + [page_id.as_posix()])

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

    def on_update_metadata(
        self, prefix: List[str], field: Dict[str, SerializableType]
    ) -> None:
        property_name = "/".join(prefix)
        # Write to Atlas if field is not an empty dictionary
        if field:
            self.client["snooty"]["metadata"].update_one(
                {"_id": property_name}, {"$set": field}, upsert=True
            )

    def on_delete(self, page_id: FileId) -> None:
        pass

    def on_published_branches(
        self, prefix: List[str], published_branches: PublishedBranches
    ) -> None:
        page_id = "/".join(prefix)
        self.client["snooty"]["metadata"].replace_one(
            {"_id": page_id},
            {"publishedBranches": published_branches.serialize()},
            upsert=True,
        )


def usage(exit_code: int) -> None:
    """Exit and print usage information."""
    print(
        "Usage: {} <build|watch|language-server> <source-path> <mongodb-url>".format(
            sys.argv[0]
        )
    )
    sys.exit(exit_code)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) == 2 and sys.argv[1] == "language-server":
        language_server.start()
        return

    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("watch", "build"):
        usage(1)

    url = sys.argv[3] if len(sys.argv) == 4 else None
    connection = (
        None if not url else pymongo.MongoClient(url, password=getpass.getpass())
    )
    backend = MongoBackend(connection) if connection else Backend()
    root_path = Path(sys.argv[2])
    project = Project(root_path, backend)

    try:
        project.build()

        if sys.argv[1] == "watch":
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

    if sys.argv[1] == "build" and backend.total_warnings > 0:
        sys.exit(1)

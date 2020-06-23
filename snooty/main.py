"""Snooty.

Usage:
  snooty build <source-path> [<mongodb-url>] [--commit=<commit_hash> | (--commit=<commit_hash> --patch=<patch_id>)]
  snooty watch <source-path>
  snooty language-server

Options:
  -h --help                 Show this screen.
  --commit=<commit_hash>    Commit hash of build.
  --patch=<patch_id>        Patch ID of build. Must be specified with a commit hash.

Environment variables:
  SNOOTY_PARANOID           0, 1 where 0 is default
  DIAGNOSTICS_FORMAT        JSON, text where text is default

"""
import getpass
import logging
import os
import pymongo
import sys
import toml
import json
import watchdog.events
import watchdog.observers
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional, Union
from docopt import docopt

from . import language_server
from .parser import Project
from .util import SOURCE_FILE_EXTENSIONS
from .types import FileId, SerializableType, BuildIdentifierSet
from .page import Page
from .diagnostics import Diagnostic

PARANOID_MODE = os.environ.get("SNOOTY_PARANOID", "0") == "1"
PATTERNS = ["*" + ext for ext in SOURCE_FILE_EXTENSIONS]
logger = logging.getLogger(__name__)
SNOOTY_ENV = os.getenv("SNOOTY_ENV", "development")
PACKAGE_ROOT = Path(sys.modules["snooty"].__file__).resolve().parent
if PACKAGE_ROOT.is_file():
    PACKAGE_ROOT = PACKAGE_ROOT.parent

COLL_DOCUMENTS = "documents"
COLL_METADATA = "metadata"
COLL_ASSETS = "assets"

EXIT_STATUS_ERROR_DIAGNOSTICS = 2


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
        if PurePath(event.src_path).suffix not in SOURCE_FILE_EXTENSIONS:
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
        self.total_errors = 0

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        output = os.environ.get("DIAGNOSTICS_FORMAT", "text")

        for diagnostic in diagnostics:
            info = diagnostic.serialize()
            info["path"] = path.as_posix()

            if output == "JSON":
                document = {"diagnostic": info}
                print(json.dumps(document))
            else:
                print("{severity}({path}:{start}ish): {message}".format(**info))

            if diagnostic.severity >= Diagnostic.Level.error:
                self.total_errors += 1

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        if PARANOID_MODE:
            page.ast.verify()

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        pass

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        pass


def construct_build_identifiers_filter(
    build_identifiers: BuildIdentifierSet
) -> Dict[str, Union[str, Dict[str, Any]]]:
    """Given a dictionary of build identifiers associated with build, construct
    a filter to properly query MongoDB for associated documents.
    """
    return {
        key: (value if value else {"$exists": False})
        for (key, value) in build_identifiers.items()
    }


class MongoBackend(Backend):
    def __init__(self, connection: pymongo.MongoClient) -> None:
        super(MongoBackend, self).__init__()
        self.client = connection
        self.db = self._config_db()

    def _config_db(self) -> str:
        with PACKAGE_ROOT.joinpath("config.toml").open(encoding="utf-8") as f:
            config = toml.load(f)
            db_name = config["environments"][SNOOTY_ENV]["db"]
            assert isinstance(db_name, str)
            return db_name

    def on_update(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        page: Page,
    ) -> None:
        super().on_update(prefix, build_identifiers, page_id, page)
        checksums = list(
            asset.get_checksum() for asset in page.static_assets if asset.can_upload()
        )

        fully_qualified_pageid = "/".join(prefix + [page_id.without_known_suffix])

        # Construct filter for retrieving build documents
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": fully_qualified_pageid,
            **construct_build_identifiers_filter(build_identifiers),
        }

        document = {
            "page_id": fully_qualified_pageid,
            **{
                key: value
                for (key, value) in build_identifiers.items()
                if value is not None
            },
            "prefix": prefix,
            "filename": page_id.as_posix(),
            "ast": page.ast.serialize(),
            "source": page.source,
            "static_assets": checksums,
        }

        if page.query_fields:
            document.update({"query_fields": page.query_fields})

        self.client[self.db][COLL_DOCUMENTS].replace_one(
            document_filter, document, upsert=True
        )

        remote_assets = set(
            doc["_id"]
            for doc in self.client[self.db][COLL_ASSETS].find(
                {"_id": {"$in": checksums}},
                {"_id": True},
                cursor_type=pymongo.cursor.CursorType.EXHAUST,
            )
        )
        missing_assets = page.static_assets.difference(remote_assets)

        for static_asset in missing_assets:
            if not static_asset.can_upload():
                continue

            self.client[self.db][COLL_ASSETS].replace_one(
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
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        property_name = "/".join(prefix)

        # Construct filter for retrieving build documents
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": property_name,
            **construct_build_identifiers_filter(build_identifiers),
        }

        # Write to Atlas if field is not an empty dictionary
        if field:
            self.client[self.db][COLL_METADATA].update_one(
                document_filter, {"$set": field}, upsert=True
            )

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        pass


def _generate_build_identifiers(args: Dict[str, Optional[str]]) -> BuildIdentifierSet:
    identifiers = {}

    identifiers["commit_hash"] = args["--commit"]
    identifiers["patch_id"] = args["--patch"]

    return identifiers


def main() -> None:
    # docopt will terminate here and display usage instructions if snooty is run improperly
    args = docopt(__doc__)

    logging.basicConfig(level=logging.INFO)

    if PARANOID_MODE:
        logger.info("Paranoid mode on")

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

    if project.config.fail_on_diagnostics:
        EXIT_STATUS_ERROR_DIAGNOSTICS = 1

    if args["build"] and backend.total_errors > 0:
        sys.exit(EXIT_STATUS_ERROR_DIAGNOSTICS)

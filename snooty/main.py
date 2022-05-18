"""Snooty.

Usage:
  snooty build [--no-caching] <source-path> [<mongodb-url>] [--output=<path>] [options]
  snooty watch [--no-caching] <source-path>
  snooty [--no-caching] language-server

Options:
  -h --help                 Show this screen.
  --output=<path>             The path to which the output manifest should be written.
  --commit=<commit_hash>    Commit hash of build.
  --patch=<patch_id>        Patch ID of build. Must be specified with a commit hash.
  --no-caching              Disable HTTP response caching.
  --rstspec=<url>           Override the reStructuredText directive & role spec.

Environment variables:
  SNOOTY_PARANOID           0, 1 where 0 is default
  DIAGNOSTICS_FORMAT        JSON, text where text is default
  SNOOTY_PERF_SUMMARY       0, 1 where 0 is default

"""
import getpass
import json
import logging
import multiprocessing
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional, Set, Union

import bson
import pymongo
import tomli
import watchdog.events
import watchdog.observers
from docopt import docopt

from . import __version__, language_server, specparser
from .diagnostics import Diagnostic, MakeCorrectionMixin
from .n import FileId, SerializableType
from .page import Page
from .parser import Project, ProjectBackend
from .types import BuildIdentifierSet, ProjectConfig
from .util import PACKAGE_ROOT, SOURCE_FILE_EXTENSIONS, HTTPCache, PerformanceLogger

PARANOID_MODE = os.environ.get("SNOOTY_PARANOID", "0") == "1"
PATTERNS = ["*" + ext for ext in SOURCE_FILE_EXTENSIONS]
logger = logging.getLogger(__name__)
SNOOTY_ENV = os.getenv("SNOOTY_ENV", "development")

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


class Backend(ProjectBackend):
    def __init__(self) -> None:
        self.total_errors = 0
        self.assets_written: Set[str] = set()

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        output = os.environ.get("DIAGNOSTICS_FORMAT", "text")

        for diagnostic in diagnostics:
            did_you_mean: List[str] = []
            info = diagnostic.serialize()
            info["path"] = path.as_posix()

            if isinstance(diagnostic, MakeCorrectionMixin):
                did_you_mean = diagnostic.did_you_mean()
                info["did_you_mean"] = did_you_mean

            if output == "JSON":
                document: Dict[str, object] = {"diagnostic": info}
                print(json.dumps(document))
            else:
                print("{severity}({path}:{start}ish): {message}".format(**info))
                for candidate in did_you_mean:
                    print("    Did you mean: " + candidate)

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

        fully_qualified_pageid = "/".join(prefix + [page_id.without_known_suffix])

        uploadable_assets = [
            asset for asset in page.static_assets if asset.can_upload()
        ]

        document = {
            "page_id": fully_qualified_pageid,
            "filename": page_id.as_posix(),
            "ast": page.ast.serialize(),
            "source": page.source,
            "static_assets": [
                {"checksum": asset.get_checksum(), "key": asset.key}
                for asset in uploadable_assets
            ],
        }

        if page.query_fields:
            document.update({"query_fields": page.query_fields})

        self.handle_document(build_identifiers, page_id.without_known_suffix, document)

        for static_asset in uploadable_assets:
            checksum = static_asset.get_checksum()
            if checksum in self.assets_written:
                continue

            self.assets_written.add(checksum)
            self.handle_asset(checksum, static_asset.data)

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        pass

    def on_delete(self, page_id: FileId, build_identifiers: BuildIdentifierSet) -> None:
        pass

    def flush(self) -> None:
        pass

    def handle_document(
        self,
        build_identifiers: BuildIdentifierSet,
        fully_qualified_pageid: str,
        document: Dict[str, Any],
    ) -> None:
        pass

    def handle_asset(self, checksum: str, asset: Union[str, bytes]) -> None:
        pass


class MongoBackend(Backend):
    def __init__(self, connection: pymongo.MongoClient) -> None:
        super(MongoBackend, self).__init__()
        self.client = connection
        self.db = self._config_db()

        self.pending_writes: Dict[
            str, List[Union[pymongo.UpdateOne, pymongo.ReplaceOne]]
        ] = defaultdict(list)

    def _config_db(self) -> str:
        with PACKAGE_ROOT.joinpath("config.toml").open("rb") as f:
            config = tomli.load(f)
            db_name = config["environments"][SNOOTY_ENV]["db"]
            assert isinstance(db_name, str)
            return db_name

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        property_name_with_prefix = "/".join(prefix)

        # Construct filter for retrieving build documents
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": property_name_with_prefix,
            **self.construct_build_identifiers_filter(build_identifiers),
        }

        # Write to Atlas if field is not an empty dictionary
        if field:
            field["created_at"] = datetime.utcnow()
            self.client[self.db][COLL_METADATA].update_one(
                document_filter, {"$set": field}, upsert=True
            )

    def flush(self) -> None:
        for collection_name, pending_writes in self.pending_writes.items():
            self.client[self.db][collection_name].bulk_write(
                pending_writes, ordered=False
            )
        self.pending_writes.clear()

    def handle_document(
        self,
        build_identifiers: BuildIdentifierSet,
        fully_qualified_pageid: str,
        document: Dict[str, Any],
    ) -> None:
        document_filter: Dict[str, Union[str, Dict[str, Any]]] = {
            "page_id": fully_qualified_pageid,
            **self.construct_build_identifiers_filter(build_identifiers),
        }

        self.pending_writes[COLL_DOCUMENTS].append(
            pymongo.ReplaceOne(document_filter, document, upsert=True)
        )

    def handle_asset(self, checksum: str, data: Union[str, bytes]) -> None:
        self.pending_writes[COLL_ASSETS].append(
            pymongo.UpdateOne(
                {"_id": checksum},
                {
                    "$setOnInsert": {
                        "_id": checksum,
                        "data": data,
                    }
                },
                upsert=True,
            )
        )

    def close(self) -> None:
        if self.client:
            print("Closing connection...")
            self.client.close()

    @staticmethod
    def construct_build_identifiers_filter(
        build_identifiers: BuildIdentifierSet,
    ) -> Dict[str, Union[str, Dict[str, Any]]]:
        """Given a dictionary of build identifiers associated with build, construct
        a filter to properly query MongoDB for associated documents.
        """
        return {
            key: (value if value else {"$exists": False})
            for (key, value) in build_identifiers.items()
        }


class ZipBackend(Backend):
    def __init__(self, zip: zipfile.ZipFile) -> None:
        super(ZipBackend, self).__init__()
        self.zip = zip
        self.metadata: Dict[str, SerializableType] = {}
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)
        self.assets_written: Set[str] = set()

    def on_config(self, config: ProjectConfig) -> None:
        self.metadata["project"] = config.name

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        if not diagnostics:
            return

        super().on_diagnostics(path, diagnostics)
        self.diagnostics[path].extend(diagnostics)

    def handle_document(
        self,
        build_identifiers: BuildIdentifierSet,
        fully_qualified_pageid: str,
        document: Dict[str, Any],
    ) -> None:
        self.zip.writestr(
            f"documents/{fully_qualified_pageid}.bson", bson.encode(document)
        )

    def handle_asset(self, checksum: str, data: Union[str, bytes]) -> None:
        self.zip.writestr(f"assets/{checksum}", data)

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        if field:
            self.metadata.update(field)

    def flush(self) -> None:
        for key, diagnostics in self.diagnostics.items():
            self.zip.writestr(
                f"diagnostics/{key.as_posix()}.bson",
                bson.encode(
                    {
                        "diagnostics": [
                            diagnostic.serialize() for diagnostic in diagnostics
                        ]
                    }
                ),
            )

    def close(self) -> None:
        self.zip.writestr("site.bson", bson.encode(self.metadata))
        self.zip.close()


def _generate_build_identifiers(args: Dict[str, Optional[str]]) -> BuildIdentifierSet:
    identifiers = {}

    identifiers["commit_hash"] = args["--commit"]
    identifiers["patch_id"] = args["--patch"]

    return identifiers


def main() -> None:
    multiprocessing.freeze_support()

    # docopt will terminate here and display usage instructions if snooty is run improperly
    args = docopt(__doc__)

    logging.basicConfig(level=logging.INFO)

    if args["--no-caching"]:
        HTTPCache.initialize(False)

    logger.info(f"Snooty {__version__} starting")

    if args["--rstspec"]:
        rstspec_path = args["--rstspec"]
        if rstspec_path.startswith("https://") or rstspec_path.startswith("http://"):
            rstspec_bytes = HTTPCache.singleton().get(args["--rstspec"])
            rstspec_text = str(rstspec_bytes, "utf-8")
        else:
            rstspec_text = Path(rstspec_path).read_text(encoding="utf-8")
        specparser.Spec.initialize(rstspec_text)

    if PARANOID_MODE:
        logger.info("Paranoid mode on")

    if args["language-server"]:
        language_server.start()
        return

    url = args["<mongodb-url>"]
    output_path = args["--output"]

    connection: Optional[pymongo.MongoClient] = None

    if url:
        connection = pymongo.MongoClient(url, password=getpass.getpass())
        backend: Backend = MongoBackend(connection)
    elif output_path:
        zf = zipfile.ZipFile(output_path, mode="w")
        backend = ZipBackend(zf)
    else:
        backend = Backend()

    assert args["<source-path>"] is not None
    root_path = Path(args["<source-path>"])
    project = Project(root_path, backend, _generate_build_identifiers(args))

    try:
        project.build()

        if os.environ.get("SNOOTY_PERF_SUMMARY", "0") == "1":
            PerformanceLogger.singleton().print(sys.stderr)

        if args["watch"]:
            observer = watchdog.observers.Observer()
            handler = ObserveHandler(project)
            logger.info("Watching for changes...")
            observer.schedule(handler, str(root_path), recursive=True)
            observer.start()
            observer.join()
    except KeyboardInterrupt:
        pass
    except:
        if output_path:
            os.unlink(output_path)
        raise
    finally:
        backend.close()

    if args["build"] and backend.total_errors > 0:
        exit_code = (
            1 if project.config.fail_on_diagnostics else EXIT_STATUS_ERROR_DIAGNOSTICS
        )
        sys.exit(exit_code)

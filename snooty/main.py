"""Snooty.

Usage:
  snooty build [--no-caching]               <source-path> [--output=<path>] [options]
  snooty create-cache [--no-caching]        <source-path> [options]
  snooty [--no-caching] language-server

Options:
  -h --help                 Show this screen.
  --output=<path>           The path to which the output manifest should be written.
  --commit=<commit_hash>    Commit hash of build.
  --patch=<patch_id>        Patch ID of build. Must be specified with a commit hash.
  --no-caching              Disable HTTP response caching.
  --rstspec=<url>           Override the reStructuredText directive & role spec.

Environment variables:
  SNOOTY_PARANOID           0, 1 where 0 is default
  DIAGNOSTICS_FORMAT        JSON, text where text is default
  SNOOTY_PERF_SUMMARY       0, 1 where 0 is default

"""

import json
import logging
import multiprocessing
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import bson
from docopt import docopt

from . import __version__, language_server, specparser
from .diagnostics import Diagnostic, MakeCorrectionMixin
from .n import FileId, SerializableType
from .page import Page
from .parser import Project, ProjectBackend, ProjectLoadError
from .types import BuildIdentifierSet, ProjectConfig
from .util import EXT_FOR_PAGE, SOURCE_FILE_EXTENSIONS, HTTPCache, PerformanceLogger

PARANOID_MODE = os.environ.get("SNOOTY_PARANOID", "0") == "1"
PATTERNS = ["*" + ext for ext in SOURCE_FILE_EXTENSIONS]
logger = logging.getLogger(__name__)

EXIT_STATUS_ERROR_DIAGNOSTICS = 2


class Backend(ProjectBackend):
    def __init__(self) -> None:
        self.total_errors = 0
        self.total_diagnostics = 0
        self.total_pages = 0
        self.assets_written: Set[str] = set()

    def on_progress(self, progress: int, total: int, message: str) -> None:
        pass

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        output = os.environ.get("DIAGNOSTICS_FORMAT", "text")
        self.total_diagnostics += len(diagnostics)

        for diagnostic in diagnostics:
            did_you_mean: List[str] = []
            info = diagnostic.serialize()
            info["path"] = path.as_posix()

            if isinstance(diagnostic, MakeCorrectionMixin):
                did_you_mean = diagnostic.did_you_mean()
                if did_you_mean:
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

        # Sort for repeatable builds
        uploadable_assets.sort(key=lambda asset: asset.key)

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
        if page.facets:
            document["facets"] = [facet.serialize() for facet in page.facets]

        self.handle_document(
            build_identifiers, page_id, fully_qualified_pageid, document
        )

        for static_asset in uploadable_assets:
            checksum = static_asset.get_checksum()
            if static_asset.diagnostics:
                self.on_diagnostics(page_id, static_asset.diagnostics)
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
        page_id: FileId,
        fully_qualified_pageid: str,
        document: Dict[str, Any],
    ) -> None:
        if page_id.suffix != EXT_FOR_PAGE:
            return
        self.total_pages += 1

    def handle_asset(self, checksum: str, asset: Union[str, bytes]) -> None:
        pass


class ZipBackend(Backend):
    def __init__(self, zip: zipfile.ZipFile) -> None:
        super(ZipBackend, self).__init__()
        self.zip = zip
        self.metadata: Dict[str, SerializableType] = {}
        self.diagnostics: Dict[FileId, List[Diagnostic]] = defaultdict(list)
        self.assets_written: Set[str] = set()

    def on_config(self, config: ProjectConfig, branch: str) -> None:
        self.metadata["project"] = config.name
        self.metadata["branch"] = branch

    def on_diagnostics(self, path: FileId, diagnostics: List[Diagnostic]) -> None:
        if not diagnostics:
            return

        super().on_diagnostics(path, diagnostics)
        self.diagnostics[path].extend(diagnostics)

    def handle_document(
        self,
        build_identifiers: BuildIdentifierSet,
        page_id: FileId,
        fully_qualified_pageid: str,
        document: Dict[str, Any],
    ) -> None:
        if page_id.suffix != EXT_FOR_PAGE:
            return
        super().handle_document(
            build_identifiers, page_id, fully_qualified_pageid, document
        )
        info = zipfile.ZipInfo(f"documents/{page_id.without_known_suffix}.bson")
        self.zip.writestr(info, bson.encode(document))

    def handle_asset(self, checksum: str, data: Union[str, bytes]) -> None:
        info = zipfile.ZipInfo(f"assets/{checksum}")
        self.zip.writestr(info, data)

    def on_update_metadata(
        self,
        prefix: List[str],
        build_identifiers: BuildIdentifierSet,
        field: Dict[str, SerializableType],
    ) -> None:
        if field:
            self.metadata.update(field)

    def flush(self) -> None:
        # Pages can have their diagnostics inserted in any order. Sort for repeatability.
        sorted_keys = sorted(self.diagnostics.keys())

        for key in sorted_keys:
            diagnostics = self.diagnostics[key]
            # ZipInfo defaults to a timestamp of 1980. We do not want to encode the actual mtime
            # to ensure repeatable builds.
            info = zipfile.ZipInfo(f"diagnostics/{key.as_posix()}.bson")

            self.zip.writestr(
                info,
                bson.encode(
                    {
                        "diagnostics": [
                            diagnostic.serialize() for diagnostic in diagnostics
                        ]
                    }
                ),
            )

    def close(self) -> None:
        zipinfo = zipfile.ZipInfo("site.bson")
        self.zip.writestr(zipinfo, bson.encode(self.metadata))
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

    no_caching = args["--no-caching"]
    if no_caching:
        HTTPCache.initialize(False)

    logger.info(f"Snooty {__version__} starting")

    if args["--rstspec"]:
        rstspec_path = args["--rstspec"]
        if rstspec_path.startswith("https://") or rstspec_path.startswith("http://"):
            rstspec_bytes = HTTPCache.singleton().get(args["--rstspec"])
            rstspec_text = str(rstspec_bytes, "utf-8")
        else:
            rstspec_text = Path(rstspec_path).expanduser().read_text(encoding="utf-8")
        specparser.Spec.initialize(rstspec_text)

    if PARANOID_MODE:
        logger.info("Paranoid mode on")

    if args["language-server"]:
        language_server.start()
        return

    output_path = args["--output"]

    if output_path:
        zf = zipfile.ZipFile(os.path.expanduser(output_path), mode="w")
        backend: Backend = ZipBackend(zf)
    else:
        backend = Backend()

    assert args["<source-path>"] is not None
    root_path = Path(args["<source-path>"])

    try:
        project = Project(root_path, backend, _generate_build_identifiers(args))
    except ProjectLoadError:
        # Close out the backend so that load diagnostics get reported
        backend.close()
        sys.exit(1)

    if not no_caching:
        project.load_cache()

    try:
        project.build()

        if args["create-cache"]:
            with PerformanceLogger.singleton().start("persist cache"):
                project.update_cache()

        if os.environ.get("SNOOTY_PERF_SUMMARY", "0") == "1":
            PerformanceLogger.singleton().print(sys.stderr)
    except KeyboardInterrupt:
        pass
    except:
        if output_path:
            os.unlink(output_path)
        raise
    finally:
        backend.close()

        print(
            f"{backend.total_diagnostics} diagnostics; {backend.total_pages} pages; {len(backend.assets_written)} assets"
        )

    exit_code = 0
    if args["build"] and backend.total_errors > 0:
        exit_code = (
            1 if project.config.fail_on_diagnostics else EXIT_STATUS_ERROR_DIAGNOSTICS
        )

    sys.exit(exit_code)

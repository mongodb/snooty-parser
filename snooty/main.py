import getpass
import logging
import sys
import pymongo
import watchdog.events
import watchdog.observers
from pathlib import Path, PurePath

from . import language_server
from . import backends
from .parser import Project, RST_EXTENSIONS

PATTERNS = ["*" + ext for ext in RST_EXTENSIONS] + ["*.yaml"]
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
    backend = backends.MongoBackend(connection) if connection else backends.Backend()
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

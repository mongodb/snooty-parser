import datetime
import logging
import urllib
import requests
from email.utils import formatdate
from time import mktime
from pathlib import Path
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)
DEFAULT_CACHE_DIR = Path.home().joinpath(".cache", "snooty")


def download_url(
    url: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> Tuple[str, Path, bytes]:
    """Fetch a URL, or use a locally cached copy if it is still valid."""
    logger.debug(f"Fetching inventory: {url}")

    base_url = url.rsplit("/", 1)[0]
    base_url.rstrip("/")
    base_url += "/"

    # Make our user's cache directory if it doesn't exist
    parsed_url = urllib.parse.urlparse(url)
    filename = "".join(
        char for char in parsed_url.netloc + parsed_url.path if char.isalnum()
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = cache_dir.joinpath(filename)

    # Only re-request if more than an hour old
    request_headers: Dict[str, str] = {}
    mtime: Optional[datetime.datetime] = None
    try:
        mtime = datetime.datetime.fromtimestamp(inventory_path.stat().st_mtime)
    except FileNotFoundError:
        pass

    if mtime is not None:
        if (datetime.datetime.now() - mtime) < datetime.timedelta(hours=1):
            request_headers["If-Modified-Since"] = formatdate(mktime(mtime.timetuple()))

    res = requests.get(url, headers=request_headers)
    res.raise_for_status()
    if res.status_code == 304:
        return base_url, inventory_path, inventory_path.read_bytes()

    with open(inventory_path, "wb") as f:
        f.write(res.content)

    return base_url, inventory_path, res.content

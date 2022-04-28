from . import operations
from .database import Database
from typing import Optional

UpdateOne = operations.UpdateOne
ReplaceOne = operations.ReplaceOne


class MongoClient:
    def __init__(self, url: str, password: Optional[str]=None) -> None: ...
    def __getitem__(self, name: str) -> Database: ...
    def close(self) -> None: ...

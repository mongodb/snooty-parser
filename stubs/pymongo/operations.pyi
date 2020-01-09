from typing import List, Optional, Tuple, Union

class IndexModel(object):
    def __init__(self, keys: Union[str, List[Tuple[str, int]]], unique: Optional[bool]=False, sparse: Optional[bool]=False) -> None: ...

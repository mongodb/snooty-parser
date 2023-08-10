from dataclasses import asdict, dataclass
from typing import ClassVar, List, Optional, Tuple

import tomli

from . import util
from .flutter import check_type, checked


@checked
@dataclass
class FacetDefinition:
    name: str
    display_name: Optional[str]


@checked
@dataclass
class TargetPlatformDefinition:
    name: str
    display_name: Optional[str]
    sub_platforms: Optional[List[FacetDefinition]]
    versions: Optional[List[FacetDefinition]]


@checked
@dataclass
class TaxonomySpec:
    genres: List[FacetDefinition]
    target_platforms: List[TargetPlatformDefinition]
    programming_languages: List[FacetDefinition]

    TAXONOMY_SPEC: ClassVar[Optional["TaxonomySpec"]] = None

    @classmethod
    def get_taxonomy(cls) -> "TaxonomySpec":
        if not cls.TAXONOMY_SPEC:
            path = util.PACKAGE_ROOT.joinpath("taxonomy.toml")
            taxonomy = check_type(cls, tomli.loads(path.read_text(encoding="utf-8")))
            cls.TAXONOMY_SPEC = taxonomy
        return cls.TAXONOMY_SPEC

    @classmethod
    def validate_key_value_pairs(cls, facet_str_pairs: List[Tuple[str, str]]) -> None:
        taxonomy_ref = asdict(cls.get_taxonomy())
        try:
            while len(facet_str_pairs) > 0:
                key, value = facet_str_pairs.pop()
                list_values = taxonomy_ref[key] or []
                found_values = [
                    x for x in list_values if x == value or x["name"] == value
                ]
                taxonomy_ref = found_values[0]
        except Exception as e:
            raise KeyError(e)

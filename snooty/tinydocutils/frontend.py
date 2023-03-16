# $Id: frontend.py 8676 2021-04-08 16:36:09Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
Command-line and common processing for Docutils front-end tools.

Exports the following classes:

* `OptionParser`: Standard Docutils command-line processing.
* `Option`: Customized version of `optparse.Option`; validation support.
* `Values`: Runtime settings; objects are simple structs
  (``object.attribute``).  Supports cumulative list settings (attributes).
* `ConfigParser`: Standard Docutils config file processing.

Also exports the following functions:

* Option callbacks: `store_multiple`, `read_config_file`.
* Setting validators: `validate_encoding`,
  `validate_encoding_error_handler`,
  `validate_encoding_and_error_handler`,
  `validate_boolean`, `validate_ternary`, `validate_threshold`,
  `validate_colon_separated_list`,
  `validate_comma_separated_list`
* `make_paths_absolute`.
* SettingSpec manipulation: `filter_settings_spec`.
"""

__docformat__ = "reStructuredText"

import sys
from typing import Dict, Optional, Sequence


class OptionParser:
    thresholds = {"info": 1, "warning": 2, "error": 3, "severe": 4, "none": 5}

    def __init__(self, components: Sequence[object] = ()) -> None:
        self.components = components
        self.warning_stream = sys.stderr
        self.debug = False
        self.error_encoding = "utf-8"

        self.settings: Dict[str, Optional[str]] = {}

        self.halt_level = 5
        self.report_level = 1
        self.trim_footnote_reference_space = False
        self.tab_width = 8
        self.language_code = "en"
        self.id_prefix = ""
        self.auto_id_prefix = "id"

        self.file_insertion_enabled = False
        self.raw_enabled = False
        self.line_length_limit = 10000

    def get_default_values(self) -> "OptionParser":
        return self

    def setdefault(self, key: str, value: Optional[str]) -> Optional[str]:
        return self.settings.setdefault(key, value)

    def __setitem__(self, key: str, value: Optional[str]) -> None:
        self.settings[key] = value

    def get(self, key: str) -> Optional[str]:
        return self.settings.get(key, None)

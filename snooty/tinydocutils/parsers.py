# $Id: __init__.py 8671 2021-04-07 12:09:51Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
This package contains Docutils parser modules.
"""

__docformat__ = "reStructuredText"

from . import nodes


class Parser:
    def parse(self, inputstring: str, document: nodes.document) -> None:
        """Override to parse `inputstring` into document tree `document`."""
        raise NotImplementedError("subclass must override this method")

    def setup_parse(self, inputstring: str, document: nodes.document) -> None:
        """Initial parse setup.  Call at start of `self.parse()`."""
        self.inputstring = inputstring
        self.document = document

    def finish_parse(self) -> None:
        """Finalize parse details.  Call at end of `self.parse()`."""
        pass

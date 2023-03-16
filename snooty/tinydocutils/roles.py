# $Id: roles.py 7937 2016-05-24 10:48:48Z milde $
# Author: Edward Loper <edloper@gradient.cis.upenn.edu>
# Copyright: This module has been placed in the public domain.

"""
This module defines standard interpreted text role functions, a registry for
interpreted text roles, and an API for adding to and retrieving from the
registry.

The interface for interpreted role functions is as follows::

    def role_fn(name, rawtext, text, lineno, inliner,
                options={}, content=[]):
        code...

    # Set function attributes for customization:
    role_fn.options = ...
    role_fn.content = ...

Parameters:

- ``name`` is the local name of the interpreted text role, the role name
  actually used in the document.

- ``rawtext`` is a string containing the entire interpreted text construct.
  Return it as a ``problematic`` node linked to a system message if there is a
  problem.

- ``text`` is the interpreted text content, with backslash escapes converted
  to nulls (``\x00``).

- ``lineno`` is the line number where the interpreted text beings.

- ``inliner`` is the Inliner object that called the role function.
  It defines the following useful attributes: ``reporter``,
  ``problematic``, ``memo``, ``parent``, ``document``.

- ``options``: A dictionary of directive options for customization, to be
  interpreted by the role function.  Used for additional attributes for the
  generated elements and other functionality.

- ``content``: A list of strings, the directive content for customization
  ("role" directive).  To be interpreted by the role function.

Function attributes for customization, interpreted by the "role" directive:

- ``options``: A dictionary, mapping known option names to conversion
  functions such as `int` or `float`.  ``None`` or an empty dict implies no
  options to parse.  Several directive option conversion functions are defined
  in the `directives` module.

  All role functions implicitly support the "class" option, unless disabled
  with an explicit ``{'class': None}``.

- ``content``: A boolean; true if content is allowed.  Client code must handle
  the case where content is required but not supplied (an empty content list
  will be supplied).

Note that unlike directives, the "arguments" function attribute is not
supported for role customization.  Directive arguments are handled by the
"role" directive itself.

Interpreted role functions return a tuple of two values:

- A list of nodes which will be inserted into the document tree at the
  point where the interpreted role was encountered (can be an empty
  list).

- A list of system messages, which will be inserted into the document tree
  immediately after the end of the current inline block (can also be empty).
"""

__docformat__ = "reStructuredText"

from typing import Any, Callable, List, Optional, Tuple

from . import utils


def role(
    role_name: str, language_module: object, lineno: int, reporter: utils.Reporter
) -> Tuple[Optional[Callable[..., Any]], List[object]]:
    raise NotImplementedError("Registry not initialized")

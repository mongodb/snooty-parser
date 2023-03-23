# $Id: __init__.py 8671 2021-04-07 12:09:51Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
This is ``docutils.parsers.rst`` package. It exports a single class, `Parser`,
the reStructuredText parser.


Usage
=====

1. Create a parser::

       parser = docutils.parsers.rst.Parser()

   Several optional arguments may be passed to modify the parser's behavior.
   Please see `Customizing the Parser`_ below for details.

2. Gather input (a multi-line string), by reading a file or the standard
   input::

       input = sys.stdin.read()

3. Create a new empty `docutils.nodes.document` tree::

       document = docutils.utils.new_document(source, settings)

   See `docutils.utils.new_document()` for parameter details.

4. Run the parser, populating the document tree::

       parser.parse(input, document)


Parser Overview
===============

The reStructuredText parser is implemented as a state machine, examining its
input one line at a time. To understand how the parser works, please first
become familiar with the `docutils.statemachine` module, then see the
`states` module.


Customizing the Parser
----------------------

Anything that isn't already customizable is that way simply because that type
of customizability hasn't been implemented yet.  Patches welcome!

When instantiating an object of the `Parser` class, two parameters may be
passed: ``rfc2822`` and ``inliner``.  Pass ``rfc2822=True`` to enable an
initial RFC-2822 style header block, parsed as a "field_list" element (with
"class" attribute set to "rfc2822").  Currently this is the only body-level
element which is customizable without subclassing.  (Tip: subclass `Parser`
and change its "state_classes" and "initial_state" attributes to refer to new
classes. Contact the author if you need more details.)

The ``inliner`` parameter takes an instance of `states.Inliner` or a subclass.
It handles inline markup recognition.  A common extension is the addition of
further implicit hyperlinks, like "RFC 2822".  This can be done by subclassing
`states.Inliner`, adding a new method for the implicit markup, and adding a
``(pattern, method)`` pair to the "implicit_dispatch" attribute of the
subclass.  See `states.Inliner.implicit_inline()` for details.  Explicit
inline markup can be customized in a `states.Inliner` subclass via the
``patterns.initial`` and ``dispatch`` attributes (and new methods as
appropriate).
"""

__docformat__ = "reStructuredText"


from typing import Optional

from . import nodes, parsers, statemachine, states


class Parser(parsers.Parser):

    """The reStructuredText parser."""

    def __init__(self, inliner: Optional[states.Inliner] = None) -> None:
        self.initial_state = "Body"
        self.state_classes = states.state_classes
        self.inliner = inliner

    def parse(self, inputstring: str, document: nodes.document) -> None:
        """Parse `inputstring` and populate `document`, a document tree."""
        self.setup_parse(inputstring, document)
        # provide fallbacks in case the document has only generic settings
        self.document.settings.setdefault("syntax_highlight", "long")
        self.statemachine = states.RSTStateMachine(
            state_config=statemachine.StateConfiguration(
                self.state_classes, self.initial_state
            ),
            debug=document.reporter.debug_flag,
        )
        inputlines = statemachine.string2lines(
            inputstring,
            tab_width=document.settings.tab_width,
            convert_whitespace=True,
        )

        self.statemachine.run_rst(inputlines, document, inliner=self.inliner)

        self.finish_parse()

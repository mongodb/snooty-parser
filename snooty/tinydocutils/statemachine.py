# $Id: statemachine.py 8565 2020-09-14 10:26:03Z milde $
# Author: David Goodger <goodger@python.org>
# Copyright: This module has been placed in the public domain.

"""
A finite state machine specialized for regular-expression-based text filters,
this module defines the following classes:

- `StateMachine`, a whitespace-sensitive state machine
- `State`, a state superclass
- `StateWS`, a state superclass for use with `StateMachineWS`
- `StringList`, extends standard Python lists.
- `StringList`, string-specific StringList.

Exception classes:

- `StateMachineError`
- `DuplicateStateError`
- `UnknownTransitionError`
- `DuplicateTransitionError`
- `UnexpectedIndentationError`
- `TransitionCorrection`: Raised to switch to another transition.
- `StateCorrection`: Raised to switch to another state & transition.

Functions:

- `string2lines()`: split a multi-line string into a list of one-line strings


How To Use This Module
======================
(See the individual classes, methods, and attributes for details.)

1. Import it: ``import statemachine`` or ``from statemachine import ...``.
   You will also need to ``import re``.

2. Derive a subclass of `State` (or `StateWS`) for each state in your state
   machine::

       class MyState(statemachine.State):

   Within the state's class definition:

   a) Include a pattern for each transition, in `State.patterns`::

          patterns = {'atransition': r'pattern', ...}

   b) Include a list of initial transitions to be set up automatically, in
      `State.initial_transitions`::

          initial_transitions = ['atransition', ...]

   c) Define a method for each transition, with the same name as the
      transition pattern::

          def atransition(self, match, context, next_state):
              # do something
              result = [...]  # a list
              return context, next_state, result
              # context, next_state may be altered

      Transition methods may raise an `EOFError` to cut processing short.

   d) You may wish to override the `State.bof()` and/or `State.eof()` implicit
      transition methods, which handle the beginning- and end-of-file.

   e) In order to handle nested processing, you may wish to override the
      attributes `State.nested_sm` and/or `State.nested_sm_kwargs`.

      If you are using `StateWS` as a base class, in order to handle nested
      indented blocks, you may wish to:

      - override the attributes `StateWS.indent_sm`,
        `StateWS.indent_sm_kwargs`, `StateWS.known_indent_sm`, and/or
        `StateWS.known_indent_sm_kwargs`;
      - override the `StateWS.blank()` method; and/or
      - override or extend the `StateWS.indent()`, `StateWS.known_indent()`,
        and/or `StateWS.firstknown_indent()` methods.

3. Create a state machine object::

       sm = StateMachine(state_classes=[MyState, ...],
                         initial_state='MyState')

4. Obtain the input text, which needs to be converted into a tab-free list of
   one-line strings. For example, to read text from a file called
   'inputfile'::

       input_string = open('inputfile').read()
       input_lines = statemachine.string2lines(input_string)

5. Run the state machine on the input text and collect the results, a list::

       results = sm.run(input_lines)

6. Remove any lingering circular references::

       sm.unlink()
"""

__docformat__ = "restructuredtext"

import re
import sys
import unicodedata
from typing import (
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Match,
    NamedTuple,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Type,
    Union,
    overload,
)

from . import nodes

TransitionTuple = Tuple[
    Pattern[str],
    Callable[
        [Match[str], List[str], Type["State"]],
        Tuple[List[str], "Type[State]", List[str]],
    ],
    "Type[State]",
]

TransitionResult = Tuple[List[str], "Type[State]", List[str]]


class StateConfiguration(NamedTuple):
    state_classes: "Sequence[Type[State]]"
    initial_state: "Type[State]"


class StringList:
    """
    List with extended functionality: slices of StringList objects are child
    lists, linked to their parents. Changes made to a child list also affect
    the parent list.  A child list is effectively a "view" (in the SQL sense)
    of the parent list.  Changes to parent lists, however, do *not* affect
    active child lists.  If a parent list is changed, any active child lists
    should be recreated.

    The start and end of the slice can be trimmed using the `trim_start()` and
    `trim_end()` methods, without affecting the parent list.  The link between
    child and parent lists can be broken by calling `disconnect()` on the
    child list.

    Also, StringList objects keep track of the source & offset of each item.
    This information is accessible via the `source()`, `offset()`, and
    `info()` methods.
    """

    def __init__(
        self,
        initlist: Sequence[str],
        source: Optional[str] = None,
        items: Optional[List[Tuple[Optional[str], int]]] = None,
        parent: "Optional[StringList]" = None,
        parent_offset: Optional[int] = None,
    ) -> None:
        self.items = []
        """A list of (source, offset) pairs, same length as `self.data`: the
        source of each line and the offset of each line from the beginning of
        its source."""

        self.parent = parent
        """The parent list."""

        self.parent_offset = parent_offset
        """Offset of this list from the beginning of the parent list."""

        self.data = list(initlist)
        if items:
            self.items = items
        else:
            self.items = [(source, i) for i in range(len(initlist))]
        assert len(self.data) == len(self.items), "data mismatch"

    def __str__(self) -> str:
        return str(self.data)

    def __repr__(self) -> str:
        return "%s(%s, items=%s)" % (self.__class__.__name__, self.data, self.items)

    def __len__(self) -> int:
        return len(self.data)

    # The __getitem__()/__setitem__() methods check whether the index
    # is a slice first, since indexing a native list with a slice object
    # just works.

    @overload
    def __getitem__(self, i: int) -> str:
        ...

    @overload
    def __getitem__(self, i: slice) -> "StringList":
        ...

    def __getitem__(self, i: Union[int, slice]) -> Union[str, "StringList"]:
        if isinstance(i, slice):
            assert i.step in (None, 1), "cannot handle slice with stride"
            return self.__class__(
                self.data[i.start : i.stop],
                items=self.items[i.start : i.stop],
                parent=self,
                parent_offset=i.start or 0,
            )
        else:
            return self.data[i]

    def __setitem__(self, i: Union[int, slice], item: str) -> None:
        if isinstance(i, slice):
            assert i.step in (None, 1), "cannot handle slice with stride"
            if not isinstance(item, StringList):
                raise TypeError("assigning non-StringList to StringList slice")
            self.data[i.start : i.stop] = item.data
            self.items[i.start : i.stop] = item.items
            assert len(self.data) == len(self.items), "data mismatch"
            if self.parent:
                self.parent[
                    (i.start or 0)
                    + self.parent_offset : (i.stop or len(self))
                    + self.parent_offset
                ] = item
        else:
            self.data[i] = item
            if self.parent:
                assert self.parent_offset is not None
                self.parent[i + self.parent_offset] = item

    def __delitem__(self, i: Union[int, slice]) -> None:
        assert self.parent_offset is not None

        if isinstance(i, int):
            del self.data[i]
            del self.items[i]
            if self.parent:
                del self.parent[i + self.parent_offset]
        else:
            assert i.step is None, "cannot handle slice with stride"
            del self.data[i.start : i.stop]
            del self.items[i.start : i.stop]
            if self.parent:
                del self.parent[
                    (i.start or 0)
                    + self.parent_offset : (i.stop or len(self))
                    + self.parent_offset
                ]

    def __add__(self, other: "StringList") -> "StringList":
        return self.__class__(self.data + other.data, items=(self.items + other.items))

    def __radd__(self, other: "StringList") -> "StringList":
        return self.__class__(other.data + self.data, items=(other.items + self.items))

    def __iadd__(self, other: "StringList") -> "StringList":
        self.data += other.data
        return self

    def __mul__(self, n: int) -> "StringList":
        return self.__class__(self.data * n, items=(self.items * n))

    __rmul__ = __mul__

    def __imul__(self, n: int) -> "StringList":
        self.data *= n
        self.items *= n
        return self

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def extend(self, other: "StringList") -> None:
        if self.parent:
            assert self.parent_offset is not None
            self.parent.insert(len(self.data) + self.parent_offset, other)
        self.data.extend(other.data)
        self.items.extend(other.items)

    def append(
        self,
        item: Union[str, "StringList"],
        source: Optional[str] = None,
        offset: int = 0,
    ) -> None:
        if source is None:
            assert isinstance(item, StringList)
            self.extend(item)
        else:
            assert isinstance(item, str)
            if self.parent:
                assert self.parent_offset is not None
                self.parent.insert(
                    len(self.data) + self.parent_offset, item, source, offset
                )
            self.data.append(item)
            self.items.append((source, offset))

    def insert(
        self,
        i: int,
        item: Union[str, "StringList"],
        source: Optional[str] = None,
        offset: int = 0,
    ) -> None:
        if source is None:
            if not isinstance(item, StringList):
                raise TypeError("inserting non-StringList with no source given")
            self.data[i:i] = item.data
            self.items[i:i] = item.items
            if self.parent:
                index = (len(self.data) + i) % len(self.data)
                assert self.parent_offset is not None
                self.parent.insert(index + self.parent_offset, item)
        else:
            assert isinstance(item, str)
            self.data.insert(i, item)
            self.items.insert(i, (source, offset))
            if self.parent:
                index = (len(self.data) + i) % len(self.data)
                assert self.parent_offset is not None
                self.parent.insert(index + self.parent_offset, item, source, offset)

    def pop(self, i: int = -1) -> str:
        if self.parent:
            index = (len(self.data) + i) % len(self.data)
            assert self.parent_offset is not None
            self.parent.pop(index + self.parent_offset)
        self.items.pop(i)
        return self.data.pop(i)

    def trim_start(self, n: int = 1) -> None:
        """
        Remove items from the start of the list, without touching the parent.
        """
        if n > len(self.data):
            raise IndexError(
                "Size of trim too large; can't trim %s items "
                "from a list of size %s." % (n, len(self.data))
            )
        elif n < 0:
            raise IndexError("Trim size must be >= 0.")
        del self.data[:n]
        del self.items[:n]
        if self.parent:
            assert self.parent_offset is not None
            self.parent_offset += n

    def trim_end(self, n: int = 1) -> None:
        """
        Remove items from the end of the list, without touching the parent.
        """
        if n > len(self.data):
            raise IndexError(
                "Size of trim too large; can't trim %s items "
                "from a list of size %s." % (n, len(self.data))
            )
        elif n < 0:
            raise IndexError("Trim size must be >= 0.")
        del self.data[-n:]
        del self.items[-n:]

    def remove(self, item: str) -> None:
        index = self.index(item)
        del self[index]

    def count(self, item: str) -> int:
        return self.data.count(item)

    def index(self, item: str) -> int:
        return self.data.index(item)

    def reverse(self) -> None:
        self.data.reverse()
        self.items.reverse()
        self.parent = None

    def info(self, i: int) -> Tuple[Optional[str], Optional[int]]:
        """Return source & offset for index `i`."""
        try:
            return self.items[i]
        except IndexError:
            if i == len(self.data):  # Just past the end
                return self.items[i - 1][0], None
            else:
                raise

    def source(self, i: int) -> str:
        """Return source for index `i`."""
        result = self.info(i)[0]
        assert result is not None
        return result

    def offset(self, i: int) -> int:
        """Return offset for index `i`."""
        result = self.info(i)[1]
        assert result is not None
        return result

    def disconnect(self) -> None:
        """Break link between this list and parent list."""
        self.parent = None

    def trim_left(self, length: int, start: int = 0, end: int = sys.maxsize) -> None:
        """
        Trim `length` characters off the beginning of each item, in-place,
        from index `start` to `end`.  No whitespace-checking is done on the
        trimmed text.  Does not affect slice parent.
        """
        self.data[start:end] = [line[length:] for line in self.data[start:end]]

    def get_text_block(self, start: int, flush_left: bool = False) -> "StringList":
        """
        Return a contiguous block of text.

        If `flush_left` is true, raise `UnexpectedIndentationError` if an
        indented line is encountered before the text block ends (with a blank
        line).
        """
        end = start
        last = len(self.data)
        while end < last:
            line = self.data[end]
            if not line.strip():
                break
            if flush_left and (line[0] == " "):
                source, offset = self.info(end)
                assert offset is not None
                raise UnexpectedIndentationError(self[start:end], source, offset + 1)
            end += 1
        return self[start:end]

    def get_indented(
        self,
        start: int = 0,
        until_blank: bool = False,
        strip_indent: bool = True,
        block_indent: Optional[int] = None,
        first_indent: Optional[int] = None,
    ) -> Tuple["StringList", int, bool]:
        """
        Extract and return a StringList of indented lines of text.

        Collect all lines with indentation, determine the minimum indentation,
        remove the minimum indentation from all indented lines (unless
        `strip_indent` is false), and return them. All lines up to but not
        including the first unindented line will be returned.

        :Parameters:
          - `start`: The index of the first line to examine.
          - `until_blank`: Stop collecting at the first blank line if true.
          - `strip_indent`: Strip common leading indent if true (default).
          - `block_indent`: The indent of the entire block, if known.
          - `first_indent`: The indent of the first line, if known.

        :Return:
          - a StringList of indented lines with mininum indent removed;
          - the amount of the indent;
          - a boolean: did the indented block finish with a blank line or EOF?
        """
        indent = block_indent  # start with None if unknown
        end = start
        if block_indent is not None and first_indent is None:
            first_indent = block_indent
        if first_indent is not None:
            end += 1
        last = len(self.data)
        while end < last:
            line = self.data[end]
            if line and (
                line[0] != " "
                or (block_indent is not None and line[:block_indent].strip())
            ):
                # Line not indented or insufficiently indented.
                # Block finished properly iff the last indented line blank:
                blank_finish = (end > start) and not self.data[end - 1].strip()
                break
            stripped = line.lstrip()
            if not stripped:  # blank line
                if until_blank:
                    blank_finish = True
                    break
            elif block_indent is None:
                line_indent = len(line) - len(stripped)
                if indent is None:
                    indent = line_indent
                else:
                    indent = min(indent, line_indent)
            end += 1
        else:
            blank_finish = True  # block ends at end of lines
        block = self[start:end]
        if first_indent is not None and block:
            block.data[0] = block.data[0][first_indent:]
        if indent and strip_indent:
            block.trim_left(indent, start=(first_indent is not None))
        return block, indent or 0, blank_finish

    def pad_double_width(self, pad_char: str) -> None:
        """
        Pad all double-width characters in self by appending `pad_char` to each.
        For East Asian language support.
        """
        east_asian_width = unicodedata.east_asian_width
        for i in range(len(self.data)):
            line = self.data[i]
            if isinstance(line, str):
                new = []
                for char in line:
                    new.append(char)
                    if east_asian_width(char) in "WF":  # 'W'ide & 'F'ull-width
                        new.append(pad_char)
                self.data[i] = "".join(new)

    def replace(self, old: str, new: str) -> None:
        """Replace all occurrences of substring `old` with `new`."""
        for i in range(len(self.data)):
            self.data[i] = self.data[i].replace(old, new)


class StateMachine:
    """
    A finite state machine for text filters using regular expressions.

    The input is provided in the form of a list of one-line strings (no
    newlines). States are subclasses of the `State` class. Transitions consist
    of regular expression patterns and transition methods, and are defined in
    each state.

    The state machine is started with the `run()` method, which returns the
    results of processing in a list.
    """

    def __init__(
        self,
        state_config: StateConfiguration,
        debug: bool = False,
    ) -> None:
        """
        Initialize a `StateMachine` object; add state objects.

        Parameters:

        - `state_classes`: a list of `State` (sub)classes.
        - `initial_state`: a string, the class name of the initial state.
        - `debug`: a boolean; produce verbose output if true (nonzero).
        """

        self.match_titles = False

        self.input_lines: Optional[StringList] = None
        """`StringList` of input lines (without newlines).
        Filled by `self.run()`."""

        self.input_offset = 0
        """Offset of `self.input_lines` from the beginning of the file."""

        self.line: Optional[str] = None
        """Current input line."""

        self.line_offset = -1
        """Current input line offset from beginning of `self.input_lines`."""

        self.debug = debug
        """Debugging mode on/off."""

        self.initial_state = state_config.initial_state
        """The name of the initial state (key to `self.states`)."""

        self.current_state = state_config.initial_state
        """The name of the current state (key to `self.states`)."""

        self.states: Dict[Type[State], State] = {}
        """Mapping of {state_name: State_object}."""

        for state_class in state_config.state_classes:
            self.add_state(state_class)

        self.observers: List[Callable[[Optional[str], Optional[int]], None]] = []
        """List of bound methods or functions to call whenever the current
        line changes.  Observers are called with one argument, ``self``.
        Cleared at the end of `run()`."""

        self._stderr = nodes.ErrorOutput()
        """Wrapper around sys.stderr catching en-/decoding errors"""

    def unlink(self) -> None:
        self.states.clear()

    def run_sm(
        self,
        input_lines: Union[StringList, List[str]],
        input_offset: int = 0,
        context: Optional[List[str]] = None,
        input_source: Optional[str] = None,
        initial_state: "Optional[Type[State]]" = None,
    ) -> List[str]:
        """
        Run the state machine on `input_lines`. Return results (a list).

        Reset `self.line_offset` and `self.current_state`. Run the
        beginning-of-file transition. Input one line at a time and check for a
        matching transition. If a match is found, call the transition method
        and possibly change the state. Store the context returned by the
        transition method to be passed on to the next transition matched.
        Accumulate the results returned by the transition methods in a list.
        Run the end-of-file transition. Finally, return the accumulated
        results.

        Parameters:

        - `input_lines`: a list of strings without newlines, or `StringList`.
        - `input_offset`: the line offset of `input_lines` from the beginning
          of the file.
        - `context`: application-specific storage.
        - `input_source`: name or path of source of `input_lines`.
        - `initial_state`: name of initial state.
        """
        self.runtime_init()
        if isinstance(input_lines, StringList):
            self.input_lines = input_lines
        else:
            self.input_lines = StringList(input_lines, source=input_source)
        self.input_offset = input_offset
        self.line_offset = -1
        self.current_state = initial_state or self.initial_state
        if self.debug:
            print(
                "\nStateMachine.run: input_lines (line_offset=%s):\n| %s"
                % (self.line_offset, "\n| ".join(self.input_lines)),
                file=self._stderr,
            )
        transitions: Optional[Sequence[str]] = None
        results: List[str] = []
        state = self.get_state()
        if self.debug:
            print("\nStateMachine.run: bof transition", file=self._stderr)
        if context is None:
            context = []
        context, result = state.bof(context)
        results.extend(result)
        while True:
            try:
                try:
                    self.next_line()
                    if self.debug:
                        source, offset = self.input_lines.info(self.line_offset)
                        print(
                            "\nStateMachine.run: line (source=%r, "
                            "offset=%r):\n| %s" % (source, offset, self.line),
                            file=self._stderr,
                        )
                    context, next_state, result = self.check_line(
                        context, state, transitions
                    )
                except EOFError:
                    if self.debug:
                        print(
                            "\nStateMachine.run: %s.eof transition"
                            % state.__class__.__name__,
                            file=self._stderr,
                        )
                    result = state.eof(context)
                    results.extend(result)
                    break
                else:
                    results.extend(result)
            except TransitionCorrection as exception:
                self.previous_line()  # back up for another try
                transitions = (exception.transition,)
                if self.debug:
                    print(
                        "\nStateMachine.run: TransitionCorrection to "
                        'state "%s", transition %s.'
                        % (state.__class__.__name__, transitions),
                        file=self._stderr,
                    )
                continue
            except StateCorrection as exception:
                self.previous_line()  # back up for another try
                next_state = exception.new_state
                transitions = (
                    None if exception.transition is None else (exception.transition,)
                )
                if self.debug:
                    print(
                        "\nStateMachine.run: StateCorrection to state "
                        '"%s", transition %s.' % (next_state.__name__, transitions),
                        file=self._stderr,
                    )
            else:
                transitions = None
            state = self.get_state(next_state)
        self.observers = []
        return results

    def get_state(self, next_state: "Optional[Type[State]]" = None) -> "State":
        """
        Return current state object; set it first if `next_state` given.

        Parameter `next_state`: a string, the name of the next state.
        """
        if next_state:
            if self.debug and next_state is not self.current_state:
                print(
                    "\nStateMachine.get_state: Changing state from "
                    '"%s" to "%s" (input line %s).'
                    % (self.current_state, next_state, self.abs_line_number()),
                    file=self._stderr,
                )
            self.current_state = next_state
        return self.states[self.current_state]

    def next_line(self, n: int = 1) -> str:
        """Load `self.line` with the `n`'th next line and return it."""
        try:
            try:
                self.line_offset += n
                assert self.input_lines is not None
                self.line = self.input_lines[self.line_offset]
            except IndexError:
                self.line = None
                raise EOFError
            return self.line
        finally:
            self.notify_observers()

    def is_next_line_blank(self) -> bool:
        """Return 1 if the next line is blank or non-existant."""
        try:
            assert self.input_lines is not None
            return not self.input_lines[self.line_offset + 1].strip()
        except IndexError:
            return True

    def at_eof(self) -> bool:
        """Return 1 if the input is at or past end-of-file."""
        assert self.input_lines is not None
        return self.line_offset >= len(self.input_lines) - 1

    def previous_line(self, n: int = 1) -> Optional[str]:
        """Load `self.line` with the `n`'th previous line and return it."""
        self.line_offset -= n
        if self.line_offset < 0:
            self.line = None
        else:
            assert self.input_lines is not None
            self.line = self.input_lines[self.line_offset]
        self.notify_observers()
        return self.line

    def goto_line(self, line_offset: int) -> str:
        """Jump to absolute line offset `line_offset`, load and return it."""
        try:
            try:
                self.line_offset = line_offset - self.input_offset
                assert self.input_lines is not None
                self.line = self.input_lines[self.line_offset]
            except IndexError:
                self.line = None
                raise EOFError
            assert self.line is not None
            return self.line
        finally:
            self.notify_observers()

    def get_source(self, line_offset: int) -> Optional[str]:
        """Return source of line at absolute line offset `line_offset`."""
        assert self.input_lines is not None
        return self.input_lines.source(line_offset - self.input_offset)

    def abs_line_offset(self) -> int:
        """Return line offset of current line, from beginning of file."""
        return self.line_offset + self.input_offset

    def abs_line_number(self) -> int:
        """Return line number of current line (counting from 1)."""
        return self.line_offset + self.input_offset + 1

    def get_source_and_line(
        self, lineno: Optional[int] = None
    ) -> Tuple[Optional[str], int]:
        """Return (source, line) tuple for current or given line number.

        Looks up the source and line number in the `self.input_lines`
        StringList instance to count for included source files.

        If the optional argument `lineno` is given, convert it from an
        absolute line number to the corresponding (source, line) pair.
        """
        if lineno is None:
            offset = self.line_offset
        else:
            offset = lineno - self.input_offset - 1

        assert self.input_lines is not None
        src, srcoffset = self.input_lines.info(offset)
        if srcoffset is not None:
            srcline: Optional[int] = srcoffset + 1
        else:
            # line is None if index is "Just past the end"
            src, srcline = self.get_source_and_line(offset + self.input_offset)
            assert srcline is not None
            return src, srcline + 1

        assert srcline is not None
        return (src, srcline)

    def get_text_block(self, flush_left: bool = False) -> "StringList":
        """
        Return a contiguous block of text.

        If `flush_left` is true, raise `UnexpectedIndentationError` if an
        indented line is encountered before the text block ends (with a blank
        line).
        """
        assert self.input_lines is not None
        try:
            block = self.input_lines.get_text_block(self.line_offset, flush_left)
            self.next_line(len(block) - 1)
            return block
        except UnexpectedIndentationError as err:
            block = err.args[0]
            self.next_line(len(block) - 1)  # advance to last line of block
            raise

    def check_line(
        self,
        context: List[str],
        state: "State",
        transitions: Optional[Iterable[str]] = None,
    ) -> Tuple[List[str], "Type[State]", List[str]]:
        """
        Examine one line of input for a transition match & execute its method.

        Parameters:

        - `context`: application-dependent storage.
        - `state`: a `State` object, the current state.
        - `transitions`: an optional ordered list of transition names to try,
          instead of ``state.transition_order``.

        Return the values returned by the transition method:

        - context: possibly modified from the parameter `context`;
        - next state name (`State` subclass name);
        - the result output of the transition, a list.

        When there is no match, ``state.no_match()`` is called and its return
        value is returned.
        """
        if self.debug:
            print(
                '\nStateMachine.check_line: state="%s", transitions=%r.'
                % (state.__class__.__name__, transitions),
                file=self._stderr,
            )
        if transitions is None:
            transitions = state.transitions
        for name in transitions:
            pattern, method, next_state = state.transitions[name]
            assert self.line is not None
            match = pattern.match(self.line)
            if match:
                if self.debug:
                    print(
                        "\nStateMachine.check_line: Matched transition "
                        '"%s" in state "%s".' % (name, state.__class__.__name__),
                        file=self._stderr,
                    )
                return method(match, context, next_state)
        else:
            raise ValueError(
                'Internal error: no transition pattern match.  State: "%s"; '
                "transitions: %s; context: %s; current line: %r."
                % (
                    self.__class__.__name__,
                    transitions,
                    context,
                    self.line,
                )
            )

    def add_state(self, state_class: "Type[State]") -> None:
        """
        Initialize & add a `state_class` (`State` subclass) object.

        Exception: `DuplicateStateError` raised if `state_class` was already
        added.
        """
        if state_class in self.states:
            raise DuplicateStateError(state_class)
        self.states[state_class] = state_class(self, self.debug)

    def runtime_init(self) -> None:
        """
        Initialize `self.states`.
        """
        for state in self.states.values():
            state.runtime_init()

    def attach_observer(
        self, observer: Callable[[Optional[str], Optional[int]], None]
    ) -> None:
        """
        The `observer` parameter is a function or bound method which takes two
        arguments, the source and offset of the current line.
        """
        self.observers.append(observer)

    def detach_observer(
        self, observer: Callable[[Optional[str], Optional[int]], None]
    ) -> None:
        self.observers.remove(observer)

    def notify_observers(self) -> None:
        assert self.input_lines is not None
        try:
            source, lineno = self.input_lines.info(self.line_offset)
        except IndexError:
            source = None
            lineno = None

        for observer in self.observers:
            observer(source, lineno)

    def get_indented(
        self, until_blank: bool = False, strip_indent: bool = True
    ) -> Tuple[StringList, int, int, bool]:
        """
        Return a block of indented lines of text, and info.

        Extract an indented block where the indent is unknown for all lines.

        :Parameters:
            - `until_blank`: Stop collecting at the first blank line if true.
            - `strip_indent`: Strip common leading indent if true (default).

        :Return:
            - the indented block (a list of lines of text),
            - its indent,
            - its first line offset from BOF, and
            - whether or not it finished with a blank line.
        """
        offset = self.abs_line_offset()
        assert self.input_lines is not None
        indented, indent, blank_finish = self.input_lines.get_indented(
            self.line_offset, until_blank, strip_indent
        )
        if indented:
            self.next_line(len(indented) - 1)  # advance to last indented line
        while indented and not indented[0].strip():
            indented.trim_start()
            offset += 1
        return indented, indent, offset, blank_finish

    def get_known_indented(
        self, indent: int, until_blank: bool = False, strip_indent: bool = True
    ) -> Tuple[StringList, int, bool]:
        """
        Return an indented block and info.

        Extract an indented block where the indent is known for all lines.
        Starting with the current line, extract the entire text block with at
        least `indent` indentation (which must be whitespace, except for the
        first line).

        :Parameters:
            - `indent`: The number of indent columns/characters.
            - `until_blank`: Stop collecting at the first blank line if true.
            - `strip_indent`: Strip `indent` characters of indentation if true
              (default).

        :Return:
            - the indented block,
            - its first line offset from BOF, and
            - whether or not it finished with a blank line.
        """
        offset = self.abs_line_offset()
        assert self.input_lines is not None
        indented, indent, blank_finish = self.input_lines.get_indented(
            self.line_offset, until_blank, strip_indent, block_indent=indent
        )
        self.next_line(len(indented) - 1)  # advance to last indented line
        while indented and not indented[0].strip():
            indented.trim_start()
            offset += 1
        return indented, offset, blank_finish

    def get_first_known_indented(
        self,
        indent: int,
        until_blank: bool = False,
        strip_indent: bool = True,
        strip_top: bool = True,
    ) -> Tuple[StringList, int, int, bool]:
        """
        Return an indented block and info.

        Extract an indented block where the indent is known for the first line
        and unknown for all other lines.

        :Parameters:
            - `indent`: The first line's indent (# of columns/characters).
            - `until_blank`: Stop collecting at the first blank line if true
              (1).
            - `strip_indent`: Strip `indent` characters of indentation if true
              (1, default).
            - `strip_top`: Strip blank lines from the beginning of the block.

        :Return:
            - the indented block,
            - its indent,
            - its first line offset from BOF, and
            - whether or not it finished with a blank line.
        """
        offset = self.abs_line_offset()
        assert self.input_lines is not None
        indented, indent, blank_finish = self.input_lines.get_indented(
            self.line_offset, until_blank, strip_indent, first_indent=indent
        )
        self.next_line(len(indented) - 1)  # advance to last indented line
        if strip_top:
            while indented and not indented[0].strip():
                indented.trim_start()
                offset += 1
        return indented, indent, offset, blank_finish


class State:
    """
    State superclass. Contains a list of transitions, and transition methods.

    Transition methods all have the same signature. They take 3 parameters:

    - An `re` match object. ``match.string`` contains the matched input line,
      ``match.start()`` gives the start index of the match, and
      ``match.end()`` gives the end index.
    - A context object, whose meaning is application-defined (initial value
      ``None``). It can be used to store any information required by the state
      machine, and the retured context is passed on to the next transition
      method unchanged.
    - The name of the next state, a string, taken from the transitions list;
      normally it is returned unchanged, but it may be altered by the
      transition method if necessary.

    Transition methods all return a 3-tuple:

    - A context object, as (potentially) modified by the transition method.
    - The next state name (a return value of ``None`` means no state change).
    - The processing result, a list, which is accumulated by the state
      machine.

    Transition methods may raise an `EOFError` to cut processing short.

    There are two implicit transitions, and corresponding transition methods
    are defined: `bof()` handles the beginning-of-file, and `eof()` handles
    the end-of-file. These methods have non-standard signatures and return
    values. `bof()` returns the initial context and results, and may be used
    to return a header string, or do any other processing needed. `eof()`
    should handle any remaining context and wrap things up; it returns the
    final processing result.

    Typical applications need only subclass `State` (or a subclass), set the
    `patterns` and `initial_transitions` class attributes, and provide
    corresponding transition methods. The default object initialization will
    take care of constructing the list of transitions.
    """

    nested_sm: Optional[Type[StateMachine]] = None
    """
    The `StateMachine` class for handling nested processing.

    If left as ``None``, `nested_sm` defaults to the class of the state's
    controlling state machine. Override it in subclasses to avoid the default.
    """

    state_config: Optional[StateConfiguration] = None
    """
    Keyword arguments dictionary, passed to the `nested_sm` constructor.

    Two keys must have entries in the dictionary:

    - Key 'state_classes' must be set to a list of `State` classes.
    - Key 'initial_state' must be set to the name of the initial state class.

    If `nested_sm_kwargs` is left as ``None``, 'state_classes' defaults to the
    class of the current state, and 'initial_state' defaults to the name of
    the class of the current state. Override in subclasses to avoid the
    defaults.
    """

    def __init__(self, state_machine: StateMachine, debug: bool = False) -> None:
        """
        Initialize a `State` object; make & add initial transitions.

        Parameters:

        - `statemachine`: the controlling `StateMachine` object.
        - `debug`: a boolean; produce verbose output if true.
        """

        self.transitions: Dict[str, TransitionTuple] = {}

        self.state_machine: StateMachine = state_machine
        """A reference to the controlling `StateMachine` object."""

        self.debug = debug
        """Debugging mode on/off."""

        if self.nested_sm is None:
            self.nested_sm = self.state_machine.__class__
        if self.state_config is None:
            self.state_config = StateConfiguration([self.__class__], self.__class__)

    def runtime_init(self) -> None:
        """
        Initialize this `State` before running the state machine; called from
        `self.state_machine.run()`.
        """
        pass

    def bof(self, context: List[str]) -> Tuple[List[str], List[str]]:
        """
        Handle beginning-of-file. Return unchanged `context`, empty result.

        Override in subclasses.

        Parameter `context`: application-defined storage.
        """
        return context, []

    def eof(self, context: List[str]) -> List[str]:
        """
        Handle end-of-file. Return empty result.

        Override in subclasses.

        Parameter `context`: application-defined storage.
        """
        return []

    def nop(
        self, match: Match[str], context: List[str], next_state: "Type[State]"
    ) -> TransitionResult:
        """
        A "do nothing" transition method.

        Return unchanged `context` & `next_state`, empty result. Useful for
        simple state changes (actionless transitions).
        """
        return context, next_state, []


class StateMachineError(Exception):
    pass


class DuplicateStateError(StateMachineError):
    pass


class UnknownTransitionError(StateMachineError):
    pass


class DuplicateTransitionError(StateMachineError):
    pass


class UnexpectedIndentationError(StateMachineError):
    pass


class TransitionCorrection(Exception):
    """
    Raise from within a transition method to switch to another transition.

    Raise with one argument, the new transition name.
    """

    def __init__(self, transition: str) -> None:
        self.transition = transition


class StateCorrection(Exception):
    """
    Raise from within a transition method to switch to another state.

    Raise with one or two arguments: new state name, and an optional new
    transition name.
    """

    def __init__(self, new_state: Type[State], transition: Optional[str]) -> None:
        self.new_state = new_state
        self.transition = transition


def string2lines(
    astring: str,
    tab_width: int = 8,
    convert_whitespace: bool = False,
    whitespace: Pattern[str] = re.compile("[\v\f]"),
) -> List[str]:
    """
    Return a list of one-line strings with tabs expanded, no newlines, and
    trailing whitespace stripped.

    Each tab is expanded with between 1 and `tab_width` spaces, so that the
    next character's index becomes a multiple of `tab_width` (8 by default).

    Parameters:

    - `astring`: a multi-line string.
    - `tab_width`: the number of columns between tab stops.
    - `convert_whitespace`: convert form feeds and vertical tabs to spaces?
    - `whitespace`: pattern object with the to-be-converted
      whitespace characters (default [\\v\\f]).
    """
    if convert_whitespace:
        astring = whitespace.sub(" ", astring)
    lines = [s.expandtabs(tab_width).rstrip() for s in astring.splitlines()]
    return lines

This is a heavily refactored and modified subset of docutils. The changes made include but are not limited to:
* The `Struct` class has been completely removed, and all instances replaced with specific classes
* rst tables are gone: snooty never handled them
* Block quote attributions are gone: snooty never handled them
* The `problematic` node has been removed -- snooty just ignored them
* Special RFC-2822 file handling has been removed
* `StateMachine` and `StateMachineWS` have been merged
* `ViewList` and `StringList` have been merged
* `frontend.OptionParser` is entirely different, only containing attributes
  as to satisfy other code
* Rewritten roman numeral handling that only handles the range I..XX

docutils is written and placed in the public domain by David Goodger <goodger@python.org> and
Edward Loper <edloper@gradient.cis.upenn.edu>. This directory retains the same licensing.

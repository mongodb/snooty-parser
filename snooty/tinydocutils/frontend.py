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
  `validate_comma_separated_list`,
  `validate_dependency_file`.
* `make_paths_absolute`.
* SettingSpec manipulation: `filter_settings_spec`.
"""

__docformat__ = "reStructuredText"

import codecs
import optparse
import os
import os.path
import sys
import warnings


def store_multiple(option, opt, value, parser, *args, **kwargs):
    """
    Store multiple values in `parser.values`.  (Option callback.)

    Store `None` for each attribute named in `args`, and store the value for
    each key (attribute name) in `kwargs`.
    """
    for attribute in args:
        setattr(parser.values, attribute, None)
    for key, value in kwargs.items():
        setattr(parser.values, key, value)


def read_config_file(option, opt, value, parser):
    """
    Read a configuration file during option processing.  (Option callback.)
    """
    try:
        new_settings = parser.get_config_file_settings(value)
    except ValueError as error:
        parser.error(error)
    parser.values.update(new_settings, parser)


def validate_encoding(
    setting, value, option_parser, config_parser=None, config_section=None
):
    try:
        codecs.lookup(value)
    except LookupError:
        raise LookupError('setting "%s": unknown encoding: "%s"' % (setting, value))
    return value


def validate_encoding_error_handler(
    setting, value, option_parser, config_parser=None, config_section=None
):
    try:
        codecs.lookup_error(value)
    except LookupError:
        raise LookupError(
            'unknown encoding error handler: "%s" (choices: '
            '"strict", "ignore", "replace", "backslashreplace", '
            '"xmlcharrefreplace", and possibly others; see documentation for '
            "the Python ``codecs`` module)" % value
        )
    return value


def validate_encoding_and_error_handler(
    setting, value, option_parser, config_parser=None, config_section=None
):
    """
    Side-effect: if an error handler is included in the value, it is inserted
    into the appropriate place as if it was a separate setting/option.
    """
    if ":" in value:
        encoding, handler = value.split(":")
        validate_encoding_error_handler(
            setting + "_error_handler",
            handler,
            option_parser,
            config_parser,
            config_section,
        )
        if config_parser:
            config_parser.set(config_section, setting + "_error_handler", handler)
        else:
            setattr(option_parser.values, setting + "_error_handler", handler)
    else:
        encoding = value
    validate_encoding(setting, encoding, option_parser, config_parser, config_section)
    return encoding


def validate_boolean(
    setting, value, option_parser, config_parser=None, config_section=None
) -> bool:
    """Check/normalize boolean settings:
    True:  '1', 'on', 'yes', 'true'
    False: '0', 'off', 'no','false', ''
    """
    if isinstance(value, bool):
        return value
    try:
        return option_parser.booleans[value.strip().lower()]
    except KeyError:
        raise LookupError('unknown boolean value: "%s"' % value)


def validate_ternary(
    setting, value, option_parser, config_parser=None, config_section=None
):
    """Check/normalize three-value settings:
    True:  '1', 'on', 'yes', 'true'
    False: '0', 'off', 'no','false', ''
    any other value: returned as-is.
    """
    if isinstance(value, bool) or value is None:
        return value
    try:
        return option_parser.booleans[value.strip().lower()]
    except KeyError:
        return value


def validate_nonnegative_int(
    setting, value, option_parser, config_parser=None, config_section=None
) -> int:
    value = int(value)
    if value < 0:
        raise ValueError("negative value; must be positive or zero")
    return value


def validate_threshold(
    setting, value, option_parser, config_parser=None, config_section=None
) -> int:
    try:
        return int(value)
    except ValueError:
        try:
            return option_parser.thresholds[value.lower()]
        except (KeyError, AttributeError):
            raise LookupError("unknown threshold: %r." % value)


def validate_colon_separated_string_list(
    setting, value, option_parser, config_parser=None, config_section=None
):
    if not isinstance(value, list):
        value = value.split(":")
    else:
        last = value.pop()
        value.extend(last.split(":"))
    return value


def validate_comma_separated_list(
    setting, value, option_parser, config_parser=None, config_section=None
):
    """Check/normalize list arguments (split at "," and strip whitespace)."""
    # `value` may be ``unicode``, ``str``, or a ``list`` (when  given as
    # command line option and "action" is "append").
    if not isinstance(value, list):
        value = [value]
    # this function is called for every option added to `value`
    # -> split the last item and append the result:
    last = value.pop()
    items = [i.strip(u" \t\n") for i in last.split(u",") if i.strip(u" \t\n")]
    value.extend(items)
    return value


def validate_url_trailing_slash(
    setting, value, option_parser, config_parser=None, config_section=None
):
    if not value:
        return "./"
    elif value.endswith("/"):
        return value
    else:
        return value + "/"


def validate_dependency_file(
    setting, value, option_parser, config_parser=None, config_section=None
):
    try:
        return docutils.utils.DependencyList(value)
    except IOError:
        return docutils.utils.DependencyList(None)


def validate_strip_class(
    setting, value, option_parser, config_parser=None, config_section=None
):
    # value is a comma separated string list:
    value = validate_comma_separated_list(
        setting, value, option_parser, config_parser, config_section
    )
    # validate list elements:
    for cls in value:
        normalized = docutils.nodes.make_id(cls)
        if cls != normalized:
            raise ValueError("Invalid class value %r (perhaps %r?)" % (cls, normalized))
    return value


def validate_smartquotes_locales(
    setting, value, option_parser, config_parser=None, config_section=None
):
    """Check/normalize a comma separated list of smart quote definitions.

    Return a list of (language-tag, quotes) string tuples."""

    # value is a comma separated string list:
    value = validate_comma_separated_list(
        setting, value, option_parser, config_parser, config_section
    )
    # validate list elements
    lc_quotes = []
    for item in value:
        try:
            lang, quotes = item.split(":", 1)
        except AttributeError:
            # this function is called for every option added to `value`
            # -> ignore if already a tuple:
            lc_quotes.append(item)
            continue
        except ValueError:
            raise ValueError(
                u'Invalid value "%s".'
                ' Format is "<language>:<quotes>".'
                % item.encode("ascii", "backslashreplace")
            )
        # parse colon separated string list:
        quotes = quotes.strip()
        multichar_quotes = quotes.split(":")
        if len(multichar_quotes) == 4:
            quotes = multichar_quotes
        elif len(quotes) != 4:
            raise ValueError(
                'Invalid value "%s". Please specify 4 quotes\n'
                "    (primary open/close; secondary open/close)."
                % item.encode("ascii", "backslashreplace")
            )
        lc_quotes.append((lang, quotes))
    return lc_quotes


def make_paths_absolute(pathdict, keys, base_path=None):
    """
    Interpret filesystem path settings relative to the `base_path` given.

    Paths are values in `pathdict` whose keys are in `keys`.  Get `keys` from
    `OptionParser.relative_path_settings`.
    """
    if base_path is None:
        base_path = getcwd()  # type(base_path) == unicode
        # to allow combining non-ASCII cwd with unicode values in `pathdict`
    for key in keys:
        if key in pathdict:
            value = pathdict[key]
            if isinstance(value, list):
                value = [make_one_path_absolute(base_path, path) for path in value]
            elif value:
                value = make_one_path_absolute(base_path, value)
            pathdict[key] = value


def make_one_path_absolute(base_path, path):
    return os.path.abspath(os.path.join(base_path, path))


def filter_settings_spec(settings_spec, *exclude, **replace):
    """Return a copy of `settings_spec` excluding/replacing some settings.

    `settings_spec` is a tuple of configuration settings with a structure
    described for docutils.SettingsSpec.settings_spec.

    Optional positional arguments are names of to-be-excluded settings.
    Keyword arguments are option specification replacements.
    (See the html4strict writer for an example.)
    """
    settings = list(settings_spec)
    # every third item is a sequence of option tuples
    for i in range(2, len(settings), 3):
        newopts = []
        for opt_spec in settings[i]:
            # opt_spec is ("<help>", [<option strings>], {<keyword args>})
            opt_name = [
                opt_string[2:].replace("-", "_")
                for opt_string in opt_spec[1]
                if opt_string.startswith("--")
            ][0]
            if opt_name in exclude:
                continue
            if opt_name in replace.keys():
                newopts.append(replace[opt_name])
            else:
                newopts.append(opt_spec)
        settings[i] = tuple(newopts)
    return tuple(settings)


class Values(optparse.Values):

    """
    Updates list attributes by extension rather than by replacement.
    Works in conjunction with the `OptionParser.lists` instance attribute.
    """

    def __init__(self, *args, **kwargs):
        optparse.Values.__init__(self, *args, **kwargs)
        if not hasattr(self, "record_dependencies") or self.record_dependencies is None:
            # Set up dependency list, in case it is needed.
            self.record_dependencies = docutils.utils.DependencyList()

    def update(self, other_dict, option_parser):
        if isinstance(other_dict, Values):
            other_dict = other_dict.__dict__
        other_dict = other_dict.copy()
        for setting in option_parser.lists.keys():
            if hasattr(self, setting) and setting in other_dict:
                value = getattr(self, setting)
                if value:
                    value += other_dict[setting]
                    del other_dict[setting]
        self._update_loose(other_dict)

    def copy(self):
        """Return a shallow copy of `self`."""
        return self.__class__(defaults=self.__dict__)

    def setdefault(self, name, default):
        """V.setdefault(n[,d]) -> getattr(V,n,d), also set D.n=d if n not in D or None."""
        if getattr(self, name, None) is None:
            setattr(self, name, default)
        return getattr(self, name)


class Option(optparse.Option):

    ATTRS = optparse.Option.ATTRS + ["validator", "overrides"]

    def process(self, opt, value, values, parser):
        """
        Call the validator function on applicable settings and
        evaluate the 'overrides' option.
        Extends `optparse.Option.process`.
        """
        result = optparse.Option.process(self, opt, value, values, parser)
        setting = self.dest
        if setting:
            if self.validator:
                value = getattr(values, setting)
                try:
                    new_value = self.validator(setting, value, parser)
                except Exception as error:
                    raise optparse.OptionValueError(
                        'Error in option "%s":\n    %s' % (opt, ErrorString(error))
                    )
                setattr(values, setting, new_value)
            if self.overrides:
                setattr(values, self.overrides, None)
        return result


class ConfigDeprecationWarning(DeprecationWarning):
    """Warning for deprecated configuration file features."""

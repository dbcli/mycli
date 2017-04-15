# -*- coding: utf-8 -*-
"""A generic output formatter interface."""

from __future__ import unicode_literals
from collections import namedtuple

from .expanded import expanded_table
from .preprocessors import (override_missing_value, convert_to_string)

from . import delimited_output_adapter
from . import tabulate_adapter
from . import terminaltables_adapter

MISSING_VALUE = '<null>'

OutputFormatHandler = namedtuple(
    'OutputFormatHandler',
    'format_name preprocessors formatter formatter_args')


class OutputFormatter(object):
    """A class with a standard interface for various formatting libraries."""

    _output_formats = {}

    def __init__(self, format_name=None):
        """Set the default *format_name*."""
        self._format_name = format_name

    def set_format_name(self, format_name):
        """Set the OutputFormatter's default format."""
        if format_name in self.supported_formats():
            self._format_name = format_name
        else:
            raise ValueError('unrecognized format_name: {}'.format(
                format_name))

    def get_format_name(self):
        """Get the OutputFormatter's default format."""
        return self._format_name

    def supported_formats(self):
        """Return the supported output format names."""
        return tuple(self._output_formats.keys())

    @classmethod
    def register_new_formatter(cls, format_name, handler, preprocessors=(),
                               kwargs={}):
        """Register a new formatter to format the output."""
        cls._output_formats[format_name] = OutputFormatHandler(
            format_name, preprocessors, handler, kwargs)

    def format_output(self, data, headers, format_name=None, **kwargs):
        """Format the headers and data using a specific formatter.

        *format_name* must be a formatter available in `supported_formats()`.

        All keyword arguments are passed to the specified formatter.

        """
        format_name = format_name or self._format_name
        if format_name not in self.supported_formats():
            raise ValueError('unrecognized format: {}'.format(format_name))

        (_, preprocessors, formatter,
         fkwargs) = self._output_formats[format_name]
        fkwargs.update(kwargs)
        if preprocessors:
            for f in preprocessors:
                data, headers = f(data, headers, **fkwargs)
        return formatter(data, headers, **fkwargs)


OutputFormatter.register_new_formatter('expanded', expanded_table,
                                       (override_missing_value,
                                        convert_to_string),
                                       {'missing_value': MISSING_VALUE})

for delimiter_format in delimited_output_adapter.supported_formats:
    OutputFormatter.register_new_formatter(
        delimiter_format, delimited_output_adapter.delimiter_adapter,
        delimited_output_adapter.delimiter_preprocessors,
        {'table_format': delimiter_format, 'missing_value': MISSING_VALUE})

for tabulate_format in tabulate_adapter.supported_formats:
    OutputFormatter.register_new_formatter(
        tabulate_format, tabulate_adapter.tabulate_adapter,
        tabulate_adapter.preprocessors,
        {'table_format': tabulate_format, 'missing_value': MISSING_VALUE})

for terminaltables_format in terminaltables_adapter.supported_formats:
    OutputFormatter.register_new_formatter(
        terminaltables_format, terminaltables_adapter.terminaltables_adapter,
        terminaltables_adapter.preprocessors,
        {'table_format': terminaltables_format, 'missing_value': MISSING_VALUE})

# -*- coding: utf-8 -*-
"""A generic output formatter interface."""

from __future__ import unicode_literals
from collections import namedtuple

from .expanded import expanded_table
from .preprocessors import (override_missing_value, convert_to_string)
from .delimited_output_adapter import (delimiter_adapter,
                                       supported_formats as delimiter_formats,
                                       delimiter_preprocessors)
from .tabulate_adapter import (tabulate_adapter,
                               supported_formats as tabulate_formats,
                               preprocessors as tabulate_preprocessors)
from .terminaltables_adapter import (
    terminaltables_adapter, preprocessors as terminaltables_preprocessors,
    supported_formats as terminaltables_formats)

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
    def register_new_formatter(cls, format_name, handler, preprocessors=None,
                               kwargs=None):
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
                                       {'missing_value': '<null>'})

for delimiter_format in delimiter_formats:
    OutputFormatter.register_new_formatter(delimiter_format, delimiter_adapter,
                                           delimiter_preprocessors,
                                           {'table_format': delimiter_format,
                                            'missing_value': '<null>'})

for tabulate_format in tabulate_formats:
    OutputFormatter.register_new_formatter(tabulate_format, tabulate_adapter,
                                           tabulate_preprocessors,
                                           {'table_format': tabulate_format,
                                            'missing_value': '<null>'})

for terminaltables_format in terminaltables_formats:
    OutputFormatter.register_new_formatter(
        terminaltables_format, terminaltables_adapter,
        terminaltables_preprocessors,
        {'table_format': terminaltables_format, 'missing_value': '<null>'})

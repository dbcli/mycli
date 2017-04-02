# -*- coding: utf-8 -*-
"""A generic output formatter interface."""

from __future__ import unicode_literals

import contextlib
import csv
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

from tabulate import tabulate

from . import encodingutils
from .packages.expanded import expanded_table

from decimal import Decimal


def to_string(value):
    """Convert *value* to a string."""
    if isinstance(value, encodingutils.binary_type):
        return encodingutils.bytes_to_string(value)
    else:
        return encodingutils.text_type(value)


def convert_to_string(data, headers, **_):
    """Convert all *data* and *headers* to strings."""
    return ([[to_string(v) for v in row] for row in data],
            [to_string(h) for h in headers])


def override_missing_value(data, headers, missing_value='', **_):
    """Override missing values in the data with *missing_value*."""
    return ([[missing_value if v is None else v for v in row] for row in data],
            headers)


def bytes_to_string(data, headers, **_):
    """Convert all *data* and *headers* bytes to strings."""
    return ([[encodingutils.bytes_to_string(v) for v in row] for row in data],
            [encodingutils.bytes_to_string(h) for h in headers])


def intlen(value):
    """Find (character) length
    >>> intlen('11.1')
    2
    >>> intlen('11')
    2
    >>> intlen('1.1')
    1
    """
    pos = value.find('.')
    if pos < 0:
        pos = len(value)
    return pos

def align_decimals(data, headers, **_):
    """Align decimals to decimal point
    >>> for i in align_decimals([[Decimal(1)], [Decimal('11.1')], [Decimal('1.1')]], [])[0]: print(i[0])
     1
    11.1
     1.1
    """
    pointpos = len(data[0]) * [0]
    for row in data:
        i = 0
        for v in row:
            if isinstance(v, Decimal):
                v = str(v)
                pointpos[i] = max(intlen(v), pointpos[i])
            i += 1
    results = []
    for row in data:
        i = 0
        result = []
        for v in row:
            if isinstance(v, Decimal):
                v = str(v)
                result.append((pointpos[i]-intlen(v))*" "+v)
            else:
                result.append(v)
            i += 1
        results.append(result)
    return results, headers


def quote_whitespaces(data, headers, quotestyle="'", **_):
    """Quote whitespace
    >>> for i in quote_whitespaces([["  before"], ["after  "], ["  both  "], ["none"]], [])[0]: print(i[0])
    '  before'
    'after  '
    '  both  '
    'none'
    >>> for i in quote_whitespaces([["abc"], ["def"], ["ghi"], ["jkl"]], [])[0]: print(i[0])
    abc
    def
    ghi
    jkl
    """
    """Convert all *data* and *headers* to strings."""
    quote = len(data[0])*[False]
    for row in data:
        i = 0
        for v in row:
            v = encodingutils.text_type(v)
            if v[0] == ' ' or v[-1] == ' ':
                quote[i] = True
            i += 1

    results = []
    for row in data:
        result = []
        i = 0
        for v in row:
            if quote[i]:
                result.append('{quotestyle}{value}{quotestyle}'.format(quotestyle=quotestyle, value=v))
            else:
                result.append(v)
            i += 1
        results.append(result)
    return results, headers


def tabulate_wrapper(data, headers, table_format=None, missing_value='', **_):
    """Wrap tabulate inside a standard function for OutputFormatter."""
    return tabulate(data, headers, tablefmt=table_format,
                    missingval=missing_value, disable_numparse=True)


def csv_wrapper(data, headers, delimiter=',', **_):
    """Wrap CSV formatting inside a standard function for OutputFormatter."""
    with contextlib.closing(StringIO()) as content:
        writer = csv.writer(content, delimiter=str(delimiter))

        writer.writerow(headers)
        for row in data:
            writer.writerow(row)

        return content.getvalue()


class OutputFormatter(object):
    """A class with a standard interface for various formatting libraries."""

    def __init__(self, format_name=None):
        """Register the supported output formats."""
        self._output_formats = {
            'csv': (csv_wrapper, {
                'preprocessor': (override_missing_value, bytes_to_string),
                'missing_value': '<null>'
            }),
            'tsv': (csv_wrapper, {
                'preprocessor': (override_missing_value, bytes_to_string),
                'missing_value': '<null>',
                'delimiter': '\t'
            }),
            'expanded': (expanded_table, {
                'preprocessor': (override_missing_value, convert_to_string),
                'missing_value': '<null>'
            })
        }
        self._format_name = None

        tabulate_formats = ('plain', 'simple', 'grid', 'fancy_grid', 'pipe',
                            'orgtbl', 'jira', 'psql', 'rst', 'mediawiki',
                            'moinmoin', 'html', 'latex', 'latex_booktabs',
                            'textile')
        for tabulate_format in tabulate_formats:
            self._output_formats[tabulate_format] = (tabulate_wrapper, {
                'preprocessor': (bytes_to_string, align_decimals, quote_whitespaces),
                'table_format': tabulate_format,
                'missing_value': '<null>'
            })

        if format_name:
            self.set_format_name(format_name)

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

    def format_output(self, data, headers, format_name=None, **kwargs):
        """Format the headers and data using a specific formatter.

        *format_name* must be a formatter available in `supported_formats()`.

        All keyword arguments are passed to the specified formatter.
        >>> print(OutputFormatter().format_output( \
                [["abc", Decimal(1)], ["defg", Decimal('11.1')], ["hi", Decimal('1.1')]], \
                ["text", "numeric"], \
                "psql" \
            ))
        +--------+-----------+
        | text   | numeric   |
        |--------+-----------|
        | abc    | ' 1'      |
        | defg   | '11.1'    |
        | hi     | ' 1.1'    |
        +--------+-----------+
        """
        format_name = format_name or self._format_name
        if format_name not in self.supported_formats():
            raise ValueError('unrecognized format: {}'.format(format_name))

        function, fkwargs = self._output_formats[format_name]
        fkwargs.update(kwargs)
        preprocessor = fkwargs.get('preprocessor', None)
        if preprocessor:
            for f in preprocessor:
                data, headers = f(data, headers, **fkwargs)
        return function(data, headers, **fkwargs)

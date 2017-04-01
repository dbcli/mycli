# -*- coding: utf-8 -*-
"""A generic output formatter interface."""

from __future__ import unicode_literals

import csv
import binascii
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

from tabulate import tabulate

from .packages.expanded import expanded_table


def override_missing_value(data, headers, missing_value='', **_):
    """Override missing values in the data with *missing_value*."""
    return ([[missing_value if v is None else v for v in row] for row in data],
            headers)


def bytes_to_hex(b):
    """Convert bytes that cannot be decoded to utf8 to hexlified string.

    >>> print(bytes_to_hex(b"\\xff"))
    0xff
    >>> print(bytes_to_hex('abc'))
    abc
    >>> print(bytes_to_hex('✌'))
    ✌
    """
    if isinstance(b, bytes):
        try:
            b.decode('utf8')
        except:
            b = '0x' + binascii.hexlify(b).decode('ascii')
    return b


def bytes_to_unicode(data, headers, **_):
    """Convert all *data* and *headers* to unicode."""
    return ([[bytes_to_hex(v) for v in row] for row in data],
            [bytes_to_hex(h) for h in headers])


def tabulate_wrapper(data, headers, table_format=None, missing_value='', **_):
    """Wrap tabulate inside a standard function for OutputFormatter."""
    return tabulate(data, headers, tablefmt=table_format,
                    missingval=missing_value, disable_numparse=True)


def csv_wrapper(data, headers, delimiter=',', **_):
    """Wrap CSV formatting inside a standard function for OutputFormatter."""
    content = StringIO()
    writer = csv.writer(content, delimiter=str(delimiter))
    writer.writerow(headers)

    for row in data:
        writer.writerow(row)

    output = content.getvalue()
    content.close()

    return output


class OutputFormatter(object):
    """A class with a standard interface for various formatting libraries."""

    def __init__(self):
        """Register the supported output formats."""
        self._output_formats = {}

        tabulate_formats = ('plain', 'simple', 'grid', 'fancy_grid', 'pipe',
                            'orgtbl', 'jira', 'psql', 'rst', 'mediawiki',
                            'moinmoin', 'html', 'latex', 'latex_booktabs',
                            'textile')
        for tabulate_format in tabulate_formats:
            self.register_output_format(tabulate_format, tabulate_wrapper,
                                        preprocessor=bytes_to_unicode,
                                        table_format=tabulate_format,
                                        missing_value='<null>')

        self.register_output_format('csv', csv_wrapper,
                                    preprocessor=override_missing_value,
                                    missing_value='null')
        self.register_output_format('tsv', csv_wrapper, delimiter='\t',
                                    preprocessor=override_missing_value,
                                    missing_value='null')

        self.register_output_format('expanded', expanded_table,
                                    preprocessor=override_missing_value,
                                    missing_value='<null>')

    def register_output_format(self, name, function, **kwargs):
        """Register a new output format.

        *function* should be a callable that accepts the following arguments:
            - *headers*: A list of headers for the output data.
            - *data*: The data that needs formatting.
            - *kwargs*: Any other keyword arguments for controlling the output.
        It should return the formatted output as a string.
        """
        self._output_formats[name] = (function, kwargs)

    def supported_formats(self):
        """Return the supported output format names."""
        return tuple(self._output_formats.keys())

    def format_output(self, data, headers, format_name, **kwargs):
        """Format the headers and data using a specific formatter.

        *format_name* must be a formatter available in `supported_formats()`.

        All keyword arguments are passed to the specified formatter.
        """
        function, fkwargs = self._output_formats[format_name]
        fkwargs.update(kwargs)
        preprocessor = fkwargs.pop('preprocessor', None)
        if preprocessor:
            data, headers = preprocessor(data, headers, **fkwargs)
        return function(data, headers, **fkwargs)

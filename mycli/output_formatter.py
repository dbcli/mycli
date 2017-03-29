"""A generic output formatter interface."""

from __future__ import unicode_literals

from tabulate import tabulate

from .packages.expanded import expanded_table


def tabulate_wrapper(data, headers, table_format=None, missing_value=None):
    """Wrap tabulate inside a standard function for OutputFormatter."""
    return tabulate(data, headers, tablefmt=table_format,
                    missingval=missing_value)


class OutputFormatter(object):
    """A class with a standard interface for various formatting libraries."""

    def __init__(self):
        """Register the supported output formats."""
        self._output_formats = {}

        tabulate_formats = ('plain', 'simple', 'grid', 'fancy_grid', 'pipe',
                            'orgtbl', 'jira', 'psql', 'rst', 'tsv',
                            'mediawiki', 'moinmoin', 'html', 'latex',
                            'latex_booktabs', 'textile')
        for tabulate_format in tabulate_formats:
            self.register_output_format(tabulate_format, tabulate_wrapper,
                                        table_format=tabulate_format)

        self.register_output_format('expanded', expanded_table)

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
        return function(data, headers, **fkwargs)

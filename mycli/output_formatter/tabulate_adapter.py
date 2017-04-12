from mycli.packages import tabulate
from .preprocessors import bytes_to_string, align_decimals, quote_whitespaces

tabulate.PRESERVE_WHITESPACE = True

supported_formats = ('plain', 'simple', 'grid', 'fancy_grid', 'pipe', 'orgtbl',
                     'jira', 'psql', 'rst', 'mediawiki', 'moinmoin', 'html',
                     'html', 'latex', 'latex_booktabs', 'textile')

preprocessors = (bytes_to_string, align_decimals, quote_whitespaces)


def tabulate_adapter(data, headers, table_format=None, missing_value='', **_):
    """Wrap tabulate inside a standard function for OutputFormatter."""
    return tabulate.tabulate(data, headers, tablefmt=table_format,
                             missingval=missing_value, disable_numparse=True)

"""Format data into a vertical, expanded table layout."""

from __future__ import unicode_literals


def get_separator(num):
    """Get a row separator for row *num*."""
    return "{0}[ {1}. row ]{2}\n".format('*' * 27, num + 1, '*' * 27)


def format_row(headers, row):
    """Format a row."""
    formatted_row = [' '.join(field) for field in zip(headers, row)]
    return '\n'.join(formatted_row)


def expanded_table(rows, headers, **_):
    """Format *rows* and *headers* as an expanded table.

    The values in *rows* and *headers* must be strings.
    """
    header_len = max([len(x) for x in headers])
    padded_headers = ['{} |'.format(x.ljust(header_len)) for x in headers]
    results = [format_row(padded_headers, row) for row in rows]

    output = []
    for i, result in enumerate(results):
        output.append(get_separator(i))
        output.append(result)
        output.append('\n')

    return ''.join(output)

"""Format data into a vertical, expanded table layout."""

from __future__ import unicode_literals


def pad(field, total, char=' '):
    return field + (char * (total - len(field)))


def get_separator(num, header_len, data_len):
    sep = "***************************[ %d. row ]***************************\n" % (num + 1)
    return sep


def expanded_table(rows, headers, **_):
    """Format *rows* and *headers* as an expanded table.

    The values in *rows* and *headers* must be strings.
    """
    header_len = max([len(x) for x in headers])
    max_row_len = 0
    results = []

    padded_headers = [pad(x, header_len) + ' |' for x in headers]
    header_len += 2

    for row in rows:
        row_len = max([len(x) for x in row])
        row_result = []
        if row_len > max_row_len:
            max_row_len = row_len

        for header, value in zip(padded_headers, row):
            row_result.append('{0} {1}'.format(header, value))

        results.append('\n'.join(row_result))

    output = []
    for i, result in enumerate(results):
        output.append(get_separator(i, header_len, max_row_len))
        output.append(result)
        output.append('\n')

    return ''.join(output)

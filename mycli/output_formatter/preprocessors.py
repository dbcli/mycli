from decimal import Decimal

from mycli import encodingutils


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
    """Find (character) length.

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
    """Align decimals to decimal point."""
    pointpos = len(headers) * [0]
    for row in data:
        for i, v in enumerate(row):
            if isinstance(v, Decimal):
                v = encodingutils.text_type(v)
                pointpos[i] = max(intlen(v), pointpos[i])
    results = []
    for row in data:
        result = []
        for i, v in enumerate(row):
            if isinstance(v, Decimal):
                v = encodingutils.text_type(v)
                result.append((pointpos[i] - intlen(v)) * " " + v)
            else:
                result.append(v)
        results.append(result)
    return results, headers


def quote_whitespaces(data, headers, quotestyle="'", **_):
    """Quote leading/trailing whitespace."""
    quote = len(headers) * [False]
    for row in data:
        for i, v in enumerate(row):
            v = encodingutils.text_type(v)
            if v.startswith(' ') or v.endswith(' '):
                quote[i] = True

    results = []
    for row in data:
        result = []
        for i, v in enumerate(row):
            quotation = quotestyle if quote[i] else ''
            result.append('{quotestyle}{value}{quotestyle}'.format(
                quotestyle=quotation, value=v))
        results.append(result)
    return results, headers

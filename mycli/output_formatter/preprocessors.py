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
    """Align decimals to decimal point.

    >>> for i in align_decimals([[Decimal(1)], [Decimal('11.1')], [Decimal('1.1')]], [])[0]: print(i[0])
     1
    11.1
     1.1

    """
    pointpos = len(data[0]) * [0]
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
    quote = len(data[0]) * [False]
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

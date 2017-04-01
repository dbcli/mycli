import binascii

from .encodingutils import binary_type, text_type

def pad(field, total, char=u" "):
    return field + (char * (total - len(field)))

def get_separator(num, header_len, data_len):

    sep = u"***************************[ %d. row ]***************************\n" % (num + 1)
    return sep

def format_field(value):
    # Returns the field as a text type, otherwise will hexify the string
    try:
        if isinstance(value, binary_type):
            return text_type(value, "ascii")
        else:
            return text_type(value)
    except UnicodeDecodeError:
        return text_type('0x' + binascii.hexlify(value).decode('ascii'))

def expanded_table(rows, headers, **_):
    header_len = max([len(x) for x in headers])
    max_row_len = 0
    results = []

    padded_headers = [pad(x, header_len) + u" |" for x in headers]
    header_len += 2

    for row in rows:
        row = [format_field(x) for x in row]
        row_len = max([len(x) for x in row])
        row_result = []
        if row_len > max_row_len:
            max_row_len = row_len

        for header, value in zip(padded_headers, row):
            row_result.append(u"%s %s" % (header, value))

        results.append('\n'.join(row_result))

    output = []
    for i, result in enumerate(results):
        output.append(get_separator(i, header_len, max_row_len))
        output.append(result)
        output.append('\n')

    return ''.join(output)

import contextlib
import csv
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

from .preprocessors import override_missing_value, bytes_to_string

supported_formats = ('csv', 'tsv')
delimiter_preprocessors = (override_missing_value, bytes_to_string)


def delimiter_adapter(data, headers, table_format='csv', **_):
    """Wrap CSV formatting inside a standard function for OutputFormatter."""
    with contextlib.closing(StringIO()) as content:
        if table_format == 'csv':
            writer = csv.writer(content, delimiter=',')
        elif table_format == 'tsv':
            writer = csv.writer(content, delimiter='\t')
        else:
            raise ValueError('Invalid table_format specified.')

        writer.writerow(headers)
        for row in data:
            writer.writerow(row)

        return content.getvalue()
import contextlib
import csv
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

from .preprocessors import (override_missing_value, bytes_to_string)

supported_formats = ('csv',)
delimiter_preprocessors = (override_missing_value, bytes_to_string)

def delimiter_adapter(data, headers, delimiter=',', **_):
    """Wrap CSV formatting inside a standard function for OutputFormatter."""
    with contextlib.closing(StringIO()) as content:
        writer = csv.writer(content, delimiter=str(delimiter))

        writer.writerow(headers)
        for row in data:
            writer.writerow(row)

        return content.getvalue()

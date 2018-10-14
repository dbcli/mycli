from __future__ import unicode_literals

from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.filters import Condition
from prompt_toolkit.application import get_app
from .packages.parseutils import is_open_quote


def cli_is_multiline(mycli):
    @Condition
    def cond():
        doc = get_app().layout.get_buffer_by_name(DEFAULT_BUFFER).document

        if not mycli.multi_line:
            return False
        else:
            return not _multiline_exception(doc.text)
    return cond

def _multiline_exception(text):
    orig = text
    text = text.strip()

    # Multi-statement favorite query is a special case. Because there will
    # be a semicolon separating statements, we can't consider semicolon an
    # EOL. Let's consider an empty line an EOL instead.
    if text.startswith('\\fs'):
        return orig.endswith('\n')

    return (text.startswith('\\') or   # Special Command
            text.endswith(';') or      # Ended with a semi-colon
            text.endswith('\\g') or    # Ended with \g
            text.endswith('\\G') or    # Ended with \G
            (text == 'exit') or        # Exit doesn't need semi-colon
            (text == 'quit') or        # Quit doesn't need semi-colon
            (text == ':q') or          # To all the vim fans out there
            (text == '')               # Just a plain enter without any text
            )

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition

class CLIBuffer(Buffer):
    def __init__(self, always_multiline, *args, **kwargs):
        self.always_multiline = always_multiline

        @Condition
        def is_multiline():
            doc = self.document
            return self.always_multiline and not _multiline_exception(doc.text)

        super(self.__class__, self).__init__(*args, is_multiline=is_multiline,
                                             tempfile_suffix='.sql', **kwargs)

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

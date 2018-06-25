
def multiline_exception(text):
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

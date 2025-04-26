from prompt_toolkit.application import get_app
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.filters import Condition

from mycli.packages import special


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
    if text.startswith("\\fs"):
        return orig.endswith("\n")

    return (
        # Special Command
        text.startswith("\\")
        or
        # Delimiter declaration
        text.lower().startswith("delimiter")
        or
        # Ended with the current delimiter (usually a semi-column)
        text.endswith((
            special.get_current_delimiter(),
            "\\g",
            "\\G",
            r"\e",
            r"\clip",
        ))
        or
        # Exit doesn't need semi-column`
        (text == "exit")
        or
        # Quit doesn't need semi-column
        (text == "quit")
        or
        # To all teh vim fans out there
        (text == ":q")
        or
        # just a plain enter without any text
        (text == "")
    )

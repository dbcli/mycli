from prompt_toolkit.application import get_app
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.filters import Condition, Filter

from mycli.packages.special import iocommands
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS


def cli_is_multiline(mycli) -> Filter:
    @Condition
    def cond():
        doc = get_app().layout.get_buffer_by_name(DEFAULT_BUFFER).document

        if not mycli.multi_line:
            return False
        else:
            return not _multiline_exception(doc.text)

    return cond


def _multiline_exception(text: str) -> bool:
    orig = text
    text = text.strip()
    first_word = text.split(' ')[0]

    # Multi-statement favorite query is a special case. Because there will
    # be a semicolon separating statements, we can't consider semicolon an
    # EOL. Let's consider an empty line an EOL instead.
    if first_word.startswith("\\fs"):
        return orig.endswith("\n")

    return (
        # Special Command
        first_word.startswith("\\")
        or text.endswith((
            # Ended with the current delimiter (usually a semi-column)
            iocommands.get_current_delimiter(),
            # or ended with certain commands
            "\\g",
            "\\G",
            r"\e",
            r"\clip",
        ))
        or
        # non-backslashed special commands such as "exit" or "help" don't need semicolon
        first_word in SPECIAL_COMMANDS
        or
        # uppercase variants accepted
        first_word.lower() in SPECIAL_COMMANDS
        or
        # To all teh vim fans out there
        (first_word == ":q")
        or
        # just a plain enter without any text
        (first_word == "")
    )

from prompt_toolkit.application import get_app
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode

from mycli.packages import special


def create_toolbar_tokens_func(mycli, show_fish_help):
    """Return a function that generates the toolbar tokens."""

    def get_toolbar_tokens():
        result = [("class:bottom-toolbar", " ")]

        if mycli.multi_line:
            delimiter = special.get_current_delimiter()
            result.append((
                "class:bottom-toolbar",
                " ({} [{}] will end the line) ".format("Semi-colon" if delimiter == ";" else "Delimiter", delimiter),
            ))

        if mycli.multi_line:
            result.append(("class:bottom-toolbar.on", "[F3] Multiline: ON  "))
        else:
            result.append(("class:bottom-toolbar.off", "[F3] Multiline: OFF  "))
        if mycli.prompt_app.editing_mode == EditingMode.VI:
            result.append(("class:bottom-toolbar.on", "Vi-mode ({})".format(_get_vi_mode())))

        if mycli.toolbar_error_message:
            result.append(("class:bottom-toolbar", "  " + mycli.toolbar_error_message))
            mycli.toolbar_error_message = None

        if show_fish_help():
            result.append(("class:bottom-toolbar", "  Right-arrow to complete suggestion"))

        if mycli.completion_refresher.is_refreshing():
            result.append(("class:bottom-toolbar", "     Refreshing completions..."))

        return result

    return get_toolbar_tokens


def _get_vi_mode():
    """Get the current vi mode for display."""
    return {
        InputMode.INSERT: "I",
        InputMode.NAVIGATION: "N",
        InputMode.REPLACE: "R",
        InputMode.REPLACE_SINGLE: "R",
        InputMode.INSERT_MULTIPLE: "M",
    }[get_app().vi_state.input_mode]

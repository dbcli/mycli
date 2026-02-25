from typing import Callable

from prompt_toolkit.application import get_app
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode

from mycli.packages import special


def create_toolbar_tokens_func(mycli, show_initial_toolbar_help: Callable) -> Callable:
    """Return a function that generates the toolbar tokens."""

    def get_toolbar_tokens() -> list[tuple[str, str]]:
        divider = ('class:bottom-toolbar', ' │ ')

        result = [("class:bottom-toolbar", "[Tab] Complete")]

        result.append(divider)
        result.append(("class:bottom-toolbar", "[F1] Help"))

        if mycli.completer.smart_completion:
            result.append(divider)
            result.append(("class:bottom-toolbar", "[F2] Smart-complete:"))
            result.append(("class:bottom-toolbar.on", "ON"))
        else:
            result.append(divider)
            result.append(("class:bottom-toolbar", "[F2] Smart-complete:"))
            result.append(("class:bottom-toolbar.off", "OFF"))

        if mycli.multi_line:
            result.append(divider)
            result.append(("class:bottom-toolbar", "[F3] Multiline:"))
            result.append(("class:bottom-toolbar.on", "ON"))
        else:
            result.append(divider)
            result.append(("class:bottom-toolbar", "[F3] Multiline:"))
            result.append(("class:bottom-toolbar.off", "OFF"))

        if mycli.prompt_app.editing_mode == EditingMode.VI:
            result.append(divider)
            result.append(("class:bottom-toolbar", "Vi:"))
            result.append(("class:bottom-toolbar.on", _get_vi_mode()))

        if mycli.toolbar_error_message:
            result.append(divider)
            result.append(("class:bottom-toolbar", mycli.toolbar_error_message))
            mycli.toolbar_error_message = None

        if mycli.multi_line:
            delimiter = special.get_current_delimiter()
            if delimiter != ';' or show_initial_toolbar_help():
                result.append(divider)
                result.append(('class:bottom-toolbar', '"'))
                result.append(('class:bottom-toolbar.on', delimiter))
                result.append(('class:bottom-toolbar', '" ends a statement'))

        if show_initial_toolbar_help():
            result.append(divider)
            result.append(("class:bottom-toolbar", "right-arrow accepts full-line suggestion"))

        if mycli.completion_refresher.is_refreshing():
            result.append(divider)
            result.append(("class:bottom-toolbar", "Refreshing completions…"))

        return result

    return get_toolbar_tokens


def _get_vi_mode() -> str:
    """Get the current vi mode for display."""
    return {
        InputMode.INSERT: "I",
        InputMode.NAVIGATION: "N",
        InputMode.REPLACE: "R",
        InputMode.REPLACE_SINGLE: "R",
        InputMode.INSERT_MULTIPLE: "M",
    }[get_app().vi_state.input_mode]

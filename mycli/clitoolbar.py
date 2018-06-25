from pygments.token import Token
from prompt_toolkit.application import get_app
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode


def create_toolbar_tokens_func(mycli, get_is_refreshing, show_fish_help):
    """
    Return a function that generates the toolbar tokens.
    """
    token = 'class:toolbar'
    token_on = 'class:toolbar.on'
    token_off = 'class:toolbar.off'

    def get_toolbar_tokens():
        app = get_app()
        default_buffer = app.layout.get_buffer_by_name(DEFAULT_BUFFER)

        result = []
        result.append((token, ' '))

        if mycli.always_multiline:
            result.append((token_on, '[F3] Multiline: ON  '))
        else:
            result.append((token_off, '[F3] Multiline: OFF  '))

        if mycli.always_multiline:
            result.append((token,
                ' (Semi-colon [;] will end the line)'))

        if app.editing_mode == EditingMode.VI:
            result.append((
                token_on,
                'Vi-mode ({})'.format(_get_vi_mode())
            ))

        if show_fish_help():
            result.append((token, '  Right-arrow to complete suggestion'))

        if get_is_refreshing():
            result.append((token, '     Refreshing completions...'))

        return result
    return get_toolbar_tokens


def _get_vi_mode():
    """Get the current vi mode for display."""
    return {
        InputMode.INSERT: 'I',
        InputMode.NAVIGATION: 'N',
        InputMode.REPLACE: 'R',
        InputMode.INSERT_MULTIPLE: 'M'
    }[get_app().vi_state.input_mode]

from pygments.token import Token
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode


def create_toolbar_tokens_func(get_is_refreshing, show_fish_help):
    """
    Return a function that generates the toolbar tokens.
    """
    token = Token.Toolbar

    def get_toolbar_tokens(cli):
        result = []
        result.append((token, ' '))

        if cli.buffers[DEFAULT_BUFFER].always_multiline:
            result.append((token.On, '[F3] Multiline: ON  '))
        else:
            result.append((token.Off, '[F3] Multiline: OFF  '))

        if cli.buffers[DEFAULT_BUFFER].always_multiline:
            result.append((token,
                ' (Semi-colon [;] will end the line)'))

        if cli.editing_mode == EditingMode.VI:
            result.append((
                token.On,
                'Vi-mode ({})'.format(_get_vi_mode(cli))
            ))

        if show_fish_help():
            result.append((token, '  Right-arrow to complete suggestion'))

        if get_is_refreshing():
            result.append((token, '     Refreshing completions...'))

        return result
    return get_toolbar_tokens


def _get_vi_mode(cli):
    """Get the current vi mode for display."""
    return {
        InputMode.INSERT: 'I',
        InputMode.NAVIGATION: 'N',
        InputMode.REPLACE: 'R',
        InputMode.INSERT_MULTIPLE: 'M'
    }[cli.vi_state.input_mode]

import logging
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyBindings
from .filters import has_selected_completion

_logger = logging.getLogger(__name__)


def mycli_bindings(mycli):
    """
    Custom key bindings for mycli.
    """
    key_bindings = KeyBindings()

    @key_bindings.add('f2')
    def _(event):
        """
        Enable/Disable SmartCompletion Mode.
        """
        _logger.debug('Detected F2 key.')
        buf = event.cli.current_buffer
        buf.completer.smart_completion = not buf.completer.smart_completion

    @key_bindings.add('f3')
    def _(event):
        """
        Enable/Disable Multiline Mode.
        """
        _logger.debug('Detected F3 key.')
        mycli.always_multiline = not mycli.always_multiline

    @key_bindings.add('f4')
    def _(event):
        """
        Toggle between Vi and Emacs mode.
        """
        _logger.debug('Detected F4 key.')
        if event.app.editing_mode == EditingMode.VI:
            event.app.editing_mode = EditingMode.EMACS
        else:
            event.app.editing_mode = EditingMode.VI

    @key_bindings.add('tab')
    def _(event):
        """
        Force autocompletion at cursor.
        """
        _logger.debug('Detected <Tab> key.')
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            event.app.start_completion(select_first=True)

    @key_bindings.add('c-space')
    def _(event):
        """
        Initialize autocompletion at cursor.

        If the autocompletion menu is not showing, display it with the
        appropriate completions for the context.

        If the menu is showing, select the next completion.
        """
        _logger.debug('Detected <C-Space> key.')

        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            event.app.start_completion(select_first=False)

    @key_bindings.add('enter', filter=has_selected_completion)
    def _(event):
        """
        Makes the enter key work as the tab key only when showing the menu.
        """
        _logger.debug('Detected <C-J> key.')

        event.current_buffer.complete_state = None
        b = event.app.current_buffer
        b.complete_state = None

    return key_bindings

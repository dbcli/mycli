from __future__ import unicode_literals
import logging
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import completion_is_selected
from prompt_toolkit.key_binding import KeyBindings

_logger = logging.getLogger(__name__)


def mycli_bindings(mycli):
    """Custom key bindings for mycli."""
    kb = KeyBindings()

    @kb.add('f2')
    def _(event):
        """Enable/Disable SmartCompletion Mode."""
        _logger.debug('Detected F2 key.')
        mycli.completer.smart_completion = not mycli.completer.smart_completion

    @kb.add('f3')
    def _(event):
        """Enable/Disable Multiline Mode."""
        _logger.debug('Detected F3 key.')
        mycli.multi_line = not mycli.multi_line

    @kb.add('f4')
    def _(event):
        """Toggle between Vi and Emacs mode."""
        _logger.debug('Detected F4 key.')
        if mycli.key_bindings == "vi":
            event.app.editing_mode = EditingMode.EMACS
            mycli.key_bindings = "emacs"
        else:
            event.app.editing_mode = EditingMode.VI
            mycli.key_bindings = "vi"

    @kb.add('tab')
    def _(event):
        """Force autocompletion at cursor."""
        _logger.debug('Detected <Tab> key.')
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)

    @kb.add('c-space')
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
            b.start_completion(select_first=False)

    @kb.add('enter', filter=completion_is_selected)
    def _(event):
        """Makes the enter key work as the tab key only when showing the menu.

        In other words, don't execute query when enter is pressed in
        the completion dropdown menu, instead close the dropdown menu
        (accept current selection).

        """
        _logger.debug('Detected enter key.')

        event.current_buffer.complete_state = None
        b = event.app.current_buffer
        b.complete_state = None

    return kb

import logging

from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import (
    Condition,
    completion_is_selected,
    control_is_searchable,
    emacs_mode,
)
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.selection import SelectionType

from mycli.key_binding_actions import KeyBindingActions
from mycli.packages import shortcuts
from mycli.packages.toolkit.fzf import search_history

_logger = logging.getLogger(__name__)


@Condition
def ctrl_d_condition() -> bool:
    """Ctrl-D exit binding is only active when the buffer is empty."""
    app = get_app()
    return not app.current_buffer.text


@Condition
def in_completion() -> bool:
    app = get_app()
    return bool(app.current_buffer.complete_state)


def mycli_bindings(mycli) -> KeyBindings:
    """Custom key bindings for mycli."""
    kb = KeyBindings()
    actions = KeyBindingActions(mycli)

    @kb.add('f1')
    def _(event: KeyPressEvent) -> None:
        """Open browser to documentation index."""
        actions.open_docs(event, 'Detected F1 key.')

    @kb.add('escape', '[', 'P')
    def _(event: KeyPressEvent) -> None:
        """Open browser to documentation index."""
        actions.open_docs(event, "Detected alternate F1 key sequence.")

    @kb.add("f2")
    def _(_event: KeyPressEvent) -> None:
        """Enable/Disable SmartCompletion Mode."""
        actions.toggle_smart_completion("Detected F2 key.")

    @kb.add('escape', '[', 'Q')
    def _(_event: KeyPressEvent) -> None:
        """Enable/Disable SmartCompletion Mode."""
        actions.toggle_smart_completion("Detected alternate F2 key sequence.")

    @kb.add("f3")
    def _(_event: KeyPressEvent) -> None:
        """Enable/Disable Multiline Mode."""
        actions.toggle_multiline("Detected F3 key.")

    @kb.add('escape', '[', 'R')
    def _(_event: KeyPressEvent) -> None:
        """Enable/Disable Multiline Mode."""
        actions.toggle_multiline('Detected alternate F3 key sequence.')

    @kb.add("f4")
    def _(event: KeyPressEvent) -> None:
        """Toggle between Vi and Emacs mode."""
        actions.toggle_editing_mode(event, "Detected F4 key.")

    @kb.add('escape', '[', 'S')
    def _(event: KeyPressEvent) -> None:
        """Toggle between Vi and Emacs mode."""
        actions.toggle_editing_mode(event, 'Detected alternate F4 key sequence.')

    @kb.add("tab")
    def _(event: KeyPressEvent) -> None:
        """Complete action at cursor."""
        _logger.debug("Detected <Tab> key.")
        buffer = event.app.current_buffer

        behaviors = mycli.config['keys'].as_list('tab')

        if 'toolkit_default' in behaviors:
            if buffer.complete_state:
                buffer.complete_next()
            else:
                buffer.start_completion(select_first=True)

        if buffer.complete_state:
            if 'advance' in behaviors:
                buffer.complete_next()
            elif 'cancel' in behaviors:
                buffer.cancel_completion()
            return

        if 'advancing_summon' in behaviors:
            buffer.start_completion(select_first=True)
        elif 'prefixing_summon' in behaviors:
            buffer.start_completion(insert_common_part=True)
        elif 'summon' in behaviors:
            buffer.start_completion(select_first=False)

    @kb.add("escape", eager=True, filter=in_completion)
    def _(event: KeyPressEvent) -> None:
        """Cancel completion menu.

        There will be a lag when canceling Escape due to the processing of
        Alt- keystrokes as Escape- sequences.

        There will be no lag when using control-g to cancel."""
        event.app.current_buffer.cancel_completion()

    @kb.add("c-space")
    def _(event: KeyPressEvent) -> None:
        """
        Complete action at cursor.

        By default, if the autocompletion menu is not showing, display it with the
        appropriate completions for the context.

        If the menu is showing, select the next completion.
        """
        _logger.debug("Detected <C-Space> key.")

        buffer = event.app.current_buffer

        behaviors = mycli.config['keys'].as_list('control_space')

        if 'toolkit_default' in behaviors:
            if buffer.text:
                buffer.start_selection(selection_type=SelectionType.CHARACTERS)
            return

        if buffer.complete_state:
            if 'advance' in behaviors:
                buffer.complete_next()
            elif 'cancel' in behaviors:
                buffer.cancel_completion()
            return

        if 'advancing_summon' in behaviors:
            buffer.start_completion(select_first=True)
        elif 'prefixing_summon' in behaviors:
            buffer.start_completion(insert_common_part=True)
        elif 'summon' in behaviors:
            buffer.start_completion(select_first=False)

    @kb.add("c-x", "p", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Prettify and indent current statement, usually into multiple lines.

        Only accepts buffers containing single SQL statements.
        """
        _logger.debug("Detected <C-x p>/> key.")

        buffer = event.app.current_buffer
        if buffer.text:
            buffer.transform_region(0, len(buffer.text), mycli.handle_prettify_binding)

    @kb.add("c-x", "u", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Unprettify and dedent current statement, usually into one line.

        Only accepts buffers containing single SQL statements.
        """
        _logger.debug("Detected <C-x u>/< key.")

        buffer = event.app.current_buffer
        if buffer.text:
            buffer.transform_region(0, len(buffer.text), mycli.handle_unprettify_binding)

    @kb.add("c-o", "d", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Insert the current date.
        """
        _logger.debug("Detected <C-o d> key.")

        event.app.current_buffer.insert_text(shortcuts.server_date(mycli.sqlexecute))

    @kb.add("c-o", "c-d", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Insert the quoted current date.
        """
        _logger.debug("Detected <C-o C-d> key.")

        event.app.current_buffer.insert_text(shortcuts.server_date(mycli.sqlexecute, quoted=True))

    @kb.add("c-o", "t", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Insert the current datetime.
        """
        _logger.debug("Detected <C-o t> key.")

        event.app.current_buffer.insert_text(shortcuts.server_datetime(mycli.sqlexecute))

    @kb.add("c-o", "c-t", filter=emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """
        Insert the quoted current datetime.
        """
        _logger.debug("Detected <C-o C-t> key.")

        event.app.current_buffer.insert_text(shortcuts.server_datetime(mycli.sqlexecute, quoted=True))

    @kb.add("c-r", filter=control_is_searchable)
    def _(event: KeyPressEvent) -> None:
        """Search history using fzf or reverse incremental search."""
        _logger.debug("Detected <C-r> key.")
        mode = mycli.config.get('keys', {}).get('control_r', 'auto')
        if mode == 'reverse_isearch':
            search_history(event, incremental=True)
        else:
            search_history(
                event,
                highlight_preview=mycli.highlight_preview,
                highlight_style=mycli.syntax_style,
            )

    @kb.add("escape", "r", filter=control_is_searchable & emacs_mode)
    def _(event: KeyPressEvent) -> None:
        """Search history using fzf when available."""
        _logger.debug("Detected <alt-r> key.")
        search_history(
            event,
            highlight_preview=mycli.highlight_preview,
            highlight_style=mycli.syntax_style,
        )

    @kb.add('c-d', filter=ctrl_d_condition)
    def _(event: KeyPressEvent) -> None:
        """Exit mycli or ignore keypress."""
        _logger.debug('Detected <C-d> key on empty line.')
        mode = mycli.config.get('keys', {}).get('control_d', 'exit')
        if mode == 'exit':
            event.app.exit(exception=EOFError, style='class:exiting')
        else:
            event.app.output.bell()

    @kb.add("enter", filter=completion_is_selected)
    def _(event: KeyPressEvent) -> None:
        """Makes the enter key work as the tab key only when showing the menu.

        In other words, don't execute query when enter is pressed in
        the completion dropdown menu, instead close the dropdown menu
        (accept current selection).

        """
        _logger.debug("Detected enter key.")

        event.current_buffer.complete_state = None
        buffer = event.app.current_buffer
        buffer.complete_state = None

    @kb.add("escape", "enter")
    def _(event: KeyPressEvent) -> None:
        """Introduces a line break in multi-line mode, or dispatches the
        command in single-line mode."""
        _logger.debug("Detected alt-enter key.")
        if mycli.multi_line:
            event.app.current_buffer.validate_and_handle()
        else:
            event.app.current_buffer.insert_text("\n")

    return kb

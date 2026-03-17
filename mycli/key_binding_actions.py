from __future__ import annotations
import logging
import webbrowser
from typing import Any
import prompt_toolkit
from prompt_toolkit.application.current import get_app
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from mycli.constants import DOCS_URL
from mycli.packages.toolkit.utils import safe_invalidate_display

_logger = logging.getLogger(__name__)


class KeyBindingActions:
    def __init__(self, mycli: Any) -> None:
        self._mycli = mycli

    @staticmethod
    def _print_docs_help() -> None:
        app = get_app()
        app.print_text('\n')
        app.print_text([
            ('', 'Inline help — type "'),
            ('bold', 'help'),
            ('', '" or "'),
            ('bold', r'\?'),
            ('', '"\n'),
        ])
        app.print_text([
            ('', 'Docs index — '),
            ('bold', DOCS_URL),
            ('', '\n'),
        ])
        app.print_text('\n')

    def open_docs(self, event: KeyPressEvent, message: str) -> None:
        _logger.debug(message)
        webbrowser.open_new_tab(DOCS_URL)
        prompt_toolkit.application.run_in_terminal(self._print_docs_help)
        safe_invalidate_display(event.app)

    def toggle_smart_completion(self, message: str) -> None:
        _logger.debug(message)
        self._mycli.completer.smart_completion = not self._mycli.completer.smart_completion

    def toggle_multiline(self, message: str) -> None:
        _logger.debug(message)
        self._mycli.multi_line = not self._mycli.multi_line

    def toggle_editing_mode(self, event: KeyPressEvent, message: str) -> None:
        _logger.debug(message)
        if self._mycli.key_bindings == "vi":
            event.app.editing_mode = EditingMode.EMACS
            self._mycli.key_bindings = "emacs"
            event.app.ttimeoutlen = self._mycli.emacs_ttimeoutlen
        else:
            event.app.editing_mode = EditingMode.VI
            self._mycli.key_bindings = "vi"
            event.app.ttimeoutlen = self._mycli.vi_ttimeoutlen

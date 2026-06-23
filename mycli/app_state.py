from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from configobj import ConfigObj

from mycli.config import strip_matching_quotes

if TYPE_CHECKING:
    from mycli.client import MyCli


def normalize_ssl_mode(config: ConfigObj) -> tuple[str | None, str | None]:
    ssl_mode = config['main'].get('ssl_mode', None) or config['connection'].get('default_ssl_mode', None)
    if ssl_mode not in ('auto', 'on', 'off', None):
        return None, f'Invalid config option provided for ssl_mode ({ssl_mode}); ignoring.'
    return ssl_mode, None


def configure_prompt_state(
    mycli: MyCli,
    config: ConfigObj,
    prompt: str | None,
    toolbar_format: str | None,
) -> None:
    mycli.prompt_format = prompt or config['main']['prompt'] or mycli.default_prompt
    mycli.prompt_lines = 0
    mycli.multiline_continuation_char = config['main']['prompt_continuation']
    mycli.toolbar_format = toolbar_format or config['main']['toolbar']
    mycli.terminal_tab_title_format = config['main']['terminal_tab_title']
    mycli.terminal_window_title_format = config['main']['terminal_window_title']
    mycli.multiplex_window_title_format = config['main']['multiplex_window_title']
    mycli.multiplex_pane_title_format = config['main']['multiplex_pane_title']


def destructive_keywords_from_config(config: ConfigObj) -> list[str]:
    keywords = config['main'].get('destructive_keywords', 'DROP SHUTDOWN DELETE TRUNCATE ALTER UPDATE')
    return [keyword for keyword in keywords.split(' ') if keyword]


def llm_prompt_truncation(config: ConfigObj) -> tuple[int, int]:
    if 'llm' in config and re.match(r'^\d+$', config['llm'].get('prompt_field_truncate', '')):
        field_truncate = int(config['llm'].get('prompt_field_truncate'))
    else:
        field_truncate = 0
    if 'llm' in config and re.match(r'^\d+$', config['llm'].get('prompt_section_truncate', '')):
        section_truncate = int(config['llm'].get('prompt_section_truncate'))
    else:
        section_truncate = 0
    return field_truncate, section_truncate


class AppStateMixin:
    login_path: str | None

    def read_mylogin_cnf(self, cnf: ConfigObj) -> dict[str, Any]:
        allowed_keys = [
            'user',
            'password',
            'host',
            'port',
            'socket',
        ]
        configuration: dict[str, Any] = dict.fromkeys(allowed_keys)
        for section in cnf:
            if section != self.login_path:
                continue
            for key in allowed_keys:
                if key in cnf[section]:
                    configuration[key] = strip_matching_quotes(cnf[section][key])

        return configuration

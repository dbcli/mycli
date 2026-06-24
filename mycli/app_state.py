from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from configobj import ConfigObj

from mycli.config import strip_matching_quotes

if TYPE_CHECKING:
    from mycli.client import MyCli


def normalize_ssl_mode(
    config: ConfigObj,
    config_without_package_defaults: ConfigObj,
) -> tuple[str | None, str | None]:
    error_notice: str | None = None
    ssl_mode: str | None = None

    if 'main' in config_without_package_defaults and 'ssl_mode' in config_without_package_defaults['main']:
        # migration with notice added with mycli 2.0.0 in 2026-07
        # todo: entirely remove support for ssl_mode in [main]
        error_notice = (
            'Mycli 2.0 migration: automatically moving ssl_mode under [main] to default_ssl_mode under [connection] in ~/.myclirc .'
        )

        ssl_mode = config_without_package_defaults['main']['ssl_mode']

        config_without_package_defaults.encoding = 'utf-8'
        if 'connection' not in config_without_package_defaults:
            config_without_package_defaults['connection'] = {}
        if config_without_package_defaults['connection'].get('default_ssl_mode', None) in (None, ''):
            config_without_package_defaults['connection']['default_ssl_mode'] = ssl_mode
        else:
            ssl_mode = config_without_package_defaults['connection'].get('default_ssl_mode')
            error_notice += f'\nBut connection.default_ssl_mode already existed, with the value: "{ssl_mode}".'
        del config_without_package_defaults['main']['ssl_mode']
        config_without_package_defaults.write()

    if not ssl_mode and 'default_ssl_mode' in config['connection']:
        ssl_mode = config['connection']['default_ssl_mode']
    if ssl_mode not in ('auto', 'on', 'off', None):
        error_notice = f'Invalid config option provided for ssl_mode ({ssl_mode}); ignoring.'
        return None, error_notice
    return ssl_mode, error_notice


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

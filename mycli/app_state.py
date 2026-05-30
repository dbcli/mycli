from __future__ import annotations

from collections import defaultdict
import re
from typing import TYPE_CHECKING, Any

from configobj import ConfigObj

from mycli.config import str_to_bool, strip_matching_quotes

if TYPE_CHECKING:
    from mycli.client import MyCli


def normalize_ssl_mode(config: ConfigObj) -> tuple[str | None, str | None]:
    ssl_mode = config['main'].get('ssl_mode', None) or config['connection'].get('default_ssl_mode', None)
    if ssl_mode not in ('auto', 'on', 'off', None):
        return None, f'Invalid config option provided for ssl_mode ({ssl_mode}); ignoring.'
    return ssl_mode, None


def ensure_my_cnf_sections(my_cnf: ConfigObj) -> None:
    if not my_cnf.get('client'):
        my_cnf['client'] = {}
    if not my_cnf.get('mysqld'):
        my_cnf['mysqld'] = {}


def configure_prompt_state(
    mycli: MyCli,
    config: ConfigObj,
    prompt: str | None,
    prompt_cnf: str | None,
    toolbar_format: str | None,
) -> None:
    mycli.prompt_format = prompt or prompt_cnf or config['main']['prompt'] or mycli.default_prompt
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
    defaults_suffix: str | None
    login_path: str | None

    def read_my_cnf(self, cnf: ConfigObj, keys: list[str]) -> dict[str, Any]:
        sections = ['client', 'mysqld']
        key_transformations = {
            'mysqld': {
                'socket': 'default_socket',
                'port': 'default_port',
                'user': 'default_user',
            },
        }

        if self.login_path and self.login_path != 'client':
            sections.append(self.login_path)

        if self.defaults_suffix:
            sections.extend([sect + self.defaults_suffix for sect in sections])

        configuration: dict[str, Any] = defaultdict(lambda: None)
        for key in keys:
            for section in cnf:
                if section not in sections or key not in cnf[section]:
                    continue
                new_key = key_transformations.get(section, {}).get(key) or key
                configuration[new_key] = strip_matching_quotes(cnf[section][key])

        return configuration

    def merge_ssl_with_cnf(self, ssl: dict[str, Any], cnf: dict[str, Any]) -> dict[str, Any]:
        merged = {}
        merged.update(ssl)
        prefix = 'ssl-'
        for key, value in cnf.items():
            if not key.startswith(prefix):
                continue
            if value is None:
                continue
            if key == 'ssl-verify-server-cert':
                merged['check_hostname'] = str_to_bool(value)
            else:
                merged[key[len(prefix) :]] = value

        return merged

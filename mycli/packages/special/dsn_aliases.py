from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mycli.config import str_to_bool
from mycli.constants import DEFAULT_CHARSET, DEFAULT_PROMPT, KNOWN_DSN_QUERY_PARAMS

if TYPE_CHECKING:
    from mycli.client import MyCli

DSN_SUBCOMMANDS = {'help', 'list', 'show', 'save', 'delete'}
INVALID_DSN_ALIAS_ERROR = 'Error: DSN aliases cannot start with a dash.'

SSL_QUERY_PARAMS = {
    'ssl_ca': 'ca',
    'ssl_capath': 'capath',
    'ssl_cert': 'cert',
    'ssl_cipher': 'cipher',
    'ssl_key': 'key',
    'ssl_mode': 'mode',
    'ssl_verify_server_cert': 'check_hostname',
    'tls_version': 'tls_version',
}


def is_valid_dsn_alias(alias: str) -> bool:
    return not alias.startswith('-')


def _config_bool(value: Any) -> bool:
    try:
        return str_to_bool(value)
    except (TypeError, ValueError):
        return False


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


class DsnAliases:
    section_name: str = 'alias_dsn'

    usage = """
DSN aliases are a way to save frequently used connections
with a short alias.  You can manage them by editing ~/.myclirc
directly or by using this command.

The only way to include a password in a DSN alias is by editing
~/.myclirc directly.

Examples:

    # Show a DSN for the current connection
    mysql> /dsn show
    mysql://mycli@localhost/mysql

    # Include non-default connection settings
    mysql> /dsn show --more
    mysql://mycli@localhost/mysql?prompt=%5Cd%3E%5C_

    # Save a DSN alias based on the current connection
    # The password will not be saved!
    mysql> /dsn save rocks

    # Include non-default connection settings in the saved DSN
    # The password will still not be saved!
    mysql> /dsn save --more rocks

    # List all persisted DSN aliases, some of which might have been
    # saved with --more
    mysql> /dsn list
    ┌───────┬──────────────────────────────────────────────────┐
    │ Alias │ DSN                                              │
    ├───────┼──────────────────────────────────────────────────┤
    │ rocks │ mysql://mycli@localhost/mysql?prompt=%5Cd%3E%5C_ │
    └───────┴──────────────────────────────────────────────────┘

    # Delete a DSN alias.
    mysql> /dsn delete rocks
"""

    # Class-level variable, for convenience to use as a singleton.
    instance: DsnAliases

    def __init__(self, config: Any, mycli: MyCli | None = None) -> None:
        self.config = config
        self.mycli = mycli

    @classmethod
    def from_config(cls, config: Any, mycli: MyCli | None = None) -> DsnAliases:
        return DsnAliases(config, mycli)

    def _query_param_defaults(self) -> dict[str, Any]:
        if self.mycli is None:
            return {}

        main_config = self.config.get('main', {})
        connection_config = self.config.get('connection', {})
        vault_config = self.config.get('vault_beta', {})
        return {
            'character_set': connection_config.get('default_character_set') or DEFAULT_CHARSET,
            'keepalive_ticks': self.mycli.default_keepalive_ticks,
            'prompt': main_config.get('prompt') or DEFAULT_PROMPT,
            'socket': connection_config.get('default_socket') or '',
            'ssl_ca': connection_config.get('default_ssl_ca') or '',
            'ssl_capath': connection_config.get('default_ssl_capath') or connection_config.get('default_ssl_ca_path') or '',
            'ssl_cert': connection_config.get('default_ssl_cert') or '',
            'ssl_cipher': connection_config.get('default_ssl_cipher') or '',
            'ssl_key': connection_config.get('default_ssl_key') or '',
            'ssl_mode': self.mycli.ssl_mode,
            'ssl_verify_server_cert': _config_bool(connection_config.get('default_ssl_verify_server_cert')),
            'vault_address': vault_config.get('address') or '',
            'vault_mount': vault_config.get('default_mount') or '',
            'vault_password_field': vault_config.get('default_password_field') or 'password',
            'vault_username_field': vault_config.get('default_username_field') or 'username',
        }

    def dsn_more(self, dsn: str) -> str:
        if self.mycli is None or self.mycli.sqlexecute is None:
            return dsn

        parsed = urlsplit(dsn)
        query_params: dict[str, Any] = {
            key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key in KNOWN_DSN_QUERY_PARAMS
        }
        sqlexecute = self.mycli.sqlexecute
        query_params.update({
            'character_set': sqlexecute.character_set,
            'keepalive_ticks': self.mycli.keepalive_ticks,
            'prompt': self.mycli.prompt_format,
        })
        ssl = sqlexecute.ssl or {}
        query_params.update({query_param: ssl.get(ssl_key) for query_param, ssl_key in SSL_QUERY_PARAMS.items()})

        defaults = self._query_param_defaults()
        more_params = [
            (key, _query_value(query_params[key]))
            for key in sorted(KNOWN_DSN_QUERY_PARAMS)
            if query_params.get(key) not in (None, '', False) and _query_value(query_params[key]) != _query_value(defaults.get(key, ''))
        ]
        return urlunsplit(parsed._replace(query=urlencode(more_params)))

    def list(self) -> list[str]:
        return [alias for alias in self.config.get(self.section_name, {}) if is_valid_dsn_alias(alias)]

    def get(self, alias: str) -> str | None:
        if not is_valid_dsn_alias(alias):
            return None
        return self.config.get(self.section_name, {}).get(alias, None)

    def save(self, alias: str, dsn: str) -> str:
        if not is_valid_dsn_alias(alias):
            return INVALID_DSN_ALIAS_ERROR
        self.config.encoding = 'utf-8'
        if self.section_name not in self.config:
            self.config[self.section_name] = {}
        self.config[self.section_name][alias] = dsn
        self.config.write()
        return f'Saved: {alias}'

    def delete(self, alias: str) -> str:
        if not is_valid_dsn_alias(alias):
            return INVALID_DSN_ALIAS_ERROR
        try:
            del self.config[self.section_name][alias]
        except KeyError:
            return f'Not Found: {alias}'
        self.config.write()
        return f'Deleted: {alias}'

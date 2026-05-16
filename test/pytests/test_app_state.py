from __future__ import annotations

from typing import Any

from configobj import ConfigObj
import pytest

from mycli.app_state import (
    AppStateMixin,
    destructive_keywords_from_config,
    ensure_my_cnf_sections,
    llm_prompt_truncation,
    normalize_ssl_mode,
)


class AppState(AppStateMixin):
    def __init__(self, defaults_suffix: str | None = None, login_path: str | None = None) -> None:
        self.defaults_suffix = defaults_suffix
        self.login_path = login_path


@pytest.mark.parametrize('ssl_mode', ['auto', 'on', 'off'])
def test_normalize_ssl_mode_accepts_known_values(ssl_mode: str) -> None:
    config = ConfigObj({'main': {'ssl_mode': ssl_mode}, 'connection': {'default_ssl_mode': 'off'}})

    assert normalize_ssl_mode(config) == (ssl_mode, None)


def test_normalize_ssl_mode_falls_back_to_connection_default() -> None:
    config = ConfigObj({'main': {'ssl_mode': ''}, 'connection': {'default_ssl_mode': 'on'}})

    assert normalize_ssl_mode(config) == ('on', None)


def test_normalize_ssl_mode_reports_invalid_values() -> None:
    config = ConfigObj({'main': {'ssl_mode': 'required'}, 'connection': {'default_ssl_mode': 'off'}})

    ssl_mode, warning = normalize_ssl_mode(config)

    assert ssl_mode is None
    assert warning == 'Invalid config option provided for ssl_mode (required); ignoring.'


def test_ensure_my_cnf_sections_adds_missing_sections() -> None:
    config = ConfigObj({'client': {'user': 'alice'}, 'extra': {'port': '3307'}})

    ensure_my_cnf_sections(config)

    assert config['client'] == {'user': 'alice'}
    assert config['mysqld'] == {}
    assert config['extra'] == {'port': '3307'}


def test_destructive_keywords_from_config_splits_non_empty_words() -> None:
    config = ConfigObj({'main': {'destructive_keywords': 'DROP  DELETE  UPDATE'}})

    assert destructive_keywords_from_config(config) == ['DROP', 'DELETE', 'UPDATE']


def test_destructive_keywords_from_config_uses_default() -> None:
    config = ConfigObj({'main': {}})

    assert destructive_keywords_from_config(config) == ['DROP', 'SHUTDOWN', 'DELETE', 'TRUNCATE', 'ALTER', 'UPDATE']


@pytest.mark.parametrize(
    ('llm_config', 'expected'),
    [
        ({'prompt_field_truncate': '12', 'prompt_section_truncate': '34'}, (12, 34)),
        ({'prompt_field_truncate': 'abc', 'prompt_section_truncate': '-1'}, (0, 0)),
        ({}, (0, 0)),
    ],
)
def test_llm_prompt_truncation_reads_positive_integer_strings(
    llm_config: dict[str, str],
    expected: tuple[int, int],
) -> None:
    config = ConfigObj({'main': {}, 'llm': llm_config})

    assert llm_prompt_truncation(config) == expected


def test_llm_prompt_truncation_handles_missing_llm_section() -> None:
    assert llm_prompt_truncation(ConfigObj({'main': {}})) == (0, 0)


def test_read_my_cnf_reads_allowed_sections_and_strips_quotes() -> None:
    app_state = AppState()
    cnf = ConfigObj({
        'client': {'host': '"db.example.com"', 'socket': '/tmp/client.sock'},
        'mysqld': {'socket': "'/tmp/mysql.sock'", 'port': '3307', 'user': 'mysql'},
        'ignored': {'host': 'ignored.example.com'},
    })

    configuration = app_state.read_my_cnf(cnf, ['host', 'socket', 'port', 'user', 'password'])

    assert configuration == {
        'host': 'db.example.com',
        'socket': '/tmp/client.sock',
        'default_socket': '/tmp/mysql.sock',
        'default_port': '3307',
        'default_user': 'mysql',
    }
    assert configuration['password'] is None


def test_read_my_cnf_includes_login_path_and_suffix_sections() -> None:
    app_state = AppState(defaults_suffix='test', login_path='work')
    cnf = ConfigObj({
        'client': {'user': 'client-user'},
        'work': {'password': 'work-pass'},
        'clienttest': {'host': 'client-test-host'},
        'worktest': {'database': 'work-test-db'},
    })

    configuration = app_state.read_my_cnf(cnf, ['user', 'password', 'host', 'database'])

    assert configuration == {
        'user': 'client-user',
        'password': 'work-pass',
        'host': 'client-test-host',
        'database': 'work-test-db',
    }


def test_merge_ssl_with_cnf_keeps_existing_ssl_and_adds_cnf_values() -> None:
    app_state = AppState()
    ssl: dict[str, Any] = {'ca': 'existing-ca.pem', 'cert': 'existing-cert.pem'}
    cnf = {
        'ssl-ca': 'cnf-ca.pem',
        'ssl-key': 'client-key.pem',
        'ssl-verify-server-cert': 'ON',
        'ssl-empty': None,
        'host': 'db.example.com',
    }

    merged = app_state.merge_ssl_with_cnf(ssl, cnf)

    assert merged == {
        'ca': 'cnf-ca.pem',
        'cert': 'existing-cert.pem',
        'key': 'client-key.pem',
        'check_hostname': True,
    }
    assert ssl == {'ca': 'existing-ca.pem', 'cert': 'existing-cert.pem'}

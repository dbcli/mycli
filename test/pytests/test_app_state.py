from __future__ import annotations

from configobj import ConfigObj
import pytest

from mycli.app_state import (
    AppStateMixin,
    destructive_keywords_from_config,
    llm_prompt_truncation,
    normalize_ssl_mode,
)


class AppState(AppStateMixin):
    def __init__(self, login_path: str | None = None) -> None:
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


def test_read_mylogin_cnf_reads_login_path_only() -> None:
    app_state = AppState(login_path='work')
    cnf = ConfigObj({
        'client': {'user': 'client-user'},
        'work': {'password': 'work-pass'},
        'clienttest': {'host': 'client-test-host'},
        'worktest': {'socket': 'work-test-socket'},
    })

    configuration = app_state.read_mylogin_cnf(cnf)

    assert configuration == {
        'user': None,
        'password': 'work-pass',
        'host': None,
        'port': None,
        'socket': None,
    }


def test_read_mylogin_cnf_strips_quotes() -> None:
    app_state = AppState(login_path='work')
    cnf = ConfigObj({
        'work': {'password': '"work-pass"'},
    })

    configuration = app_state.read_mylogin_cnf(cnf)

    assert configuration == {
        'user': None,
        'password': 'work-pass',
        'host': None,
        'port': None,
        'socket': None,
    }

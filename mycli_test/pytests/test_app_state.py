from __future__ import annotations

from configobj import ConfigObj
import pytest

from mycli.app_state import (
    AppStateMixin,
    configure_prompt_state,
    destructive_keywords_from_config,
    llm_prompt_truncation,
    normalize_image_protocol,
    normalize_ssl_mode,
)


class AppState(AppStateMixin):
    def __init__(self, login_path: str | None = None) -> None:
        self.login_path = login_path


class PromptState:
    prompt_format: str
    prompt_lines: int
    multiline_continuation_char: str
    toolbar_format: str
    terminal_tab_title_format: str
    terminal_window_title_format: str
    multiplex_window_title_format: str
    multiplex_pane_title_format: str

    def __init__(self) -> None:
        self.default_prompt = 'default> '


@pytest.mark.parametrize(
    ('image_protocol', 'expected'),
    [
        ('iterm2', ('iterm2', None)),
        ('kitty', ('kitty', None)),
        ('none', ('none', None)),
        ('', ('none', None)),
        (None, ('none', None)),
        ('unknown', ('none', 'Invalid config option provided for image_protocol (unknown); disabling.')),
    ],
)
def test_normalize_image_protocol(image_protocol: str | None, expected: tuple[str, str | None]) -> None:
    assert normalize_image_protocol(image_protocol) == expected


@pytest.mark.parametrize(
    ('prompt', 'config_prompt', 'toolbar_format', 'config_toolbar', 'expected_prompt', 'expected_toolbar'),
    [
        ('custom> ', 'configured> ', 'custom toolbar', 'configured toolbar', 'custom> ', 'custom toolbar'),
        (None, 'configured> ', None, 'configured toolbar', 'configured> ', 'configured toolbar'),
        ('', '', '', 'configured toolbar', 'default> ', 'configured toolbar'),
    ],
)
def test_configure_prompt_state_uses_overrides_and_fallbacks(
    prompt: str | None,
    config_prompt: str,
    toolbar_format: str | None,
    config_toolbar: str,
    expected_prompt: str,
    expected_toolbar: str,
) -> None:
    state = PromptState()
    config = ConfigObj({
        'main': {
            'prompt': config_prompt,
            'prompt_continuation': '... ',
            'toolbar': config_toolbar,
            'terminal_tab_title': 'tab title',
            'terminal_window_title': 'window title',
            'multiplex_window_title': 'multiplex window title',
            'multiplex_pane_title': 'multiplex pane title',
        },
    })

    configure_prompt_state(state, config, prompt, toolbar_format)  # type: ignore[arg-type]

    assert state.prompt_format == expected_prompt
    assert state.prompt_lines == 0
    assert state.multiline_continuation_char == '... '
    assert state.toolbar_format == expected_toolbar
    assert state.terminal_tab_title_format == 'tab title'
    assert state.terminal_window_title_format == 'window title'
    assert state.multiplex_window_title_format == 'multiplex window title'
    assert state.multiplex_pane_title_format == 'multiplex pane title'


@pytest.mark.parametrize('ssl_mode', ['auto', 'on', 'off'])
def test_normalize_ssl_mode_accepts_known_values(ssl_mode: str) -> None:
    config = ConfigObj({'main': {'ssl_mode': ssl_mode}, 'connection': {'default_ssl_mode': ssl_mode}})
    config_wo = ConfigObj({'main': {}, 'connection': {}})

    assert normalize_ssl_mode(config, config_wo) == (ssl_mode, None)


def test_normalize_ssl_mode_falls_back_to_connection_default() -> None:
    config = ConfigObj({'main': {'ssl_mode': ''}, 'connection': {'default_ssl_mode': 'on'}})
    config_wo = ConfigObj({'main': {}, 'connection': {}})

    assert normalize_ssl_mode(config, config_wo) == ('on', None)


def test_normalize_ssl_mode_returns_none_when_not_configured() -> None:
    config = ConfigObj({'main': {}, 'connection': {}})
    config_wo = ConfigObj({'main': {}, 'connection': {}})

    assert normalize_ssl_mode(config, config_wo) == (None, None)


def test_normalize_ssl_mode_migrates_deprecated_main_value() -> None:
    config = ConfigObj({'main': {}, 'connection': {'default_ssl_mode': 'off'}})
    config_wo = ConfigObj({'main': {'ssl_mode': 'on'}})

    ssl_mode, warning = normalize_ssl_mode(config, config_wo)

    assert ssl_mode == 'on'
    assert (
        warning == 'Mycli 2.0 migration: automatically moving ssl_mode under [main] to default_ssl_mode under [connection] in ~/.myclirc .'
    )
    assert config_wo['connection']['default_ssl_mode'] == 'on'
    assert 'ssl_mode' not in config_wo['main']


def test_normalize_ssl_mode_uses_existing_connection_value_when_migrating() -> None:
    config = ConfigObj({'main': {}, 'connection': {'default_ssl_mode': 'off'}})
    config_wo = ConfigObj({'main': {'ssl_mode': 'on'}, 'connection': {'default_ssl_mode': 'off'}})

    ssl_mode, warning = normalize_ssl_mode(config, config_wo)

    assert ssl_mode == 'off'
    assert warning == (
        'Mycli 2.0 migration: automatically moving ssl_mode under [main] to default_ssl_mode under [connection] in ~/.myclirc .'
        '\nBut connection.default_ssl_mode already existed, with the value: "off".'
    )
    assert config_wo['connection']['default_ssl_mode'] == 'off'
    assert 'ssl_mode' not in config_wo['main']


def test_normalize_ssl_mode_reports_invalid_values() -> None:
    config = ConfigObj({'main': {'ssl_mode': 'required'}, 'connection': {'default_ssl_mode': 'required'}})
    config_wo = ConfigObj()

    ssl_mode, warning = normalize_ssl_mode(config, config_wo)

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

# type: ignore

from types import SimpleNamespace
from unittest.mock import MagicMock

from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode
import pytest

from mycli import clitoolbar


def make_mycli(
    *,
    smart_completion: bool = True,
    multi_line: bool = False,
    editing_mode: EditingMode = EditingMode.EMACS,
    toolbar_error_message: str | None = None,
    refreshing: bool = False,
):
    return SimpleNamespace(
        completer=SimpleNamespace(smart_completion=smart_completion),
        multi_line=multi_line,
        prompt_app=SimpleNamespace(editing_mode=editing_mode),
        toolbar_error_message=toolbar_error_message,
        completion_refresher=SimpleNamespace(is_refreshing=MagicMock(return_value=refreshing)),
        get_custom_toolbar=MagicMock(return_value="custom toolbar"),
    )


def test_create_toolbar_tokens_func_shows_initial_help() -> None:
    mycli = make_mycli()

    toolbar = clitoolbar.create_toolbar_tokens_func(mycli, lambda: True, None)
    result = toolbar()

    assert ("class:bottom-toolbar", "right-arrow accepts full-line suggestion") in result
    assert ("class:bottom-toolbar", "[F2] Smart-complete:") in result
    assert ("class:bottom-toolbar.on", "ON ") in result
    assert ("class:bottom-toolbar", "[F3] Multiline:") in result
    assert ("class:bottom-toolbar.off", "OFF") in result


def test_create_toolbar_tokens_func_clears_toolbar_error_message() -> None:
    mycli = make_mycli(toolbar_error_message="boom")

    toolbar = clitoolbar.create_toolbar_tokens_func(mycli, lambda: False, None)
    first = toolbar()
    second = toolbar()

    assert ("class:bottom-toolbar.transaction.failed", "boom") in first
    assert ("class:bottom-toolbar.transaction.failed", "boom") not in second
    assert mycli.toolbar_error_message is None
    assert ("class:bottom-toolbar", "right-arrow accepts full-line suggestion") not in first


def test_create_toolbar_tokens_func_shows_multiline_vi_and_refreshing(monkeypatch) -> None:
    mycli = make_mycli(
        smart_completion=False,
        multi_line=True,
        editing_mode=EditingMode.VI,
        refreshing=True,
    )
    monkeypatch.setattr(clitoolbar.special, 'get_current_delimiter', lambda: '$$')
    monkeypatch.setattr(clitoolbar, '_get_vi_mode', lambda: 'N')

    toolbar = clitoolbar.create_toolbar_tokens_func(mycli, lambda: False, None)
    result = toolbar()

    assert ("class:bottom-toolbar.off", "OFF") in result
    assert ("class:bottom-toolbar", "[F3] Multiline:") in result
    assert ("class:bottom-toolbar.on", "ON ") in result
    assert ("class:bottom-toolbar", "Vi:") in result
    assert ("class:bottom-toolbar.on", "N") in result
    assert ('class:bottom-toolbar.on', '$$') in result
    assert ("class:bottom-toolbar", "Refreshing completions…") in result


def test_create_toolbar_tokens_func_applies_custom_format(monkeypatch) -> None:
    mycli = make_mycli(multi_line=True, refreshing=True)
    monkeypatch.setattr(clitoolbar.special, 'get_current_delimiter', lambda: '$$')

    formatted = [("class:bottom-toolbar", "CUSTOM")]
    to_formatted_text = MagicMock(return_value=formatted)
    monkeypatch.setattr(clitoolbar, 'to_formatted_text', to_formatted_text)

    toolbar = clitoolbar.create_toolbar_tokens_func(mycli, lambda: True, r'\Bfmt')
    result = toolbar()

    mycli.get_custom_toolbar.assert_called_once_with('fmt')
    to_formatted_text.assert_called_once_with("custom toolbar", style='class:bottom-toolbar')
    assert ('class:bottom-toolbar', '\n') in result
    assert ("class:bottom-toolbar", "CUSTOM") in result
    assert ("class:bottom-toolbar", "right-arrow accepts full-line suggestion") in result
    assert ("class:bottom-toolbar", "Refreshing completions…") in result


def test_create_toolbar_tokens_func_replaces_default_toolbar_for_plain_custom_format(monkeypatch) -> None:
    mycli = make_mycli(multi_line=True, toolbar_error_message='boom', refreshing=True)
    monkeypatch.setattr(clitoolbar.special, 'get_current_delimiter', lambda: '$$')

    formatted = [('class:bottom-toolbar', 'PLAIN CUSTOM')]
    to_formatted_text = MagicMock(return_value=formatted)
    monkeypatch.setattr(clitoolbar, 'to_formatted_text', to_formatted_text)

    toolbar = clitoolbar.create_toolbar_tokens_func(mycli, lambda: True, 'fmt')
    result = toolbar()

    mycli.get_custom_toolbar.assert_called_once_with('fmt')
    to_formatted_text.assert_called_once_with('custom toolbar', style='class:bottom-toolbar')
    assert ('class:bottom-toolbar', 'PLAIN CUSTOM') in result
    assert ('class:bottom-toolbar', '[Tab] Complete') not in result
    assert ('class:bottom-toolbar', '[F1] Help') not in result
    assert ('class:bottom-toolbar', 'right-arrow accepts full-line suggestion') in result
    assert ('class:bottom-toolbar.transaction.failed', 'boom') in result


@pytest.mark.parametrize(
    ('input_mode', 'expected'),
    [
        (InputMode.INSERT, 'I'),
        (InputMode.NAVIGATION, 'N'),
        (InputMode.REPLACE, 'R'),
        (InputMode.REPLACE_SINGLE, 'R'),
        (InputMode.INSERT_MULTIPLE, 'M'),
    ],
)
def test_get_vi_mode(monkeypatch, input_mode: InputMode, expected: str) -> None:
    app = SimpleNamespace(vi_state=SimpleNamespace(input_mode=input_mode))
    monkeypatch.setattr(clitoolbar, 'get_app', lambda: app)

    assert clitoolbar._get_vi_mode() == expected

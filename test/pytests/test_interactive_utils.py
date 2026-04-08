from types import SimpleNamespace

import click
import pytest

from mycli.packages import interactive_utils


def test_confirm_bool_param_type_converts_bool_and_strings() -> None:
    boolean_type = interactive_utils.ConfirmBoolParamType()

    assert boolean_type.convert(True, None, None) is True
    assert boolean_type.convert(False, None, None) is False
    assert boolean_type.convert('YES', None, None) is True
    assert boolean_type.convert('y', None, None) is True
    assert boolean_type.convert('NO', None, None) is False
    assert boolean_type.convert('n', None, None) is False
    assert repr(boolean_type) == 'BOOL'


def test_confirm_bool_param_type_rejects_invalid_string() -> None:
    boolean_type = interactive_utils.ConfirmBoolParamType()

    with pytest.raises(click.BadParameter, match='maybe is not a valid boolean'):
        boolean_type.convert('maybe', None, None)


def test_confirm_destructive_query_returns_none_when_not_destructive(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_called = False
    destructive_calls: list[tuple[list[str], str]] = []

    def fake_prompt(*args: object, **kwargs: object) -> bool:
        nonlocal prompt_called
        prompt_called = True
        return True

    def fake_is_destructive(keywords: list[str], query: str) -> bool:
        destructive_calls.append((keywords, query))
        return False

    monkeypatch.setattr(interactive_utils, 'is_destructive', fake_is_destructive)
    monkeypatch.setattr(interactive_utils, 'prompt', fake_prompt)
    monkeypatch.setattr(interactive_utils.sys, 'stdin', SimpleNamespace(isatty=lambda: True))

    keywords = ['drop']
    query = 'select 1;'
    assert interactive_utils.confirm_destructive_query(keywords, query) is None
    assert destructive_calls == [(keywords, query)]
    assert prompt_called is False


def test_confirm_destructive_query_returns_none_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_called = False

    def fake_prompt(*args: object, **kwargs: object) -> bool:
        nonlocal prompt_called
        prompt_called = True
        return True

    monkeypatch.setattr(interactive_utils, 'is_destructive', lambda keywords, query: True)
    monkeypatch.setattr(interactive_utils, 'prompt', fake_prompt)
    monkeypatch.setattr(interactive_utils.sys, 'stdin', SimpleNamespace(isatty=lambda: False))

    keywords = ['drop']
    sql = 'drop database foo;'
    assert interactive_utils.confirm_destructive_query(keywords, sql) is None
    assert prompt_called is False


def test_confirm_destructive_query_prompts_and_returns_user_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    destructive_calls: list[tuple[list[str], str]] = []

    def fake_prompt(*args: object, **kwargs: object) -> bool:
        prompt_calls.append((args, dict(kwargs)))
        return True

    def fake_is_destructive(keywords: list[str], query: str) -> bool:
        destructive_calls.append((keywords, query))
        return True

    monkeypatch.setattr(interactive_utils, 'is_destructive', fake_is_destructive)
    monkeypatch.setattr(interactive_utils, 'prompt', fake_prompt)
    monkeypatch.setattr(interactive_utils.sys, 'stdin', SimpleNamespace(isatty=lambda: True))

    keywords = ['drop']
    query = 'drop database foo;'
    result = interactive_utils.confirm_destructive_query(keywords, query)

    assert result is True
    assert destructive_calls == [(keywords, query)]
    assert prompt_calls == [
        (
            ("You're about to run a destructive command.\nDo you want to proceed? (y/n)",),
            {'type': interactive_utils.BOOLEAN_TYPE},
        )
    ]


def test_confirm_destructive_query_returns_false_when_user_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    destructive_calls: list[tuple[list[str], str]] = []

    def fake_prompt(*args: object, **kwargs: object) -> bool:
        prompt_calls.append((args, dict(kwargs)))
        return False

    def fake_is_destructive(keywords: list[str], query: str) -> bool:
        destructive_calls.append((keywords, query))
        return True

    monkeypatch.setattr(interactive_utils, 'is_destructive', fake_is_destructive)
    monkeypatch.setattr(interactive_utils, 'prompt', fake_prompt)
    monkeypatch.setattr(interactive_utils.sys, 'stdin', SimpleNamespace(isatty=lambda: True))

    keywords = ['drop']
    query = 'drop database foo;'
    assert interactive_utils.confirm_destructive_query(keywords, query) is False
    assert destructive_calls == [(keywords, query)]
    assert prompt_calls == [
        (
            ("You're about to run a destructive command.\nDo you want to proceed? (y/n)",),
            {'type': interactive_utils.BOOLEAN_TYPE},
        )
    ]


def test_confirm_returns_false_on_click_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_confirm(*args: object, **kwargs: object) -> bool:
        raise click.Abort()

    monkeypatch.setattr(click, 'confirm', fake_confirm)

    assert interactive_utils.confirm('continue?') is False


def test_confirm_delegates_to_click_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        calls.append((args, dict(kwargs)))
        return True

    monkeypatch.setattr(click, 'confirm', fake_confirm)

    assert interactive_utils.confirm('continue?', default=True) is True
    assert calls == [(('continue?',), {'default': True})]


def test_prompt_returns_false_on_click_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_prompt(*args: object, **kwargs: object) -> bool:
        raise click.Abort()

    monkeypatch.setattr(click, 'prompt', fake_prompt)

    assert interactive_utils.prompt('continue?') is False


def test_prompt_delegates_to_click_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_prompt(*args: object, **kwargs: object) -> bool:
        calls.append((args, dict(kwargs)))
        return True

    monkeypatch.setattr(click, 'prompt', fake_prompt)

    assert interactive_utils.prompt('continue?', type=interactive_utils.BOOLEAN_TYPE) is True
    assert calls == [(('continue?',), {'type': interactive_utils.BOOLEAN_TYPE})]

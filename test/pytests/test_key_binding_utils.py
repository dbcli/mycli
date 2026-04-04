import datetime
from typing import Any, cast

import pytest

from mycli.packages import key_binding_utils


class FakeSQLExecute:
    def __init__(self, now_value: datetime.datetime) -> None:
        self.now_value = now_value

    def now(self) -> datetime.datetime:
        return self.now_value


class FakePromptSession:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.prompt_calls: list[dict[str, Any]] = []

    def prompt(self, *, default: str, inputhook: Any, message: Any) -> str:
        self.prompt_calls.append({
            'default': default,
            'inputhook': inputhook,
            'message': message,
        })
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return cast(str, response)


class FakeMyCli:
    def __init__(
        self,
        *,
        prompt_session: FakePromptSession | None = None,
        last_query: str = 'last query',
    ) -> None:
        self.prompt_session = prompt_session
        self.last_query = last_query
        self.toolbar_error_message: str | None = None

    def get_last_query(self) -> str:
        return self.last_query


def test_server_date_returns_quoted_and_unquoted_values() -> None:
    sqlexecute = FakeSQLExecute(datetime.datetime(2026, 4, 3, 14, 5, 6))

    assert key_binding_utils.server_date(cast(Any, sqlexecute)) == '2026-04-03'
    assert key_binding_utils.server_date(cast(Any, sqlexecute), quoted=True) == "'2026-04-03'"


def test_server_datetime_returns_quoted_and_unquoted_values() -> None:
    sqlexecute = FakeSQLExecute(datetime.datetime(2026, 4, 3, 14, 5, 6))

    assert key_binding_utils.server_datetime(cast(Any, sqlexecute)) == '2026-04-03 14:05:06'
    assert key_binding_utils.server_datetime(cast(Any, sqlexecute), quoted=True) == "'2026-04-03 14:05:06'"


def test_prettify_statement():
    statement = 'SELECT 1'
    mycli = FakeMyCli()
    pretty_statement = key_binding_utils.handle_prettify_binding(cast(Any, mycli), statement)
    assert pretty_statement == 'SELECT\n    1;'


def test_unprettify_statement():
    statement = 'SELECT\n    1'
    mycli = FakeMyCli()
    unpretty_statement = key_binding_utils.handle_unprettify_binding(cast(Any, mycli), statement)
    assert unpretty_statement == 'SELECT 1;'


def test_handle_editor_command_returns_text_unchanged_when_not_editor_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(key_binding_utils.special, 'editor_command', lambda text: False)

    mycli = FakeMyCli()

    assert key_binding_utils.handle_editor_command(cast(Any, mycli), 'select 1', None, lambda: 'loaded') == 'select 1'


def test_handle_editor_command_opens_editor_reprompts_after_keyboard_interrupt_and_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_session = FakePromptSession([KeyboardInterrupt(), 'edited sql'])
    mycli = FakeMyCli(prompt_session=prompt_session)
    open_calls: list[dict[str, str]] = []

    def inputhook(*args: object, **kwargs: object) -> None:
        return None

    def loaded_message_fn() -> str:
        return 'loaded'

    def open_external_editor(*, filename: str | None, sql: str) -> tuple[str, str | None]:
        open_calls.append({'filename': cast(str, filename), 'sql': sql})
        return 'SELECT 1', None

    monkeypatch.setattr(key_binding_utils, 'PromptSession', FakePromptSession)
    monkeypatch.setattr(key_binding_utils.special, 'editor_command', lambda text: text in {'\\e', ''})
    monkeypatch.setattr(key_binding_utils.special, 'get_filename', lambda text: 'query.sql')
    monkeypatch.setattr(key_binding_utils.special, 'get_editor_query', lambda text: '' if text == '\\e' else None)
    monkeypatch.setattr(
        key_binding_utils.special,
        'open_external_editor',
        open_external_editor,
    )

    result = key_binding_utils.handle_editor_command(cast(Any, mycli), '\\e', inputhook, loaded_message_fn)

    assert result == 'edited sql'
    assert open_calls == [{'filename': 'query.sql', 'sql': 'last query'}]
    assert prompt_session.prompt_calls == [
        {'default': 'SELECT 1', 'inputhook': inputhook, 'message': loaded_message_fn},
        {'default': '', 'inputhook': inputhook, 'message': loaded_message_fn},
    ]


def test_handle_editor_command_uses_explicit_editor_query_and_raises_on_editor_error(monkeypatch: pytest.MonkeyPatch) -> None:
    mycli = FakeMyCli(prompt_session=FakePromptSession([]))

    monkeypatch.setattr(key_binding_utils.special, 'editor_command', lambda text: True)
    monkeypatch.setattr(key_binding_utils.special, 'get_filename', lambda text: 'query.sql')
    monkeypatch.setattr(key_binding_utils.special, 'get_editor_query', lambda text: 'select from text')
    monkeypatch.setattr(
        key_binding_utils.special,
        'open_external_editor',
        lambda *, filename, sql: ('', 'editor failed'),
    )

    with pytest.raises(RuntimeError, match='editor failed'):
        key_binding_utils.handle_editor_command(cast(Any, mycli), '\\eselect 1', None, lambda: 'loaded')


def test_handle_clip_command_returns_false_when_not_clip_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(key_binding_utils.special, 'clip_command', lambda text: False)

    mycli = FakeMyCli()

    assert key_binding_utils.handle_clip_command(cast(Any, mycli), 'select 1') is False


def test_handle_clip_command_copies_explicit_query(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard_calls: list[str] = []

    def copy_query_to_clipboard(*, sql: str) -> None:
        clipboard_calls.append(sql)

    monkeypatch.setattr(key_binding_utils.special, 'clip_command', lambda text: True)
    monkeypatch.setattr(key_binding_utils.special, 'get_clip_query', lambda text: 'select 1')
    monkeypatch.setattr(
        key_binding_utils.special,
        'copy_query_to_clipboard',
        copy_query_to_clipboard,
    )

    mycli = FakeMyCli()

    assert key_binding_utils.handle_clip_command(cast(Any, mycli), '\\clip select 1') is True
    assert clipboard_calls == ['select 1']


def test_handle_clip_command_uses_last_query_and_raises_on_clipboard_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(key_binding_utils.special, 'clip_command', lambda text: True)
    monkeypatch.setattr(key_binding_utils.special, 'get_clip_query', lambda text: '')
    monkeypatch.setattr(
        key_binding_utils.special,
        'copy_query_to_clipboard',
        lambda *, sql: 'clipboard failed',
    )

    mycli = FakeMyCli()

    with pytest.raises(RuntimeError, match='clipboard failed'):
        key_binding_utils.handle_clip_command(cast(Any, mycli), '\\clip')


def test_prettify_statement_returns_empty_string_for_empty_input() -> None:
    mycli = FakeMyCli()
    assert key_binding_utils.handle_prettify_binding(cast(Any, mycli), '') == ''


def test_unprettify_statement_returns_empty_string_for_empty_input() -> None:
    mycli = FakeMyCli()
    assert key_binding_utils.handle_unprettify_binding(cast(Any, mycli), '') == ''


@pytest.mark.parametrize(
    ('handler_name', 'text'),
    [
        ('handle_prettify_binding', 'SELECT 1;'),
        ('handle_unprettify_binding', 'SELECT 1;'),
    ],
)
def test_prettify_helpers_fall_back_to_input_without_trailing_semicolon_on_parse_error(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    text: str,
) -> None:
    monkeypatch.setattr(key_binding_utils.sqlglot, 'parse', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('bad sql')))

    handler = getattr(key_binding_utils, handler_name)

    mycli = FakeMyCli()

    assert handler(cast(Any, mycli), text) == 'SELECT 1'


@pytest.mark.parametrize(
    ('handler_name', 'text'),
    [
        ('handle_prettify_binding', 'SELECT 1; SELECT 2;'),
        ('handle_unprettify_binding', 'SELECT 1; SELECT 2;'),
    ],
)
def test_prettify_helpers_fall_back_when_parse_returns_multiple_statements(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    text: str,
) -> None:
    monkeypatch.setattr(key_binding_utils.sqlglot, 'parse', lambda *_args, **_kwargs: [object(), object()])

    handler = getattr(key_binding_utils, handler_name)

    mycli = FakeMyCli()

    assert handler(cast(Any, mycli), text) == 'SELECT 1; SELECT 2'

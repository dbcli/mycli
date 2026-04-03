from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mycli import clibuffer


@dataclass
class DummyDocument:
    text: str


@dataclass
class DummyBuffer:
    document: DummyDocument


@dataclass
class DummyLayout:
    buffer: DummyBuffer
    requested_names: list[str]

    def get_buffer_by_name(self, name: str) -> DummyBuffer:
        self.requested_names.append(name)
        return self.buffer


def make_app_for_text(text: str) -> tuple[SimpleNamespace, DummyLayout]:
    layout = DummyLayout(
        buffer=DummyBuffer(document=DummyDocument(text=text)),
        requested_names=[],
    )
    return SimpleNamespace(layout=layout), layout


def test_multiline_exception_handles_favorite_queries_only_after_blank_line() -> None:
    assert clibuffer._multiline_exception(r'\fs demo select 1; select 2') is False
    assert clibuffer._multiline_exception('\\fs demo select 1; select 2\n') is True


@pytest.mark.parametrize(
    ('text', 'expected'),
    (
        (r'\dt', True),
        ('select 1 //', True),
        ('select 1 \\g', True),
        ('select 1 \\G', True),
        ('select 1 \\e', True),
        ('select 1 \\edit', True),
        ('select 1 \\clip', True),
        ('help topic', True),
        ('HELP topic', True),
        ('   ', True),
        ('select 1', False),
    ),
)
def test_multiline_exception_detects_commands_terminators_and_plain_sql(
    monkeypatch,
    text: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(clibuffer.iocommands, 'get_current_delimiter', lambda: '//')
    monkeypatch.setattr(clibuffer, 'SPECIAL_COMMANDS', {'help': object(), 'exit': object()})

    assert clibuffer._multiline_exception(text) is expected


def test_cli_is_multiline_returns_false_when_multiline_mode_is_disabled(monkeypatch) -> None:
    mycli = SimpleNamespace(multi_line=False)

    def fail_get_app() -> None:
        raise AssertionError('get_app() should not be called when multiline mode is disabled')

    monkeypatch.setattr(clibuffer, 'get_app', fail_get_app)

    multiline_filter = clibuffer.cli_is_multiline(mycli)

    assert multiline_filter() is False


@pytest.mark.parametrize('text', ('help\tselect', 'HELP\nselect'))
def test_multiline_exception_recognizes_non_backslashed_special_commands_with_general_whitespace(
    monkeypatch,
    text: str,
) -> None:
    monkeypatch.setattr(clibuffer.iocommands, 'get_current_delimiter', lambda: ';')
    monkeypatch.setattr(clibuffer, 'SPECIAL_COMMANDS', {'help': object(), 'exit': object()})

    assert clibuffer._multiline_exception(text) is True


@pytest.mark.parametrize(
    ('text', 'expected'),
    (
        ('select 1', True),
        ('help select', False),
    ),
)
def test_cli_is_multiline_uses_buffer_text_when_multiline_mode_is_enabled(
    monkeypatch,
    text: str,
    expected: bool,
) -> None:
    app, layout = make_app_for_text(text)
    mycli = SimpleNamespace(multi_line=True)

    monkeypatch.setattr(clibuffer, 'get_app', lambda: app)
    monkeypatch.setattr(clibuffer.iocommands, 'get_current_delimiter', lambda: ';')
    monkeypatch.setattr(clibuffer, 'SPECIAL_COMMANDS', {'help': object()})

    multiline_filter = clibuffer.cli_is_multiline(mycli)

    assert multiline_filter() is expected
    assert layout.requested_names == [clibuffer.DEFAULT_BUFFER]

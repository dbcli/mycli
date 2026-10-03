from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mycli.packages.prompt_toolkit import multiline


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


@pytest.mark.parametrize('command', [r'\fs', '/fs', r'\favorite save', '/favorite save'])
def test_multiline_exception_handles_favorite_queries_only_after_blank_line(command: str) -> None:
    text = f'{command} demo select 1; select 2'

    assert multiline._multiline_exception(text) is False
    assert multiline._multiline_exception(f'{text}\n') is True


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
    monkeypatch.setattr(multiline.iocommands, 'get_current_delimiter', lambda: '//')
    monkeypatch.setattr(multiline, 'CASE_SENSITIVE_COMMANDS', {'Camel'})
    monkeypatch.setattr(multiline, 'CASE_INSENSITIVE_COMMANDS', {'help', 'exit'})

    assert multiline._multiline_exception(text) is expected


def test_repl_is_multiline_returns_false_when_multiline_mode_is_disabled(monkeypatch) -> None:
    mycli = SimpleNamespace(multi_line=False)

    def fail_get_app() -> None:
        raise AssertionError('get_app() should not be called when multiline mode is disabled')

    monkeypatch.setattr(multiline, 'get_app', fail_get_app)

    multiline_filter = multiline.repl_is_multiline(mycli)

    assert multiline_filter() is False


@pytest.mark.parametrize('text', ('help\tselect', 'HELP\nselect'))
def test_multiline_exception_recognizes_non_backslashed_special_commands_with_general_whitespace(
    monkeypatch,
    text: str,
) -> None:
    monkeypatch.setattr(multiline.iocommands, 'get_current_delimiter', lambda: ';')
    monkeypatch.setattr(multiline, 'CASE_SENSITIVE_COMMANDS', {'Camel'})
    monkeypatch.setattr(multiline, 'CASE_INSENSITIVE_COMMANDS', {'help', 'exit'})

    assert multiline._multiline_exception(text) is True


@pytest.mark.parametrize(
    ('text', 'expected'),
    (
        ('select 1', True),
        ('help select', False),
    ),
)
def test_repl_is_multiline_uses_buffer_text_when_multiline_mode_is_enabled(
    monkeypatch,
    text: str,
    expected: bool,
) -> None:
    app, layout = make_app_for_text(text)
    mycli = SimpleNamespace(multi_line=True)

    monkeypatch.setattr(multiline, 'get_app', lambda: app)
    monkeypatch.setattr(multiline.iocommands, 'get_current_delimiter', lambda: ';')
    monkeypatch.setattr(multiline, 'CASE_SENSITIVE_COMMANDS', {'Camel'})
    monkeypatch.setattr(multiline, 'CASE_INSENSITIVE_COMMANDS', {'help'})

    multiline_filter = multiline.repl_is_multiline(mycli)

    assert multiline_filter() is expected
    assert layout.requested_names == [multiline.DEFAULT_BUFFER]

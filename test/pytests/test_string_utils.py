# type: ignore

from mycli.packages.string_utils import sanitize_terminal_title


def test_sanitize_terminal_title_strips_ansi_sequences() -> None:
    title = '\x1b[31mmycli\x1b[0m session'

    assert sanitize_terminal_title(title) == 'mycli session'


def test_sanitize_terminal_title_replaces_newlines_with_spaces() -> None:
    title = 'schema\nquery\r\nprompt'

    assert sanitize_terminal_title(title) == 'schema query prompt'


def test_sanitize_terminal_title_removes_control_characters() -> None:
    title = 'my\x00cl\ti\x1f title\x7f'

    assert sanitize_terminal_title(title) == 'mycli title'


def test_sanitize_terminal_title_preserves_printable_text() -> None:
    title = 'db-01 / reporting'

    assert sanitize_terminal_title(title) == 'db-01 / reporting'

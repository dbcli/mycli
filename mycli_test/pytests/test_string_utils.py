# type: ignore

import pytest

from mycli.packages.utils.string_utils import bracket_ipv6_literal, sanitize_terminal_title


@pytest.mark.parametrize('host', ['::1', '2001:db8::1', 'fe80::1%en0', '::ffff:192.0.2.1'])
def test_bracket_ipv6_literal_wraps_addresses(host: str) -> None:
    assert bracket_ipv6_literal(host) == f'[{host}]'


@pytest.mark.parametrize('host', ['', 'localhost', 'db.example.com', '192.0.2.1', 'prod:readonly', '2001:db8::invalid'])
def test_bracket_ipv6_literal_preserves_non_ipv6_values(host: str) -> None:
    assert bracket_ipv6_literal(host) == host


@pytest.mark.parametrize('host', ['[::1]', '[2001:db8::1]', '[fe80::1%en0]'])
def test_bracket_ipv6_literal_preserves_existing_brackets(host: str) -> None:
    assert bracket_ipv6_literal(host) == host


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

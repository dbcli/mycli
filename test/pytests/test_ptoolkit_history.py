# type: ignore

from pathlib import Path

from mycli.packages.ptoolkit import history as history_module
from mycli.packages.ptoolkit.history import FileHistoryWithTimestamp


def test_file_history_with_timestamp_sets_filename(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'

    history = FileHistoryWithTimestamp(history_path)

    assert history.filename == history_path


def test_append_string_caches_and_stores_non_password_statement(tmp_path: Path, monkeypatch) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')
    stored: list[str] = []
    monkeypatch.setattr(history, 'store_string', stored.append)

    history.append_string('SELECT 1')

    assert history.get_strings()[0] == 'SELECT 1'
    assert stored == ['SELECT 1']


def test_append_string_does_not_store_password_change(tmp_path: Path, monkeypatch) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')
    stored: list[str] = []
    monkeypatch.setattr(history, 'store_string', stored.append)
    monkeypatch.setattr(history_module, 'is_password_change', lambda string: True)

    history.append_string("SET PASSWORD = 'secret'")

    assert history.get_strings()[0] == "SET PASSWORD = 'secret'"
    assert stored == []


def test_load_history_with_timestamp_returns_empty_when_file_is_missing(tmp_path: Path) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'missing-history.txt')

    assert history.load_history_with_timestamp() == []


def test_load_history_with_timestamp_parses_and_reverses_entries(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text(
        '# 2026-04-02 10:00:00\n+SELECT 1\n+FROM dual\n\n# 2026-04-02 11:00:00\n+SHOW DATABASES\n',
        encoding='utf-8',
    )

    history = FileHistoryWithTimestamp(history_path)

    assert history.load_history_with_timestamp() == [
        ('SHOW DATABASES', '2026-04-02 11:00:00'),
        ('SELECT 1\nFROM dual', '2026-04-02 10:00:00'),
    ]


def test_load_history_with_timestamp_ignores_empty_separator_blocks(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text(
        '# 2026-04-02 10:00:00\n\n# 2026-04-02 11:00:00\n+SELECT 1\n\ngarbage separator\n',
        encoding='utf-8',
    )

    history = FileHistoryWithTimestamp(history_path)

    assert history.load_history_with_timestamp() == [
        ('SELECT 1', '2026-04-02 11:00:00'),
    ]

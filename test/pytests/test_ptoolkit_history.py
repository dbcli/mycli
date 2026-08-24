# type: ignore

from pathlib import Path
import threading

import pytest

from mycli.packages.ptoolkit import history as history_module
from mycli.packages.ptoolkit.history import FileHistoryWithTimestamp, frecency_score


def wait_for_frecency_refresh(history: FileHistoryWithTimestamp) -> None:
    while history._frecency_thread is not None:
        thread = history._frecency_thread
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_file_history_with_timestamp_sets_filename(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'

    history = FileHistoryWithTimestamp(history_path)

    assert history.filename == history_path
    assert history.frecency == {}


def test_history_frecency_weights_normalizes_and_filters_tokens() -> None:
    entries = [
        'SELECT foo, foo, 123, \'foo\', "bar", `Mixed``Name` /* ignored */; /status',
        'select Foo FROM `mixed``name`',
    ]

    frecency = history_module._calculate_frecency(entries)

    assert frecency == {
        'select': 1.5,
        'foo': 2.5,
        'mixed`name': 1.5,
        'status': 1.0,
        'from': 0.5,
    }


def test_history_frecency_ignores_invalid_entries() -> None:
    entries = ['SELECT "unterminated', 'SELECT valid_name']

    assert history_module._calculate_frecency(entries) == {
        'select': 0.5,
        'valid_name': 0.5,
    }


@pytest.mark.parametrize(
    ('candidate', 'expected'),
    [
        ('`Mixed``Name`', 4.0),
        ('/status', 2.0),
        ('ORDER BY unseen', 1.5),
        ('foo bar', 2.0),
        ("'literal'", 0.0),
        ('"unterminated', 0.0),
    ],
)
def test_frecency_score_normalizes_and_averages_candidate_tokens(candidate: str, expected: float) -> None:
    frecency = {'mixed`name': 4.0, 'status': 2.0, 'order by': 3.0, 'foo': 3.0, 'bar': 1.0}

    assert frecency_score(candidate, frecency) == expected


def test_history_frecency_uses_only_newest_thousand_entries(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text(
        ''.join(f'\n# 2026-01-01 00:00:{index:04d}\n+SELECT token_{index}\n' for index in range(1001)),
        encoding='utf-8',
    )

    history = FileHistoryWithTimestamp(history_path)
    wait_for_frecency_refresh(history)

    assert 'token_0' not in history.frecency
    assert history.frecency['token_1000'] == 1.0
    assert history.frecency['token_1'] == pytest.approx(0.001)


def test_history_frecency_uses_configured_entry_count(tmp_path: Path) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text(
        '\n# old\n+SELECT old_token\n\n# middle\n+SELECT middle_token\n\n# new\n+SELECT new_token\n',
        encoding='utf-8',
    )

    history = FileHistoryWithTimestamp(history_path, frecency_history_entries=2)
    wait_for_frecency_refresh(history)

    assert history.frecency_history_entries == 2
    assert history.frecency['new_token'] == 1.0
    assert history.frecency['middle_token'] == 0.5
    assert 'old_token' not in history.frecency


@pytest.mark.parametrize('history_entries', [0, -1])
def test_nonpositive_history_entry_count_disables_frecency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history_entries: int,
) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text('\n# entry\n+SELECT ignored\n', encoding='utf-8')
    calculate_frecency = pytest.fail
    monkeypatch.setattr(history_module, '_calculate_frecency', calculate_frecency)

    history = FileHistoryWithTimestamp(history_path, frecency_history_entries=history_entries, frecency_refresh_interval=1)
    history.append_string('SELECT new_token')
    history.refresh_frecency()

    assert history.frecency_history_entries == 0
    assert history.frecency == {}
    assert history._frecency_thread is None


def test_initial_frecency_is_calculated_in_background(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calculation_started = threading.Event()
    release_calculation = threading.Event()

    def calculate_frecency(entries, history_entries):
        calculation_started.set()
        assert release_calculation.wait(timeout=5)
        return {'calculated': 1.0}

    monkeypatch.setattr(history_module, '_calculate_frecency', calculate_frecency)

    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')

    assert calculation_started.wait(timeout=5)
    assert history.frecency == {}
    release_calculation.set()
    wait_for_frecency_refresh(history)
    assert history.frecency == {'calculated': 1.0}


def test_history_frecency_is_not_updated_when_history_is_appended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / 'history.txt'
    history_path.write_text('\n# 2026-01-01 00:00:00\n+SELECT existing\n', encoding='utf-8')
    history = FileHistoryWithTimestamp(history_path)
    wait_for_frecency_refresh(history)
    original_frecency = history.frecency.copy()
    monkeypatch.setattr(history, 'store_string', lambda _string: None)

    history.append_string('SELECT new_token')

    assert history.frecency == original_frecency
    assert 'new_token' not in history.frecency


def test_history_frecency_is_recomputed_every_fifty_stored_entries(tmp_path: Path) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')
    wait_for_frecency_refresh(history)

    for index in range(49):
        history.append_string(f'SELECT token_{index}')
    assert history.frecency == {}

    history.append_string('SELECT token_49')
    wait_for_frecency_refresh(history)
    assert history.frecency['token_49'] == 1.0
    assert history.frecency['token_0'] == pytest.approx(1 / 50)

    for index in range(50, 99):
        history.append_string(f'SELECT token_{index}')
    assert 'token_98' not in history.frecency

    history.append_string('SELECT token_99')
    wait_for_frecency_refresh(history)
    assert history.frecency['token_99'] == 1.0
    assert history.frecency['token_49'] == pytest.approx(1 / 51)


def test_history_frecency_uses_configured_refresh_interval(tmp_path: Path) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt', frecency_refresh_interval=2)
    wait_for_frecency_refresh(history)

    history.append_string('SELECT first_token')
    assert history.frecency == {}

    history.append_string('SELECT second_token')
    wait_for_frecency_refresh(history)
    assert history.frecency_refresh_interval == 2
    assert history.frecency['second_token'] == 1.0
    assert history.frecency['first_token'] == 0.5


def test_manual_frecency_refresh_recomputes_before_interval(tmp_path: Path) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')
    wait_for_frecency_refresh(history)

    history.append_string('SELECT manual_token')
    assert history.frecency == {}

    history.refresh_frecency()
    wait_for_frecency_refresh(history)

    assert history.frecency['manual_token'] == 1.0
    assert history._frecency_entries_since_refresh == 0


@pytest.mark.parametrize('refresh_interval', [0, -1])
def test_nonpositive_refresh_interval_disables_periodic_refresh(tmp_path: Path, refresh_interval: int) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt', frecency_refresh_interval=refresh_interval)
    wait_for_frecency_refresh(history)

    for index in range(50):
        history.append_string(f'SELECT token_{index}')

    assert history.frecency_refresh_interval == 0
    assert history.frecency == {}


def test_password_changes_do_not_advance_frecency_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')
    wait_for_frecency_refresh(history)
    monkeypatch.setattr(history_module, 'is_password_change', lambda string: string == 'password change')

    for index in range(49):
        history.append_string(f'SELECT token_{index}')
    history.append_string('password change')

    assert history.frecency == {}

    history.append_string('SELECT token_49')
    wait_for_frecency_refresh(history)
    assert history.frecency['token_49'] == 1.0
    assert 'password' not in history.frecency


def test_frecency_refresh_requests_are_coalesced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt', frecency_refresh_interval=1)
    wait_for_frecency_refresh(history)
    calculation_started = threading.Event()
    release_calculation = threading.Event()
    calls: list[int] = []
    worker_threads: set[int | None] = set()

    def calculate_frecency(entries, history_entries):
        calls.append(history_entries)
        worker_threads.add(threading.current_thread().ident)
        if len(calls) == 1:
            calculation_started.set()
            assert release_calculation.wait(timeout=5)
        return {f'generation_{len(calls)}': 1.0}

    monkeypatch.setattr(history_module, '_calculate_frecency', calculate_frecency)

    history.append_string('SELECT first_token')
    assert calculation_started.wait(timeout=5)
    first_thread = history._frecency_thread
    history.append_string('SELECT second_token')
    assert history._frecency_thread is first_thread
    assert first_thread.name == 'frecency_refresh'
    assert first_thread.daemon is True
    release_calculation.set()
    wait_for_frecency_refresh(history)

    assert len(calls) == 2
    assert len(worker_threads) == 1
    assert history.frecency == {'generation_2': 1.0}


def test_frecency_failure_retains_snapshot_and_later_refresh_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt', frecency_refresh_interval=1)
    wait_for_frecency_refresh(history)
    calls = 0
    logged_errors: list[str] = []

    def calculate_frecency(entries, history_entries):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('calculation failed')
        return {'recovered': 1.0}

    monkeypatch.setattr(history_module, '_calculate_frecency', calculate_frecency)
    monkeypatch.setattr(history_module.logger, 'exception', logged_errors.append)

    history.append_string('SELECT first_token')
    wait_for_frecency_refresh(history)
    assert history.frecency == {}
    assert logged_errors == ['Failed to calculate history frecency.']

    history.append_string('SELECT second_token')
    wait_for_frecency_refresh(history)
    assert history.frecency == {'recovered': 1.0}


def test_pending_frecency_refresh_retries_after_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history = FileHistoryWithTimestamp(tmp_path / 'history.txt', frecency_refresh_interval=1)
    wait_for_frecency_refresh(history)
    calculation_started = threading.Event()
    release_calculation = threading.Event()
    calls = 0

    def calculate_frecency(entries, history_entries):
        nonlocal calls
        calls += 1
        if calls == 1:
            calculation_started.set()
            assert release_calculation.wait(timeout=5)
            raise RuntimeError('calculation failed')
        return {'recovered': 1.0}

    monkeypatch.setattr(history_module, '_calculate_frecency', calculate_frecency)

    history.append_string('SELECT first_token')
    assert calculation_started.wait(timeout=5)
    history.append_string('SELECT second_token')
    release_calculation.set()
    wait_for_frecency_refresh(history)

    assert calls == 2
    assert history.frecency == {'recovered': 1.0}


def test_frecency_thread_start_failure_can_be_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    thread_class = history_module.threading.Thread
    threads = []
    logged_errors: list[str] = []

    class FailingThread:
        def __init__(self, target, **kwargs):
            self.history = target.__self__
            threads.append(self)

        def start(self):
            raise RuntimeError('thread failed')

    monkeypatch.setattr(history_module.threading, 'Thread', FailingThread)
    monkeypatch.setattr(history_module.logger, 'exception', logged_errors.append)

    history = FileHistoryWithTimestamp(tmp_path / 'history.txt')

    assert history is threads[0].history
    assert history._frecency_thread is None
    assert logged_errors == ['Failed to start history frecency calculation.']

    monkeypatch.setattr(history_module.threading, 'Thread', thread_class)
    history._request_frecency_refresh()
    wait_for_frecency_refresh(history)

    assert history.frecency == {}


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

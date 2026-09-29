from collections.abc import Iterator
from concurrent.futures import Future
from io import StringIO
import signal
from threading import Event, get_ident
from time import monotonic
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from pymysql.connections import Connection
from pymysql.cursors import Cursor, SSCursor
import pytest

from mycli import query_runner
from mycli import sqlexecute as sqlexecute_module
from mycli.constants import DEFAULT_WIDTH, TTY_ERASE_LINE, QueryState
from mycli.packages.sqlresult import SQLResult
from mycli.query_runner import BackgroundCursor, BackgroundSSCursor, QueryCancelled, QueryRunner
from mycli.sqlexecute import SQLExecute
from test.utils import dbtest  # type: ignore[attr-defined]


@pytest.fixture
def runner() -> Iterator[QueryRunner]:
    instance = QueryRunner(show_state_interval=0.5)
    yield instance
    instance.close()


@pytest.mark.parametrize(
    'client',
    [None, SimpleNamespace(), SimpleNamespace(sqlexecute=None), SimpleNamespace(sqlexecute=SimpleNamespace(query_runner=object()))],
)
def test_runner_for_returns_none_without_valid_runner(client: Any) -> None:
    assert query_runner.runner_for(client) is None


def test_runner_for_returns_attached_runner(runner: QueryRunner) -> None:
    client = SimpleNamespace(sqlexecute=SimpleNamespace(query_runner=runner))
    assert query_runner.runner_for(client) is runner


@pytest.mark.parametrize('attached', [False, True])
def test_rendering_output_preserves_arguments_and_result(runner: QueryRunner, attached: bool) -> None:
    runner.show_state = False
    client = SimpleNamespace(sqlexecute=SimpleNamespace(query_runner=runner if attached else None))

    @query_runner.rendering_output
    def render(owner: Any, value: str, *, suffix: str) -> str:
        assert owner is client
        assert runner._render_depth == int(attached)
        return value + suffix

    assert render(client, 'row', suffix='!') == 'row!'
    assert runner._render_depth == 0
    assert render.__name__ == 'render'


def test_rendering_output_cleans_up_after_failure(runner: QueryRunner) -> None:
    runner.show_state = False
    client = SimpleNamespace(sqlexecute=SimpleNamespace(query_runner=runner))
    error = ValueError('format failed')

    @query_runner.rendering_output
    def render(owner: Any) -> None:
        assert runner._render_depth == 1
        raise error

    with pytest.raises(ValueError) as raised:
        render(client)

    assert raised.value is error
    assert runner._render_depth == 0
    assert runner._render_stop.is_set()


@pytest.mark.parametrize('error', [OSError('unavailable'), ValueError('closed')])
def test_render_ticks_stops_after_display_failure(
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    runner.started = 0.0
    monkeypatch.setattr(query_runner, 'monotonic', lambda: 2.0)
    wait = Mock(side_effect=[False, True])
    monkeypatch.setattr(runner._render_stop, 'wait', wait)
    display = Mock(side_effect=error)
    monkeypatch.setattr(runner, '_display', display)

    with caplog.at_level('DEBUG', logger='mycli.query_runner'):
        runner._render_ticks()

    display.assert_called_once_with(2.0, QueryState.RENDERING.value)
    wait.assert_called_once_with(runner.interval)
    assert 'Rendering status display failed' in caplog.text


def test_close_control_discards_connection_even_when_close_fails(
    runner: QueryRunner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    control = Mock()
    control.close.side_effect = OSError('connection lost')
    runner.control = control

    with caplog.at_level('DEBUG', logger='mycli.query_runner'):
        runner._close_control()

    control.close.assert_called_once_with()
    assert vars(runner)['control'] is None
    assert 'Closing query monitor failed' in caplog.text


@pytest.mark.parametrize('cancel', [False, True])
def test_monitor_skips_query_completed_during_connection(runner: QueryRunner, cancel: bool) -> None:
    done = Event()
    control = Mock()

    def connect() -> Any:
        done.set()
        return control

    runner.connect_control = connect

    assert runner._control(42, done, cancel=cancel) == QueryState.UNKNOWN.value
    control.cursor.assert_not_called()
    assert runner.control is control


@pytest.mark.parametrize('method', ['write', 'flush'])
@pytest.mark.parametrize('error', [OSError('unavailable'), ValueError('closed')])
def test_clear_resets_visibility_when_terminal_fails(
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    method: str,
    error: Exception,
) -> None:
    output = Mock()
    getattr(output, method).side_effect = error
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.visible = True

    with caplog.at_level('DEBUG', logger='mycli.query_runner'):
        runner._clear()

    assert not runner.visible
    assert 'Clearing query status failed' in caplog.text
    output.write.assert_called_once_with(TTY_ERASE_LINE)


def test_forced_cancel_tolerates_socket_shutdown_failure(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    started, released = Event(), Event()
    connection = Connection(defer_connect=True)
    connection.server_thread_id = (42,)
    sock = Mock()
    connection._sock = sock
    runner.attach(connection, Mock())
    interrupts = 2

    def shutdown(how: int) -> None:
        released.set()
        raise OSError('socket already disconnected')

    sock.shutdown.side_effect = shutdown

    class InterruptEvent(Event):
        def wait(self, timeout: float | None = None) -> bool:
            nonlocal interrupts
            assert started.wait(2)
            if interrupts:
                interrupts -= 1
                raise KeyboardInterrupt
            return super().wait(timeout)

    def execute() -> None:
        started.set()
        assert released.wait(2)

    monkeypatch.setattr(query_runner, 'Event', InterruptEvent)
    monkeypatch.setattr(runner, '_control', Mock(return_value='Cancelling'))

    with pytest.raises(QueryCancelled) as raised:
        runner.call(execute)

    assert raised.value.disconnected
    sock.shutdown.assert_called_once_with(query_runner.socket.SHUT_RDWR)
    assert not connection.open
    assert runner.call(lambda: 'next query') == 'next query'


def test_work_runs_on_single_background_thread(runner: QueryRunner) -> None:
    first = runner.call(get_ident)
    assert first != get_ident()
    assert runner.call(get_ident) == first


def test_nested_work_does_not_deadlock(runner: QueryRunner) -> None:
    assert runner.call(lambda: runner.call(get_ident)) == runner.worker_id


def test_sigint_handler_is_restored_after_failure(runner: QueryRunner) -> None:
    previous = signal.getsignal(signal.SIGINT)

    def fail() -> None:
        raise ValueError('failure')

    with pytest.raises(ValueError):
        runner.call(fail)
    assert signal.getsignal(signal.SIGINT) == previous


def test_worker_exception_propagates(runner: QueryRunner) -> None:
    error = ValueError('query failed')

    def fail() -> None:
        raise error

    with pytest.raises(ValueError) as raised:
        runner.call(fail)
    assert raised.value is error
    assert runner.call(lambda: 42) == 42


def test_interrupt_at_query_completion_is_not_swallowed(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class InterruptOnCompletion(Event):
        def wait(self, timeout: float | None = None) -> bool:
            completed = super().wait(timeout)
            if completed:
                signal.raise_signal(signal.SIGINT)
            return completed

    monkeypatch.setattr(query_runner, 'Event', InterruptOnCompletion)
    control = Mock()
    runner.show_state = False
    monkeypatch.setattr(runner, '_control', control)
    with pytest.raises(QueryCancelled) as raised:
        runner.call(lambda: 42)
    assert not raised.value.disconnected
    control.assert_not_called()


def test_interrupt_while_finishing_monitor_is_not_swallowed(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class CompleteAfterPoll(Event):
        first_wait = True

        def wait(self, timeout: float | None = None) -> bool:
            if self.first_wait:
                self.first_wait = False
                return False
            return super().wait(timeout)

    class InterruptingFuture(Future[str]):
        def result(self, timeout: float | None = None) -> str:
            signal.raise_signal(signal.SIGINT)
            return 'executing'

    runner.show_state = True
    runner.interval = 60
    monkeypatch.setattr(query_runner, 'Event', CompleteAfterPoll)
    with monkeypatch.context() as patch:
        patch.setattr(runner.monitor, 'submit', lambda *args, **kwargs: InterruptingFuture())
        with pytest.raises(QueryCancelled) as raised:
            runner.call(lambda: 42)
    assert not raised.value.disconnected


@pytest.mark.parametrize('cursorclass, expected', [(Cursor, BackgroundCursor), (SSCursor, BackgroundSSCursor)])
def test_attach_selects_background_cursor(runner: QueryRunner, cursorclass: type[Cursor], expected: type[Cursor]) -> None:
    connection = Connection(defer_connect=True, cursorclass=cursorclass)
    runner.attach(connection, Mock())
    assert connection.cursorclass is expected


@pytest.mark.parametrize('cursorclass', [Cursor, SSCursor])
def test_detach_restores_original_cursor(runner: QueryRunner, cursorclass: type[Cursor]) -> None:
    connection = Connection(defer_connect=True, cursorclass=cursorclass)
    runner.attach(connection, Mock())
    runner.detach()
    assert connection.cursorclass is cursorclass
    assert not hasattr(connection, '_mycli_query_runner')


def test_cursor_execution_uses_worker(runner: QueryRunner) -> None:
    connection = Connection(defer_connect=True)
    connection.server_thread_id = (42,)
    runner.attach(connection, Mock())
    cursor = connection.cursor()
    thread_ids = []

    def query(sql: str) -> int:
        thread_ids.append(get_ident())
        return 1

    cursor._query = query
    cursor.execute('select 1')
    assert thread_ids == [runner.worker_id]


def test_monitor_queries_separate_connection(runner: QueryRunner) -> None:
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchall.return_value = [(42, 'user', 'host', 'db', 'Query', 3, 'Sending data', 'select')]
    connection = Mock()
    connection.cursor.return_value = cursor
    runner.connect_control = Mock(return_value=connection)
    assert runner.monitor.submit(runner._control, 42, Event()).result() == 'Sending data'
    cursor.execute.assert_called_once_with('SHOW PROCESSLIST')


def test_finished_query_is_not_killed(runner: QueryRunner) -> None:
    done = Event()
    done.set()
    factory = Mock()
    runner.connect_control = factory
    assert runner._control(42, done, cancel=True) == QueryState.UNKNOWN
    factory.assert_not_called()


def test_empty_server_state_reuses_last_polled_state(runner: QueryRunner) -> None:
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.description = [('Id',), ('User',), ('Host',), ('db',), ('Command',), ('Time',), ('State',)]
    cursor.fetchall.side_effect = [
        [(42, 'user', 'host', 'db', 'Query', 1, 'Sending data')],
        [(42, 'user', 'host', 'db', 'Query', 2, '')],
    ]
    runner.control = Mock()
    runner.control.cursor.return_value = cursor

    assert runner._control(42, Event()) == 'Sending data'
    assert runner._control(42, Event()) == 'Sending data'


@pytest.mark.parametrize('state', [QueryState.RENDERING.value, 'Cancelling', QueryState.UNKNOWN.value])
def test_display_does_not_replace_server_state(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    monkeypatch.setattr(query_runner.sys, 'stderr', StringIO())
    runner.previous_state = 'Sending data'
    runner._display(2, state)
    assert runner.previous_state == 'Sending data'


@pytest.mark.parametrize('new_statement', [False, True])
def test_only_new_statements_reset_server_state(runner: QueryRunner, new_statement: bool) -> None:
    runner.started = monotonic()
    runner.previous_state = 'Sending data'
    runner.call(lambda: None, new_statement=new_statement)
    assert runner.previous_state == (QueryState.INITIAL.value if new_statement else 'Sending data')


def test_reset_progress_resets_server_state(runner: QueryRunner) -> None:
    runner.previous_state = 'Sending data'
    runner.reset_progress()
    assert runner.previous_state == QueryState.INITIAL.value


def test_monitor_failure_is_nonfatal(runner: QueryRunner) -> None:
    runner.connect_control = Mock(side_effect=OSError('unavailable'))
    assert runner._control(42, Event()) == QueryState.UNKNOWN


def test_cancel_sends_kill_query(runner: QueryRunner) -> None:
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    runner.control = Mock()
    runner.control.cursor.return_value = cursor
    assert runner._control(42, Event(), cancel=True) == 'Cancelling'
    cursor.execute.assert_called_once_with('KILL QUERY 42')


@pytest.mark.parametrize('forced', [False, True])
def test_interrupt_waits_for_worker_before_returning(
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
    forced: bool,
) -> None:
    started, released = Event(), Event()
    connection = Connection(defer_connect=True)
    connection.server_thread_id = (42,)
    connection._sock = Mock()
    connection._sock.shutdown.side_effect = lambda *_: released.set()
    runner.attach(connection, Mock())
    interrupts = 2 if forced else 1

    class InterruptEvent(Event):
        def wait(self, timeout: float | None = None) -> bool:
            nonlocal interrupts
            assert started.wait(2)
            if interrupts:
                interrupts -= 1
                raise KeyboardInterrupt
            return super().wait(timeout)

    def control(*args: Any) -> str:
        if not forced:
            released.set()
        return 'Cancelling'

    def execute() -> None:
        started.set()
        assert released.wait(2)

    monkeypatch.setattr(query_runner, 'Event', InterruptEvent)
    monkeypatch.setattr(runner, '_control', control)
    with pytest.raises(QueryCancelled) as raised:
        runner.call(execute)
    assert raised.value.disconnected is forced
    assert released.is_set()
    assert runner.call(lambda: 'next query') == 'next query'


def test_status_is_transient(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner._display(2, 'Waiting')
    assert len(output.getvalue().removeprefix(TTY_ERASE_LINE)) == 15
    runner.stop_rendering()
    assert output.getvalue().endswith(TTY_ERASE_LINE)
    assert not runner.visible


def test_status_uses_stderr_width_with_redirected_stdout(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(output, 'fileno', lambda: 42)
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    monkeypatch.setattr(query_runner.sys, 'stdout', StringIO())
    monkeypatch.setattr(query_runner.sys, '__stdout__', StringIO())
    monkeypatch.setenv('COLUMNS', '120')
    descriptors: list[int] = []

    def terminal_size(fd: int) -> Any:
        descriptors.append(fd)
        return query_runner.os.terminal_size((20, 24))

    monkeypatch.setattr(query_runner.os, 'get_terminal_size', terminal_size)
    runner._display(3, 'waiting for table metadata lock')

    assert descriptors == [42]
    assert len(output.getvalue().removeprefix(TTY_ERASE_LINE)) == 19


@pytest.mark.parametrize('error', [OSError('not a terminal'), ValueError('closed descriptor')])
def test_status_width_falls_back_when_stderr_size_is_unavailable(
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    output = StringIO()
    monkeypatch.setattr(output, 'fileno', lambda: 42)
    monkeypatch.setattr(query_runner.sys, 'stderr', output)

    def terminal_size(fd: int) -> Any:
        raise error

    monkeypatch.setattr(query_runner.os, 'get_terminal_size', terminal_size)
    runner._display(3, 'x' * 120)
    assert len(output.getvalue().removeprefix(TTY_ERASE_LINE)) == DEFAULT_WIDTH - 1


@pytest.mark.parametrize('interval', [float('nan'), float('inf')])
def test_invalid_interval_defaults_to_half_second(interval: float) -> None:
    instance = QueryRunner(interval)
    try:
        assert instance.interval == 0.5
    finally:
        instance.close()


def test_non_tty_suppresses_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_runner.sys, 'stderr', StringIO())
    instance = QueryRunner(True)
    try:
        assert not instance.show_state
    finally:
        instance.close()


@pytest.mark.parametrize('state', [QueryState.RENDERING, QueryState.TRANSFORMING])
def test_rendering_keeps_elapsed_time_advancing(
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
    state: QueryState,
) -> None:
    runner.show_state = True
    runner.interval = 0.01
    runner.started = monotonic() - 2
    updates: list[tuple[float, str]] = []
    updated = Event()

    def display(elapsed: float, state: str) -> None:
        updates.append((elapsed, state))
        if len(updates) >= 2:
            updated.set()

    monkeypatch.setattr(runner, '_display', display)
    monitor = Mock()
    monkeypatch.setattr(runner, '_control', monitor)
    with runner.rendering(state):
        assert updated.wait(2)
    assert updates[1][0] > updates[0][0] >= 2
    assert all(displayed == state for _, displayed in updates)
    monitor.assert_not_called()


def test_fetch_does_not_reset_statement_start(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_runner, 'monotonic', lambda: 10.0)
    runner.call(lambda: None)
    monkeypatch.setattr(query_runner, 'monotonic', lambda: 20.0)
    runner.call(lambda: None, new_statement=False)
    assert runner.started == 10.0
    runner.call(lambda: None)
    assert runner.started == 20.0


def test_fetch_handoffs_share_query_update_deadline(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.show_state = runner.visible = True
    runner.started = 0.0
    runner._next_update = 0.5
    display = Mock()
    monkeypatch.setattr(runner, '_display', display)

    for now in (0.5, 0.6, 0.9, 1.0, 1.1, 1.5):
        monkeypatch.setattr(query_runner, 'monotonic', Mock(return_value=now))
        runner.call(lambda: None, new_statement=False)

    assert [call.args[0] for call in display.call_args_list] == [0.5, 1.0, 1.5]


def test_fetch_polling_shares_query_update_deadline(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class PollOnceEvent(Event):
        def __init__(self) -> None:
            super().__init__()
            self.polled = False

        def wait(self, timeout: float | None = None) -> bool:
            if not self.polled:
                self.polled = True
                return False
            return super().wait(timeout)

    runner.show_state = True
    runner.started = 0.0
    runner._next_update = 1.0
    runner._state_requested = True
    control = Mock(return_value='Executing')
    display = Mock()
    monkeypatch.setattr(query_runner, 'Event', PollOnceEvent)
    monkeypatch.setattr(runner, '_control', control)
    monkeypatch.setattr(runner, '_display', display)

    for now in (0.6, 0.7, 0.8):
        monkeypatch.setattr(query_runner, 'monotonic', Mock(return_value=now))
        runner.call(lambda: None, new_statement=False)
    display.assert_not_called()
    control.assert_not_called()

    monkeypatch.setattr(query_runner, 'monotonic', lambda: 1.0)
    runner.call(lambda: None, new_statement=False)
    display.assert_called_once()
    control.assert_called_once()


def test_render_ticks_share_handoff_deadline(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.started = 0.0
    display = Mock()
    monkeypatch.setattr(runner, '_display', display)
    runner._handoff_to_rendering(1.0)
    monkeypatch.setattr(query_runner, 'monotonic', lambda: 1.1)
    monkeypatch.setattr(runner._render_stop, 'wait', Mock(side_effect=[False, True]))

    runner._render_ticks()

    display.assert_called_once_with(1.0, QueryState.RENDERING.value)


def test_new_statement_resets_update_deadline(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner._next_update = 999.0
    runner._state_requested = True
    monkeypatch.setattr(query_runner, 'monotonic', lambda: 10.0)
    runner.call(lambda: None)
    assert runner._next_update == 10.5
    assert not runner._state_requested


@pytest.mark.parametrize('error', [ValueError('formatting'), KeyboardInterrupt()])
@pytest.mark.parametrize('state', [QueryState.RENDERING, QueryState.TRANSFORMING])
def test_rendering_error_stops_ticker(runner: QueryRunner, error: BaseException, state: QueryState) -> None:
    runner.show_state = True
    with pytest.raises(type(error)):
        with runner.rendering(state):
            thread = runner._render_thread
            assert thread is not None
            raise error
    assert thread is not None and not thread.is_alive()
    assert runner._render_thread is None
    assert not runner.visible
    assert runner._render_state == QueryState.RENDERING


def test_fetch_after_output_does_not_redisplay_rendering(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.show_state = True
    runner._display(1, QueryState.RENDERING)
    runner.stop_rendering()
    before_fetch = output.getvalue()

    runner.call(lambda: None, new_statement=False)

    assert output.getvalue() == before_fetch
    assert not runner.visible


def test_disabled_query_display_has_no_handoff(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.call(lambda: None)
    assert output.getvalue() == ''


def test_pager_suppresses_query_handoff(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.show_state = True
    with runner.suspend_display():
        runner.call(lambda: None)
    assert output.getvalue() == ''


def test_failed_query_clears_status_without_rendering(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.show_state = True
    runner._display(1, 'Executing')

    def fail() -> None:
        raise ValueError('query failed')

    with pytest.raises(ValueError):
        runner.call(fail)
    assert QueryState.RENDERING not in output.getvalue()
    assert output.getvalue().endswith(TTY_ERASE_LINE)
    assert not runner.visible


def test_successful_visible_query_hands_off_to_rendering(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.show_state = True
    times = iter([0.0, 1.0])
    monkeypatch.setattr(query_runner, 'monotonic', lambda: next(times))
    runner._display(1, 'Executing')
    runner.call(lambda: None)
    assert output.getvalue().endswith(QueryState.RENDERING)
    assert runner.visible


@pytest.mark.parametrize('state', [QueryState.RENDERING, QueryState.TRANSFORMING])
def test_disabled_rendering_starts_no_thread(runner: QueryRunner, state: QueryState) -> None:
    with runner.rendering(state):
        assert runner._render_thread is None


def test_nested_rendering_uses_one_ticker(runner: QueryRunner) -> None:
    runner.show_state = True
    with runner.rendering():
        thread = runner._render_thread
        with runner.rendering():
            assert runner._render_thread is thread
        assert thread is not None and thread.is_alive()
    assert not thread.is_alive()


@pytest.mark.parametrize('state', [QueryState.RENDERING, QueryState.TRANSFORMING])
def test_pager_suppresses_rendering(runner: QueryRunner, state: QueryState) -> None:
    runner.show_state = True
    with runner.suspend_display():
        with runner.rendering(state):
            assert runner._render_thread is None
    assert runner._suppressed == 0


def test_nested_processing_restores_outer_state_after_error(runner: QueryRunner) -> None:
    runner.show_state = True
    with runner.rendering(QueryState.TRANSFORMING):
        thread = runner._render_thread
        assert vars(runner)['_render_state'] == QueryState.TRANSFORMING
        with pytest.raises(ValueError, match='format failed'):
            with runner.rendering():
                assert runner._render_thread is thread
                assert vars(runner)['_render_state'] == QueryState.RENDERING
                raise ValueError('format failed')
        assert vars(runner)['_render_state'] == QueryState.TRANSFORMING
        assert thread is not None and thread.is_alive()
    assert vars(runner)['_render_state'] == QueryState.RENDERING
    assert not thread.is_alive()


def test_database_handoff_uses_active_transform_state(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setattr(query_runner.sys, 'stderr', output)
    runner.show_state = True
    runner.interval = 60
    times = iter([0.0, 60.0])
    monkeypatch.setattr(query_runner, 'monotonic', lambda: next(times))
    with runner.rendering(QueryState.TRANSFORMING):
        runner._display(1, 'Executing')
        runner.call(lambda: None)
        assert output.getvalue().endswith(QueryState.TRANSFORMING.value)
    assert not runner.visible


def test_transform_to_rendering_preserves_elapsed_time(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.started = 10.0
    runner.show_state = False
    times = iter([12.0, 12.5])
    monkeypatch.setattr(query_runner, 'monotonic', lambda: next(times))
    display = Mock()
    monkeypatch.setattr(runner, '_display', display)

    for elapsed, state in ((2.0, QueryState.TRANSFORMING), (2.5, QueryState.RENDERING)):
        with runner.rendering(state):
            with monkeypatch.context() as patch:
                patch.setattr(runner._render_stop, 'wait', Mock(side_effect=[False, True]))
                runner._render_ticks()
            display.assert_called_with(elapsed, state.value)
            assert runner.started == 10.0
    assert display.call_count == 2


def test_worker_pauses_rendering_ticks(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.show_state = True
    runner.interval = 0.01
    released, rendered = Event(), Event()
    updates: list[str] = []

    def display(elapsed: float, state: str) -> None:
        updates.append(state)
        if state == QueryState.RENDERING:
            assert released.is_set()
            rendered.set()
        else:
            released.set()

    monkeypatch.setattr(runner, '_display', display)
    monkeypatch.setattr(runner, '_control', lambda *args: 'Executing')
    with runner.rendering():
        runner.call(lambda: released.wait(2))
        assert rendered.wait(2)
    assert updates[-1] == QueryState.RENDERING


def test_status_is_delayed_and_refreshed(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    released = Event()
    first_displayed = Event()
    updates: list[tuple[float, str]] = []
    times = iter([0.0, 0.5, 1.0, 1.5, 2.0])
    runner.show_state = True
    monkeypatch.setattr(query_runner, 'monotonic', lambda: next(times))

    def control(*args: Any) -> str:
        assert first_displayed.wait(2)
        return 'waiting for lock'

    monkeypatch.setattr(runner, '_control', control)

    def display(elapsed: float, state: str) -> None:
        updates.append((elapsed, state))
        runner.visible = True
        first_displayed.set()
        if len(updates) == 2:
            released.set()

    monkeypatch.setattr(runner, '_display', display)
    runner.call(lambda: released.wait(2))
    assert updates == [(0.5, 'finding state'), (1.0, 'waiting for lock'), (1.5, QueryState.RENDERING.value)]


def test_replacing_connection_discards_monitor(runner: QueryRunner) -> None:
    first = Connection(defer_connect=True)
    second = Connection(defer_connect=True)
    runner.attach(first, Mock())
    control = Mock()
    runner.control = control
    runner.attach(second, Mock())
    control.close.assert_called_once()
    assert vars(runner)['control'] is None
    assert not hasattr(first, '_mycli_query_runner')


def test_monitor_completion_precedes_next_query(runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    released, monitor_finished = Event(), Event()
    runner.show_state = True
    ticks = iter([0.0, 2.0, 3.0, 4.0])
    monkeypatch.setattr(query_runner, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(runner, '_display', lambda *args: None)

    def monitor(connection_id: int, done: Event) -> str:
        released.set()
        assert done.wait(2)
        monitor_finished.set()
        return 'Running'

    monkeypatch.setattr(runner, '_control', monitor)
    runner.call(lambda: released.wait(2))
    assert monitor_finished.is_set()


@dbtest
@pytest.mark.parametrize('unbuffered', [False, True])
def test_real_cursor_streams_results_in_worker(executor: SQLExecute, runner: QueryRunner, unbuffered: bool) -> None:
    executor.connect(unbuffered=unbuffered)
    executor.set_query_runner(runner)
    try:
        results = executor.run('SELECT 1 UNION ALL SELECT 2; SELECT 3')
        first = next(results)
        assert isinstance(first.rows, BackgroundSSCursor if unbuffered else BackgroundCursor)
        assert list(first.rows) == [(1,), (2,)]
        second = next(results)
        assert second.rows is not None
        assert list(second.rows) == [(3,)]
        with pytest.raises(StopIteration):
            next(results)
    finally:
        executor.set_query_runner(None)


@dbtest
def test_special_dispatch_stays_on_main_thread(
    executor: SQLExecute,
    runner: QueryRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_thread = get_ident()

    def special(cursor: Cursor, sql: str) -> Iterator[SQLResult]:
        assert get_ident() == main_thread
        cursor.execute('SELECT 42')
        assert runner.worker_id != main_thread
        yield executor.get_result(cursor)

    monkeypatch.setattr(sqlexecute_module, 'execute', special)
    executor.set_query_runner(runner)
    try:
        rows = next(executor.run('/example')).rows
        assert rows is not None
        assert list(rows) == [(42,)]
    finally:
        executor.set_query_runner(None)


@dbtest
def test_monitor_does_not_inherit_database_or_init_command(executor: SQLExecute) -> None:
    executor.connect(init_command='SET @mycli_monitor_probe = 1')
    with executor.connect_query_monitor() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATABASE(), @mycli_monitor_probe')
            assert cursor.fetchone() == (None, None)
        assert connection.connect_timeout == 2
        assert connection._read_timeout == 2
        assert connection._write_timeout == 2


@dbtest
def test_lock_wait_state_is_displayed(executor: SQLExecute, runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    states: list[str] = []
    name = f'mycli_query_runner_{executor.connection_id}'
    runner.show_state = True
    runner.interval = 0.05
    with executor.connect_query_monitor() as holder:
        with holder.cursor() as cursor:
            cursor.execute('SELECT GET_LOCK(%s, 0)', (name,))

            def display(elapsed: float, state: str) -> None:
                states.append(state)
                if 'lock' in state.lower():
                    cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))

            monkeypatch.setattr(runner, '_display', display)
            executor.set_query_runner(runner)
            try:
                list(executor.run(f"SELECT GET_LOCK('{name}', 5)"))
                assert any('lock' in state.lower() for state in states)
            finally:
                list(executor.run(f"SELECT RELEASE_LOCK('{name}')"))
                executor.set_query_runner(None)


@dbtest
def test_database_reconnect_retains_runner(executor: SQLExecute, runner: QueryRunner) -> None:
    executor.set_query_runner(runner)
    previous = executor.conn
    try:
        executor.connect()
        assert executor.conn is not previous
        assert runner.connection is executor.conn
        assert isinstance(next(executor.run('SELECT 1')).rows, BackgroundCursor)
    finally:
        executor.set_query_runner(None)


@dbtest
def test_database_session_survives_kill_query(executor: SQLExecute, runner: QueryRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    executor.set_query_runner(runner)
    waits = 0

    class InterruptEvent(Event):
        def wait(self, timeout: float | None = None) -> bool:
            nonlocal waits
            waits += 1
            if waits == 5:
                signal.raise_signal(signal.SIGINT)
            return super().wait(timeout)

    connection = executor.conn
    try:
        monkeypatch.setattr(query_runner, 'Event', InterruptEvent)
        with pytest.raises(QueryCancelled):
            list(executor.run('SELECT SLEEP(10)'))
        assert executor.conn is connection
        result = list(executor.run('SELECT 42'))[0]
        assert result.rows is not None
        assert list(result.rows) == [(42,)]
    finally:
        executor.set_query_runner(None)

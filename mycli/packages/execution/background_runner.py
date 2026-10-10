"""Serialized REPL database work with independent query monitoring."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from functools import wraps
import logging
import math
import os
import signal
import socket
import sys
from threading import Event, RLock, Thread, get_ident, main_thread
from time import monotonic
from types import FrameType
from typing import Any, Callable, Iterator, TypeVar

from prompt_toolkit.utils import get_cwidth
from pymysql import OperationalError
from pymysql.connections import Connection, MySQLResult
from pymysql.constants import ER
from pymysql.cursors import Cursor, SSCursor

from mycli.constants import DEFAULT_WIDTH, TTY_ERASE_LINE, QueryState

T = TypeVar('T')
logger = logging.getLogger(__name__)


def runner_for(client: Any) -> BackgroundRunner | None:
    runner = getattr(getattr(client, 'sql_execute', None), 'background_runner', None)
    return runner if isinstance(runner, BackgroundRunner) else None


def rendering_output(method: Callable[..., T]) -> Callable[..., T]:
    @wraps(method)
    def wrapped(client: Any, *args: Any, **kwargs: Any) -> T:
        runner = runner_for(client)
        with runner.rendering() if runner else nullcontext():
            return method(client, *args, **kwargs)

    return wrapped


class QueryCancelled(Exception):
    def __init__(self, disconnected: bool) -> None:
        super().__init__('Query cancelled.')
        self.disconnected = disconnected


def background(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def call(cursor: Cursor, *args: Any, **kwargs: Any) -> Any:
        runner = getattr(cursor.connection, '_mycli_background_runner', None)
        if runner is None:
            return method(cursor, *args, **kwargs)
        try:
            return runner.call(lambda: method(cursor, *args, **kwargs), new_statement=method.__name__ == 'execute')
        except QueryCancelled:
            if isinstance(cursor, BackgroundSSCursor):
                cursor._cancelled_result = cursor._result
            raise

    return call


class BackgroundCursor(Cursor):
    execute = background(Cursor.execute)
    nextset = background(Cursor.nextset)
    close = background(Cursor.close)


class BackgroundSSCursor(SSCursor):
    connection: Connection | None
    _result: MySQLResult | None
    _cancelled_result: MySQLResult | None = None

    execute = background(SSCursor.execute)
    nextset = background(SSCursor.nextset)
    fetchone = background(SSCursor.fetchone)
    fetchmany = background(SSCursor.fetchmany)
    scroll = background(SSCursor.scroll)

    @background
    def close(self) -> None:
        connection = self.connection
        if connection is None:
            return
        try:
            if connection.open:
                super().close()
        except OperationalError as exc:
            if exc.args[0] != ER.QUERY_INTERRUPTED or self._result is None or self._result is not self._cancelled_result:
                raise
            self._discard_result()
        finally:
            if not connection.open:
                # A disconnected stream cannot be drained, even during destruction.
                self._discard_result()
            if self.connection is None:
                self._cancelled_result = None

    def _discard_result(self) -> None:
        if self._result is not None:
            self._result.unbuffered_active = False
            self._result.has_next = False
            self._result.connection = None
        self._result = None
        self.connection = None

    __del__ = close


class BackgroundRunner:
    def __init__(self, show_state_interval: float = 0.5) -> None:
        self.show_state = math.isfinite(show_state_interval) and show_state_interval > 0 and sys.stderr.isatty()
        self.interval = show_state_interval if self.show_state else 0.5
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='query')
        self.monitor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='query_state')
        self.worker_id: int | None = None
        self.connection: Connection | None = None
        self.control: Connection | None = None
        self.connect_control: Callable[[], Connection] | None = None
        self.cursorclass: Any = None
        self.visible = False
        self.previous_state = QueryState.INITIAL.value
        self.started: float | None = None
        self._next_update = 0.0
        self._state_requested = False
        self._display_lock = RLock()
        self._busy = False
        self._output_started = False
        self._suppressed = 0
        self._render_depth = 0
        self._render_state = QueryState.RENDERING
        self._render_stop = Event()
        self._render_thread: Thread | None = None

    @contextmanager
    def rendering(self, state: QueryState = QueryState.RENDERING) -> Iterator[None]:
        with self._display_lock:
            outer = self._render_depth == 0
            self._render_depth += 1
            previous_state = self._render_state
            self._render_state = state
        if outer:
            with self._display_lock:
                self._output_started = False
                self._render_stop.clear()
            if self.show_state and not self._suppressed:
                self._render_thread = Thread(target=self._render_ticks, name='rendering_state', daemon=True)
                self._render_thread.start()
        try:
            yield
        finally:
            if outer:
                self.stop_rendering()
            with self._display_lock:
                self._render_depth -= 1
                self._render_state = previous_state

    def _render_ticks(self) -> None:
        while not self._render_stop.wait(self.interval):
            with self._display_lock:
                if self.started is not None and not self._busy and not self._output_started and not self._suppressed:
                    elapsed = monotonic() - self.started
                    if elapsed >= self.interval:
                        try:
                            self._display_if_due(elapsed, self._local_state().value)
                        except (OSError, ValueError):
                            logger.debug('Rendering status display failed', exc_info=True)
                            return

    def reset_progress(self) -> None:
        self.stop_rendering()
        with self._display_lock:
            self.started = None
            self._next_update = 0.0
            self._state_requested = False
            self.previous_state = QueryState.INITIAL.value

    def stop_rendering(self) -> None:
        with self._display_lock:
            self._output_started = True
            self._render_stop.set()
            self._clear()
        if self._render_thread is not None:
            self._render_thread.join()
            self._render_thread = None

    @contextmanager
    def suspend_display(self) -> Iterator[None]:
        with self._display_lock:
            self._suppressed += 1
            self._clear()
        try:
            yield
        finally:
            with self._display_lock:
                self._suppressed -= 1

    def attach(self, connection: Connection, connect_control: Callable[[], Connection]) -> None:
        self.detach()
        self.connection = connection
        self.connect_control = connect_control
        self.cursorclass = connection.cursorclass
        connection.cursorclass = BackgroundSSCursor if issubclass(self.cursorclass, SSCursor) else BackgroundCursor
        connection._mycli_background_runner = self  # type: ignore[attr-defined]

    def detach(self) -> None:
        self.reset_progress()
        if self.connection is not None:
            self.connection.cursorclass = self.cursorclass
            del self.connection._mycli_background_runner  # type: ignore[attr-defined]
            self.connection = None
        self.monitor.submit(self._close_control).result()

    def _close_control(self) -> None:
        if self.control is not None:
            try:
                self.control.close()
            except Exception:
                logger.debug('Closing query monitor failed', exc_info=True)
            self.control = None

    def close(self) -> None:
        self.detach()
        self.worker.shutdown(wait=True)
        self.monitor.shutdown(wait=True)

    def _control(self, connection_id: int, done: Event, cancel: bool = False) -> str:
        try:
            if done.is_set():
                return QueryState.UNKNOWN.value
            if self.control is None:
                assert self.connect_control is not None
                self.control = self.connect_control()
            if done.is_set():
                return QueryState.UNKNOWN.value
            with self.control.cursor() as cursor:
                if cancel:
                    cursor.execute(f'KILL QUERY {int(connection_id)}')
                    return 'Cancelling'
                cursor.execute('SHOW PROCESSLIST')
                try:
                    header = [x[0] for x in cursor.description]
                    state_pos = header.index('State')
                except (ValueError, TypeError):
                    state_pos = 6
                for row in cursor.fetchall():
                    if row[0] == connection_id:
                        if row[state_pos]:
                            self.previous_state = str(row[state_pos])
                        return self.previous_state
        except Exception:
            logger.debug('Query monitoring failed', exc_info=True)
            self._close_control()
        return QueryState.UNKNOWN.value

    def _display(self, elapsed: float, state: str) -> None:
        state = state.strip().lower()
        message = f'{elapsed:04.1f}s | {state}'
        try:
            columns = os.get_terminal_size(sys.stderr.fileno()).columns
        except (OSError, ValueError):
            columns = DEFAULT_WIDTH
        width = max(1, (columns if columns > 0 else DEFAULT_WIDTH) - 1)
        while get_cwidth(message) > width:
            message = message[:-1]
        sys.stderr.write(TTY_ERASE_LINE + message)
        sys.stderr.flush()
        self.visible = True

    def _clear(self) -> None:
        if self.visible:
            try:
                sys.stderr.write(TTY_ERASE_LINE)
                sys.stderr.flush()
            except (OSError, ValueError):
                logger.debug('Clearing query status failed', exc_info=True)
            finally:
                self.visible = False

    def _handoff_to_rendering(self, elapsed: float) -> None:
        self._display_if_due(elapsed, self._local_state().value)

    def _local_state(self) -> QueryState:
        if self._render_state == QueryState.RENDERING and self.connection is not None and issubclass(self.cursorclass, SSCursor):
            return QueryState.STREAMING
        return self._render_state

    def _display_if_due(self, elapsed: float, state: str) -> None:
        """Share one update deadline across fetches, handoffs, and rendering ticks."""
        with self._display_lock:
            now = (self.started or 0.0) + elapsed
            if now >= self._next_update:
                self._display(elapsed, state)
                self._next_update = now + self.interval

    def call(self, operation: Callable[[], T], *, new_statement: bool = True) -> T:
        if get_ident() == self.worker_id:
            return operation()
        with self._display_lock:
            self._busy = True
            if new_statement or self.started is None:
                self.started = monotonic()
                self._next_update = self.started + self.interval
                self._state_requested = False
                self._output_started = False
                self.previous_state = QueryState.INITIAL.value
        interrupts = 0

        def interrupt(_signum: int, _frame: FrameType | None) -> None:
            nonlocal interrupts
            interrupts += 1

        def interrupted() -> bool:
            nonlocal interrupts
            if interrupts:
                interrupts -= 1
                return True
            return False

        # Defer SIGINT so it cannot strand work between submission and waiting.
        on_main_thread = get_ident() == main_thread().ident
        previous = signal.signal(signal.SIGINT, interrupt) if on_main_thread else None
        try:
            return self._call(operation, interrupted)
        finally:
            if on_main_thread:
                signal.signal(signal.SIGINT, previous)
            with self._display_lock:
                self._busy = False

    def _call(self, operation: Callable[[], T], interrupted: Callable[[], bool]) -> T:
        done = Event()

        def execute() -> T:
            self.worker_id = get_ident()
            try:
                return operation()
            finally:
                done.set()

        connection = self.connection
        connection_id = connection.thread_id() if connection is not None else 0
        future = self.worker.submit(execute)
        started = self.started if self.started is not None else monotonic()
        state = self.previous_state
        polling: Future[str] | None = None
        cancellation: Future[str] | None = None
        cancelled = disconnected = False
        successful = False
        try:
            while True:
                try:
                    if interrupted():
                        raise KeyboardInterrupt
                    if done.wait(0.05):
                        # No control operation may outlive this query and kill its successor.
                        if polling is not None:
                            polling.result()
                        if cancellation is not None:
                            cancellation.result()
                        # SIGINT may arrive while waiting for completion or monitoring.
                        cancelled = interrupted() or cancelled
                        break
                    now = monotonic()
                    display_enabled = self.show_state and not self._suppressed and not self._output_started
                    if display_enabled:
                        if polling is not None and polling.done():
                            state = polling.result()
                            polling = None
                        if not self._state_requested:
                            polling = self.monitor.submit(self._control, connection_id, done)
                            self._state_requested = True
                    if display_enabled and now >= self._next_update:
                        if polling is None:
                            polling = self.monitor.submit(self._control, connection_id, done)
                        self._display_if_due(now - started, 'Cancelling' if cancelled else state)
                except KeyboardInterrupt:
                    if not cancelled:
                        cancelled = True
                        cancellation = self.monitor.submit(self._control, connection_id, done, True)
                    else:
                        disconnected = True
                        sock = getattr(connection, '_sock', None)
                        if sock is not None:
                            try:
                                sock.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
            if cancelled:
                if connection is not None:
                    disconnected = disconnected or not connection.open
                    if disconnected and connection.open:
                        connection.close()
                raise QueryCancelled(disconnected)
            result = future.result()
            successful = True
            return result
        finally:
            with self._display_lock:
                if successful and self.visible and self.show_state and not self._suppressed and not self._output_started:
                    self._handoff_to_rendering(monotonic() - started)
                else:
                    self._clear()

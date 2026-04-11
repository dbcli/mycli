# type: ignore

from collections.abc import Iterator
import multiprocessing
import os
import platform
import signal
import time
from types import SimpleNamespace
from typing import Any, Callable, Literal, cast

import pymysql
import pytest

from mycli import main
from mycli.constants import (
    DEFAULT_CHARSET,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USER,
    TEST_DATABASE,
)
from mycli.main import special
from mycli.packages.sqlresult import SQLResult

DATABASE = TEST_DATABASE
PASSWORD = os.getenv("PYTEST_PASSWORD")
USER = os.getenv("PYTEST_USER", DEFAULT_USER)
HOST = os.getenv("PYTEST_HOST", DEFAULT_HOST)
PORT = int(os.getenv("PYTEST_PORT", DEFAULT_PORT))
CHARACTER_SET = os.getenv("PYTEST_CHARSET", DEFAULT_CHARSET)
SSH_USER = os.getenv("PYTEST_SSH_USER", None)
SSH_HOST = os.getenv("PYTEST_SSH_HOST", None)
SSH_PORT = int(os.getenv("PYTEST_SSH_PORT", "22"))
TEMPFILE_PREFIX = 'mycli_test_suite_'


class DummyLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.error_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.warning_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self.debug_calls.append((args, kwargs))

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.error_calls.append((args, kwargs))

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self.warning_calls.append((args, kwargs))


class DummyFormatter:
    def __init__(self, format_name: str = 'ascii') -> None:
        self.format_name = format_name
        self.query = ''
        self.supported_formats = ['ascii', 'csv', 'tsv', 'vertical']
        self._output_formats = {
            'ascii': SimpleNamespace(formatter_args={'missing_value': main.DEFAULT_MISSING_VALUE}),
            'csv': SimpleNamespace(formatter_args={'missing_value': main.DEFAULT_MISSING_VALUE}),
            'tsv': SimpleNamespace(formatter_args={'missing_value': main.DEFAULT_MISSING_VALUE}),
            'vertical': SimpleNamespace(formatter_args={'missing_value': main.DEFAULT_MISSING_VALUE}),
        }
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def format_output(self, rows: Any, header: Any, format_name: str | None = None, **kwargs: Any) -> list[str] | str:
        self.calls.append(((rows, header, format_name), kwargs))
        if format_name == 'vertical':
            return ['vertical output']
        return ['plain output']


class ReusableLock:
    def __init__(self, on_enter: Callable[[], Any] | None = None) -> None:
        self.on_enter = on_enter

    def __enter__(self) -> 'ReusableLock':
        if self.on_enter is not None:
            self.on_enter()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return False


class FakeCursorBase:
    def __init__(
        self,
        rows: list[tuple[Any, ...]] | None = None,
        rowcount: int = 0,
        description: list[tuple[Any, ...]] | None = None,
        warning_count: int = 0,
    ) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.description = description or []
        self.warning_count = warning_count

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        return iter(self._rows)


class RecordingSQLExecute:
    calls: list[dict[str, Any]] = []
    side_effects: list[Any] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).calls.append(dict(kwargs))
        if type(self).side_effects:
            effect = type(self).side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            if callable(effect):
                effect(kwargs)
        self.kwargs = kwargs
        self.dbname = kwargs.get('database')
        self.user = kwargs.get('user')
        self.conn = kwargs.get('conn')
        self.sandbox_mode = False


def make_bare_mycli() -> Any:
    cli = object.__new__(main.MyCli)
    cli.logger = cast(Any, DummyLogger())
    cli.main_formatter = DummyFormatter()
    cli.redirect_formatter = DummyFormatter()
    cli.helpers_style = 'helpers-style'
    cli.helpers_warnings_style = 'helpers-warnings-style'
    cli.ptoolkit_style = cast(Any, 'pt-style')
    cli.syntax_style = 'native'
    cli.cli_style = {}
    cli.null_string = '<null>'
    cli.numeric_alignment = 'right'
    cli.binary_display = None
    cli.show_warnings = False
    cli.query_history = []
    cli.toolbar_error_message = None
    cli.prompt_session = None
    cli.last_prompt_message = main.ANSI('')
    cli.last_custom_toolbar_message = main.ANSI('')
    cli.prompt_lines = 0
    cli.prompt_format = main.MyCli.default_prompt
    cli.multiline_continuation_char = '>'
    cli.toolbar_format = 'default'
    cli.destructive_warning = False
    cli.destructive_keywords = ['drop']
    cli.keepalive_ticks = None
    cli._keepalive_counter = 0
    cli.less_chatty = True
    cli.smart_completion = False
    cli.key_bindings = 'emacs'
    cli.auto_vertical_output = False
    cli.wider_completion_menu = False
    cli.explicit_pager = False
    cli._completer_lock = cast(Any, ReusableLock())
    cli.terminal_tab_title_format = ''
    cli.terminal_window_title_format = ''
    cli.multiplex_window_title_format = ''
    cli.multiplex_pane_title_format = ''
    cli.dsn_alias = None
    cli.login_path = None
    cli.login_path_as_host = False
    cli.post_redirect_command = None
    cli.logfile = None
    cli.emacs_ttimeoutlen = 1.0
    cli.vi_ttimeoutlen = 1.0
    cli.beep_after_seconds = 0.0
    cli.config = {'history_file': '~/.mycli-history-testing'}
    cli.output = lambda *args, **kwargs: None  # type: ignore[assignment]
    cli.echo = lambda *args, **kwargs: None  # type: ignore[assignment]
    cli.log_query = lambda *args, **kwargs: None  # type: ignore[assignment]
    cli.log_output = lambda *args, **kwargs: None  # type: ignore[assignment]
    cli.configure_pager = lambda: None  # type: ignore[assignment]
    cli.refresh_completions = lambda reset=False: [SQLResult(status='refresh')]  # type: ignore[assignment]
    cli.reconnect = lambda database='': False  # type: ignore[assignment]
    return cli


def make_dummy_mycli_class(
    *,
    config: dict[str, Any] | None = None,
    my_cnf: dict[str, Any] | None = None,
    config_without_package_defaults: dict[str, Any] | None = None,
) -> Any:
    class DummyMyCli:
        last_instance: Any = None

        def __init__(self, **kwargs: Any) -> None:
            type(self).last_instance = self
            self.init_kwargs = dict(kwargs)
            self.config = config or {'main': {}, 'alias_dsn': {}}
            self.my_cnf = my_cnf or {'client': {}, 'mysqld': {}}
            self.config_without_package_defaults = config_without_package_defaults or {}
            self.default_keepalive_ticks = 5
            self.ssl_mode = None
            self.logger = DummyLogger()
            self.main_formatter = SimpleNamespace(format_name=None)
            self.destructive_warning = False
            self.destructive_keywords = ['drop']
            self.dsn_alias = None
            self.connect_calls: list[dict[str, Any]] = []
            self.run_query_calls: list[tuple[str, Any, bool]] = []
            self.run_cli_called = False
            self.close_called = False

        def connect(self, **kwargs: Any) -> None:
            self.connect_calls.append(dict(kwargs))

        def run_query(self, query: str, checkpoint: Any = None, new_line: bool = True) -> None:
            self.run_query_calls.append((query, checkpoint, new_line))

        def run_cli(self) -> None:
            self.run_cli_called = True

        def close(self) -> None:
            self.close_called = True

    return DummyMyCli


def call_click_entrypoint_direct(cli_args: main.CliArgs) -> None:
    assert main.click_entrypoint.callback is not None
    cast(Any, main.click_entrypoint.callback).__wrapped__(cli_args)


def db_connection(dbname=None):
    conn = pymysql.connect(user=USER, host=HOST, port=PORT, database=dbname, password=PASSWORD, charset=CHARACTER_SET, local_infile=False)
    conn.autocommit = True
    return conn


try:
    db_connection()
    CAN_CONNECT_TO_DB = True
except Exception:
    CAN_CONNECT_TO_DB = False

dbtest = pytest.mark.skipif(not CAN_CONNECT_TO_DB, reason=f"Need a mysql instance at {DEFAULT_HOST} accessible by user '{DEFAULT_USER}'")


def create_db(dbname):
    with db_connection().cursor() as cur:
        try:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DATABASE}")
            cur.execute(f"CREATE DATABASE {TEST_DATABASE}")
        except Exception:
            pass


def run(executor, sql, rows_as_list=True):
    """Return string output for the sql to be run."""
    results = []

    for result in executor.run(sql):
        rows = list(result.rows) if (rows_as_list and result.rows) else result.rows
        results.append({
            "preamble": result.preamble,
            "header": result.header,
            "rows": rows,
            "postamble": result.postamble,
            "status": result.status,
            "status_plain": result.status_plain,
        })

    return results


def set_expanded_output(is_expanded):
    """Pass-through for the tests."""
    return special.set_expanded_output(is_expanded)


def is_expanded_output():
    """Pass-through for the tests."""
    return special.is_expanded_output()


def send_ctrl_c_to_pid(pid, wait_seconds):
    """Sends a Ctrl-C like signal to the given `pid` after `wait_seconds`
    seconds."""
    time.sleep(wait_seconds)
    system_name = platform.system()
    if system_name == "Windows":
        os.kill(pid, signal.CTRL_C_EVENT)
    else:
        os.kill(pid, signal.SIGINT)


def send_ctrl_c(wait_seconds):
    """Create a process that sends a Ctrl-C like signal to the current process
    after `wait_seconds` seconds.

    Returns the `multiprocessing.Process` created.

    """
    ctrl_c_process = multiprocessing.Process(target=send_ctrl_c_to_pid, args=(os.getpid(), wait_seconds))
    ctrl_c_process.start()
    return ctrl_c_process

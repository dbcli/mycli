"""
These generated regression tests against main.py may be more brittle than
the primary tests in test_main.py.

In addition, the tests in this file may enforce contracts that need not be
kept if main.py is refactored.

Therefore authors should be free about

 * migrating individual tests if content moves out of main.py
 * migrating individual tests to test_main.py after assessment of quality
 * removing and rewriting these tests if contracts change
"""

from __future__ import annotations

import builtins
from collections.abc import Generator, Iterator
import importlib.util
from io import StringIO
import itertools
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import click
from click.testing import CliRunner
from configobj import ConfigObj
import pymysql
import pytest

from mycli import main
import mycli.key_bindings
from mycli.packages.sqlresult import SQLResult
from test.utils import (  # type: ignore[attr-defined]
    DummyFormatter,
    DummyLogger,
    call_click_entrypoint_direct,
    make_bare_mycli,
    make_dummy_mycli_class,
)


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


class FakeConnection:
    def __init__(self, ping_exc: Exception | None = None) -> None:
        self.ping_exc = ping_exc
        self.ping_calls: list[bool] = []

    def ping(self, reconnect: bool = False) -> None:
        self.ping_calls.append(reconnect)
        if self.ping_exc is not None:
            raise self.ping_exc


class BoolSection(dict[str, Any]):
    def as_bool(self, key: str) -> bool:
        return str(self[key]).lower() == 'true'


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


class ToggleBool:
    def __init__(self, values: list[bool]) -> None:
        self.values = values

    def __bool__(self) -> bool:
        if self.values:
            return self.values.pop(0)
        return False


class IntRaises:
    def __bool__(self) -> bool:
        return True

    def __int__(self) -> int:
        raise ValueError('bad int')


def load_main_variant(monkeypatch: pytest.MonkeyPatch, *, fail_pwd: bool = False) -> ModuleType:
    import builtins

    original_import = builtins.__import__

    def fake_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:  # noqa: A002
        if fail_pwd and name == 'pwd':
            raise ImportError('no pwd')
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    module_name = f'mycli_main_variant_{int(fail_pwd)}'
    spec = importlib.util.spec_from_file_location(module_name, Path(main.__file__))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_import_fallbacks_for_pwd(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_main_variant(monkeypatch, fail_pwd=True)

    assert module.Query('sql', True, False).query == 'sql'


def test_register_special_commands_registers_expected_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    registered: list[tuple[Any, ...]] = []
    monkeypatch.setattr(main.special, 'register_special_command', lambda *args, **kwargs: registered.append(args))
    main.MyCli.register_special_commands(cli)
    names = [args[1] for args in registered]
    assert names == [
        'use',
        'connect',
        'rehash',
        'tableformat',
        'redirectformat',
        'nowarnings',
        'warnings',
        'source',
        'prompt',
    ]


def test_mycli_init_covers_config_warning_audit_log_and_login_path_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class TypedSection(dict[str, Any]):
        def as_bool(self, key: str) -> bool:
            return str(self[key]).lower() == 'true'

        def as_float(self, key: str) -> float:
            return float(self[key])

        def as_int(self, key: str) -> int:
            return int(self[key])

    class TypedConfig(dict[str, Any]):
        def __init__(self) -> None:
            super().__init__({
                'main': TypedSection({
                    'multi_line': 'false',
                    'key_bindings': 'emacs',
                    'timing': 'false',
                    'show_favorite_query': 'false',
                    'beep_after_seconds': '0',
                    'table_format': 'ascii',
                    'redirect_format': 'csv',
                    'syntax_style': 'native',
                    'less_chatty': 'true',
                    'wider_completion_menu': 'false',
                    'destructive_warning': 'false',
                    'login_path_as_host': 'false',
                    'post_redirect_command': '',
                    'null_string': '',
                    'numeric_alignment': 'right',
                    'binary_display': '',
                    'ssl_mode': 'bogus',
                    'auto_vertical_output': 'false',
                    'show_warnings': 'false',
                    'audit_log': '/tmp/audit.log',
                    'smart_completion': 'false',
                    'min_completion_trigger': '2',
                    'prompt': '',
                    'prompt_continuation': '>',
                    'toolbar': 'default',
                    'terminal_tab_title': '',
                    'terminal_window_title': '',
                    'multiplex_window_title': '',
                    'multiplex_pane_title': '',
                }),
                'connection': TypedSection({'default_keepalive_ticks': '5', 'default_ssl_mode': None}),
                'keys': TypedSection({'emacs_ttimeoutlen': '1.0', 'vi_ttimeoutlen': '1.0'}),
                'colors': {},
                'search': TypedSection({'highlight_preview': 'false'}),
                'llm': TypedSection({'prompt_field_truncate': '12', 'prompt_section_truncate': '34'}),
            })
            self.filename = '/tmp/custom.rc'

    read_calls: list[tuple[bool, bool]] = []

    def fake_read_config_files(
        files: Any, ignore_package_defaults: bool = False, ignore_user_options: bool = False, **kwargs: Any
    ) -> TypedConfig:
        read_calls.append((ignore_package_defaults, ignore_user_options))
        return TypedConfig()

    write_default_calls: list[str] = []
    secho_calls: list[str] = []
    printed: list[str] = []
    monkeypatch.setattr(main, 'read_config_files', fake_read_config_files)
    monkeypatch.setattr(main.special, 'set_timing_enabled', lambda enabled: None)
    monkeypatch.setattr(main.special, 'set_show_favorite_query', lambda enabled: None)
    monkeypatch.setattr(main, 'TabularOutputFormatter', lambda format_name: DummyFormatter(format_name))
    monkeypatch.setattr(main.sql_format, 'register_new_formatter', lambda formatter: None)
    monkeypatch.setattr(main, 'style_factory_ptoolkit', lambda *args, **kwargs: 'style')
    monkeypatch.setattr(main, 'style_factory_helpers', lambda *args, **kwargs: 'helpers')
    monkeypatch.setattr(main.FavoriteQueries, 'from_config', classmethod(lambda cls, config: object()))
    monkeypatch.setattr(main, 'CompletionRefresher', lambda: 'refresher')
    monkeypatch.setattr(main, 'SQLCompleter', lambda *args, **kwargs: 'completer')
    monkeypatch.setattr(main, 'write_default_config', lambda path: write_default_calls.append(path))
    monkeypatch.setattr(main, 'get_mylogin_cnf_path', lambda: '/tmp/mylogin.cnf')
    monkeypatch.setattr(main, 'open_mylogin_cnf', lambda path: None)
    monkeypatch.setattr(main.MyCli, 'register_special_commands', lambda self: None)
    monkeypatch.setattr(main.MyCli, 'initialize_logging', lambda self: None)
    monkeypatch.setattr(main.MyCli, 'read_my_cnf', lambda self, cnf, keys: {'prompt': None})
    monkeypatch.setattr(main.os.path, 'exists', lambda path: False)
    monkeypatch.setattr(click, 'secho', lambda message, **kwargs: secho_calls.append(str(message)))
    monkeypatch.setattr(builtins, 'print', lambda *args, **kwargs: printed.append(' '.join(str(x) for x in args)))

    def fake_open(path: Any, mode: str = 'r', *args: Any, **kwargs: Any) -> Any:
        raise OSError('open failed')

    monkeypatch.setattr(builtins, 'open', fake_open)
    mycli = main.MyCli(myclirc='/tmp/custom.rc')
    assert mycli.llm_prompt_field_truncate == 12
    assert mycli.llm_prompt_section_truncate == 34
    assert mycli.ssl_mode is None
    assert mycli.logfile is False
    assert any('Invalid config option provided for ssl_mode' in msg for msg in secho_calls)
    assert any('Unable to open the audit log file' in msg for msg in secho_calls)
    assert printed == ['Error: Unable to read login path file.']
    assert write_default_calls == ['/tmp/custom.rc']
    assert read_calls == [(False, False), (True, False), (False, True), (False, False)]


def test_mycli_init_defaults_file_valid_ssl_and_mylogin_append(monkeypatch: pytest.MonkeyPatch) -> None:
    class TypedSection(dict[str, Any]):
        def as_bool(self, key: str) -> bool:
            return str(self[key]).lower() == 'true'

        def as_float(self, key: str) -> float:
            return float(self[key])

        def as_int(self, key: str) -> int:
            return int(self[key])

    class TypedConfig(dict[str, Any]):
        def __init__(self) -> None:
            super().__init__({
                'main': TypedSection({
                    'multi_line': 'false',
                    'key_bindings': 'emacs',
                    'timing': 'false',
                    'show_favorite_query': 'false',
                    'beep_after_seconds': '0',
                    'table_format': 'ascii',
                    'redirect_format': 'csv',
                    'syntax_style': 'native',
                    'less_chatty': 'true',
                    'wider_completion_menu': 'false',
                    'destructive_warning': 'false',
                    'login_path_as_host': 'false',
                    'post_redirect_command': '',
                    'null_string': '',
                    'numeric_alignment': 'right',
                    'binary_display': '',
                    'ssl_mode': 'auto',
                    'auto_vertical_output': 'false',
                    'show_warnings': 'false',
                    'smart_completion': 'false',
                    'min_completion_trigger': '1',
                    'prompt': '',
                    'prompt_continuation': '>',
                    'toolbar': 'default',
                    'terminal_tab_title': '',
                    'terminal_window_title': '',
                    'multiplex_window_title': '',
                    'multiplex_pane_title': '',
                }),
                'connection': TypedSection({'default_keepalive_ticks': '1', 'default_ssl_mode': None}),
                'keys': TypedSection({'emacs_ttimeoutlen': '1.0', 'vi_ttimeoutlen': '1.0'}),
                'colors': {},
                'search': TypedSection({'highlight_preview': 'false'}),
            })
            self.filename = '/tmp/custom.rc'

    mylogin_cnf = StringIO('[client]\nuser = alice\n')
    monkeypatch.setattr(main, 'read_config_files', lambda *args, **kwargs: TypedConfig())
    monkeypatch.setattr(main.special, 'set_timing_enabled', lambda enabled: None)
    monkeypatch.setattr(main.special, 'set_show_favorite_query', lambda enabled: None)
    monkeypatch.setattr(main, 'TabularOutputFormatter', lambda format_name: DummyFormatter(format_name))
    monkeypatch.setattr(main.sql_format, 'register_new_formatter', lambda formatter: None)
    monkeypatch.setattr(main, 'style_factory_ptoolkit', lambda *args, **kwargs: 'style')
    monkeypatch.setattr(main, 'style_factory_helpers', lambda *args, **kwargs: 'helpers')
    monkeypatch.setattr(main.FavoriteQueries, 'from_config', classmethod(lambda cls, config: object()))
    monkeypatch.setattr(main, 'CompletionRefresher', lambda: 'refresher')
    monkeypatch.setattr(main, 'SQLCompleter', lambda *args, **kwargs: 'completer')
    monkeypatch.setattr(main.MyCli, 'register_special_commands', lambda self: None)
    monkeypatch.setattr(main.MyCli, 'initialize_logging', lambda self: None)
    monkeypatch.setattr(main.MyCli, 'read_my_cnf', lambda self, cnf, keys: {'prompt': None})
    monkeypatch.setattr(main, 'get_mylogin_cnf_path', lambda: '/tmp/mylogin.cnf')
    monkeypatch.setattr(main, 'open_mylogin_cnf', lambda path: mylogin_cnf)
    monkeypatch.setattr(main.os.path, 'exists', lambda path: True)
    monkeypatch.setattr(click, 'secho', lambda *args, **kwargs: None)

    mycli = main.MyCli(defaults_file='/tmp/defaults.cnf', myclirc='/tmp/custom.rc')
    assert mycli.cnf_files[0] == '/tmp/defaults.cnf'
    assert mycli.cnf_files[-1] is mylogin_cnf
    assert mycli.ssl_mode == 'auto'
    assert mycli.llm_prompt_field_truncate == 0
    assert mycli.llm_prompt_section_truncate == 0


def test_int_or_string_click_param_type_accepts_and_rejects_values() -> None:
    param_type = main.IntOrStringClickParamType()

    assert param_type.convert(1, None, None) == 1
    assert param_type.convert('pw', None, None) == 'pw'
    assert param_type.convert(None, None, None) is None
    with pytest.raises(click.BadParameter):
        param_type.convert(1.5, None, None)


def test_change_format_methods_cover_success_and_value_error() -> None:
    cli = make_bare_mycli()

    result = next(main.MyCli.change_table_format(cli, 'ascii'))
    assert result.status == 'Changed table format to ascii'

    cli.main_formatter = SimpleNamespace(
        supported_formats=['ascii', 'csv'],
        __setattr__=object.__setattr__,
    )

    class BadFormatter:
        supported_formats = ['ascii', 'csv']

        @property
        def format_name(self) -> str:
            return 'ascii'

        @format_name.setter
        def format_name(self, value: str) -> None:
            raise ValueError()

    cli.main_formatter = BadFormatter()
    result = next(main.MyCli.change_table_format(cli, 'bad'))
    assert 'Allowed formats' in str(result.status)

    cli.redirect_formatter = BadFormatter()
    result = next(main.MyCli.change_redirect_format(cli, 'bad'))
    assert 'Redirect format bad not recognized' in str(result.status)

    cli.redirect_formatter = DummyFormatter()
    result = next(main.MyCli.change_redirect_format(cli, 'csv'))
    assert result.status == 'Changed redirect format to csv'


def test_manual_reconnect_and_show_warnings_toggles() -> None:
    cli = make_bare_mycli()
    cli.reconnect = lambda database='': False  # type: ignore[assignment]
    assert next(main.MyCli.manual_reconnect(cli)).status == 'Not connected'

    cli.reconnect = lambda database='': True  # type: ignore[assignment]
    empty = next(main.MyCli.manual_reconnect(cli))
    assert empty.status is None

    def fake_change_db(arg: str) -> Generator[SQLResult, None, None]:
        yield SQLResult(status=f'db:{arg}')

    cli.change_db = fake_change_db  # type: ignore[assignment]
    changed = next(main.MyCli.manual_reconnect(cli, 'prod'))
    assert changed.status == 'db:prod'

    assert next(main.MyCli.enable_show_warnings(cli)).status == 'Show warnings enabled.'
    assert cli.show_warnings is True
    assert next(main.MyCli.disable_show_warnings(cli)).status == 'Show warnings disabled.'
    assert cli.show_warnings is False


def test_change_db_handles_empty_same_new_and_backticks(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    secho_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(click, 'secho', lambda *args, **kwargs: secho_calls.append((args, kwargs)))
    cli.sqlexecute = object.__new__(main.SQLExecute)
    cli.sqlexecute.dbname = 'db1'
    cli.sqlexecute.user = 'user1'
    changed_to: list[str] = []
    cli.sqlexecute.change_db = lambda arg: changed_to.append(arg)  # type: ignore[assignment]
    titles_called = {'count': 0}
    monkeypatch.setattr(
        main,
        'set_all_external_titles',
        lambda mycli: titles_called.__setitem__('count', titles_called['count'] + 1),
    )

    assert list(main.MyCli.change_db(cli, '')) == []
    assert secho_calls[0][0][0] == 'No database selected'

    same = next(main.MyCli.change_db(cli, 'db1'))
    assert 'already connected' in str(same.status)

    cli.sqlexecute.dbname = 'db2'
    new = next(main.MyCli.change_db(cli, '`db``name`'))
    assert changed_to == ['db`name']
    assert 'now connected' in str(new.status)
    assert titles_called['count'] == 2


def test_execute_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()

    class FakeSQLExecute:
        def run(self, query: str) -> list[SQLResult]:
            return [SQLResult(status=query)]

    monkeypatch.setattr(main, 'SQLExecute', FakeSQLExecute)
    cli.sqlexecute = cast(Any, FakeSQLExecute())
    cli.destructive_warning = True
    cli.destructive_keywords = ['drop']

    assert list(main.MyCli.execute_from_file(cli, ''))[0].status == 'Missing required argument: filename.'

    missing = list(main.MyCli.execute_from_file(cli, str(tmp_path / 'missing.sql')))
    assert 'No such file' in str(missing[0].status)

    sql_file = tmp_path / 'query.sql'
    sql_file.write_text('drop table test;', encoding='utf-8')
    monkeypatch.setattr(main, 'confirm_destructive_query', lambda keywords, query: False)
    stopped = list(main.MyCli.execute_from_file(cli, str(sql_file)))
    assert stopped[0].status == 'Wise choice. Command execution stopped.'

    cli.destructive_warning = False
    ran = list(main.MyCli.execute_from_file(cli, str(sql_file)))
    assert ran[0].status == 'drop table test;'


def test_initialize_logging_covers_none_bad_path_and_file_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(message)  # type: ignore[assignment]
    cli.config = {'main': {'log_file': str(tmp_path / 'mycli.log'), 'log_level': 'NONE'}}
    monkeypatch.setattr(main, 'dir_path_exists', lambda path: True)
    main.MyCli.initialize_logging(cli)

    cli.config = {'main': {'log_file': str(tmp_path / 'missing' / 'mycli.log'), 'log_level': 'INFO'}}
    monkeypatch.setattr(main, 'dir_path_exists', lambda path: False)
    main.MyCli.initialize_logging(cli)
    assert echo_calls[-1].startswith('Error: Unable to open the log file')

    cli.config = {'main': {'log_file': str(tmp_path / 'mycli.log'), 'log_level': 'INFO'}}
    monkeypatch.setattr(main, 'dir_path_exists', lambda path: True)
    main.MyCli.initialize_logging(cli)


def test_read_my_cnf_and_merge_ssl_with_cnf() -> None:
    cli = make_bare_mycli()
    cli.login_path = 'prod'
    cli.defaults_suffix = '_suffix'
    cnf = ConfigObj()
    cnf['client'] = {'prompt': '"mysql>"', 'ssl-ca': '/tmp/ca.pem'}
    cnf['mysqld'] = {'socket': "'/tmp/mysql.sock'", 'port': '3307'}
    cnf['prod'] = {'user': '`alice`'}
    cnf['client_suffix'] = {'prompt': "'alt>'"}
    values = main.MyCli.read_my_cnf(cli, cnf, ['prompt', 'socket', 'port', 'user', 'ssl-ca'])
    assert values['prompt'] == 'alt>'
    assert values['default_socket'] == '/tmp/mysql.sock'
    assert values['default_port'] == '3307'
    assert values['user'] == '`alice`'

    merged = main.MyCli.merge_ssl_with_cnf(cli, {'mode': 'on'}, {'ssl-ca': '/tmp/ca.pem', 'ssl-verify-server-cert': 'true', 'other': 'x'})
    assert merged['mode'] == 'on'
    assert merged['ca'] == '/tmp/ca.pem'
    assert merged['check_hostname'] is True


def test_connect_covers_defaults_keyring_prompt_retries_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.config_without_package_defaults = {'connection': {'default_ssl_ca_path': '/ssl/ca-path', 'default_local_infile': 'true'}}
    cli.config = {'connection': {'default_ssl_ca_path': '/ssl/ca-path'}, 'main': {'default_character_set': 'utf8mb4'}}
    echo_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    cli.echo = lambda *args, **kwargs: echo_calls.append((args, kwargs))  # type: ignore[assignment]
    logger = DummyLogger()
    cli.logger = cast(Any, logger)
    monkeypatch.setattr(main, 'WIN', True)
    monkeypatch.setattr(main, 'SQLExecute', RecordingSQLExecute)
    RecordingSQLExecute.calls = []
    RecordingSQLExecute.side_effects = []
    monkeypatch.setattr(main, 'guess_socket_location', lambda: '/tmp/mysql.sock')
    monkeypatch.setattr(main, 'str_to_bool', lambda value: str(value).lower() == 'true')
    monkeypatch.setattr(main.keyring, 'get_password', lambda *args: 'stored-pw')
    set_password_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(main.keyring, 'set_password', lambda domain, ident, password: set_password_calls.append((domain, ident, password)))
    monkeypatch.setenv('USER', 'env-user')

    main.MyCli.connect(cli, host='', port='', ssl={'mode': 'on'}, use_keyring=True)
    assert RecordingSQLExecute.calls[-1]['socket'] == '/tmp/mysql.sock'
    assert RecordingSQLExecute.calls[-1]['character_set'] == 'utf8mb4'
    assert RecordingSQLExecute.calls[-1]['ssl']['capath'] == '/ssl/ca-path'
    assert RecordingSQLExecute.calls[-1]['password'] == 'stored-pw'

    prompt_calls: list[str] = []

    def fake_prompt(message: str, **kwargs: Any) -> str:
        prompt_calls.append(message)
        return 'entered-pw'

    monkeypatch.setattr(click, 'prompt', fake_prompt)
    RecordingSQLExecute.calls = []
    main.MyCli.connect(
        cli, user='alice', passwd=main.EMPTY_PASSWORD_FLAG_SENTINEL, host='db', port=3307, ssl={'mode': 'on'}, use_keyring=True
    )
    assert prompt_calls == ['Enter password for alice']
    assert set_password_calls[-1][2] == 'entered-pw'

    handshake_error = pymysql.OperationalError(main.HANDSHAKE_ERROR, 'ssl fail')
    RecordingSQLExecute.side_effects = [handshake_error, None]
    RecordingSQLExecute.calls = []
    main.MyCli.connect(cli, host='db', port=3307, ssl={'mode': 'auto'})
    assert RecordingSQLExecute.calls[0]['ssl']['mode'] == 'auto'
    assert RecordingSQLExecute.calls[1]['ssl'] is None

    access_error = pymysql.OperationalError(main.ACCESS_DENIED_ERROR, 'denied')
    RecordingSQLExecute.side_effects = [access_error, None]
    RecordingSQLExecute.calls = []
    monkeypatch.setattr(click, 'prompt', lambda message, **kwargs: 'retry-pw')
    main.MyCli.connect(cli, user='bob', passwd=None, host='db', port=3307)
    assert RecordingSQLExecute.calls[1]['password'] == 'retry-pw'

    server_lost = pymysql.OperationalError(main.CR_SERVER_LOST, 'lost')
    RecordingSQLExecute.side_effects = [server_lost]
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='db', port=3307)
    assert any('Connection to server lost' in str(call[0][0]) for call in echo_calls)

    RecordingSQLExecute.side_effects = []
    with pytest.raises(ValueError):
        main.MyCli.connect(cli, host='db', port='bad-port')


def test_connect_socket_owner_and_tcp_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.config_without_package_defaults = {'connection': {}}
    cli.config = {'connection': {}, 'main': {}}
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(str(message))  # type: ignore[assignment]
    cli.logger = cast(Any, DummyLogger())
    monkeypatch.setattr(main, 'WIN', False)
    monkeypatch.setattr(main, 'getpwuid', lambda uid: SimpleNamespace(pw_name='socket-owner'))
    original_stat = os.stat

    def fake_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if str(path) == '/tmp/mysql.sock':
            return os.stat_result((0, 0, 0, 0, 123, 0, 0, 0, 0, 0))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(main.os, 'stat', fake_stat)
    monkeypatch.setattr(main, 'str_to_bool', lambda value: False)

    class SocketThenTcpSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = [pymysql.OperationalError(2002, 'socket fail'), None]

    monkeypatch.setattr(main, 'SQLExecute', SocketThenTcpSQLExecute)
    main.MyCli.connect(cli, host='', port='', socket='/tmp/mysql.sock', ssl={'mode': 'on'})

    assert 'Connecting to socket /tmp/mysql.sock, owned by user socket-owner' in echo_calls[0]
    assert 'Retrying over TCP/IP' in echo_calls[-1]
    assert len(SocketThenTcpSQLExecute.calls) == 2


def test_connect_additional_error_and_config_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config = {'connection': {'default_ssl_ca_path': '/tmp/ca-path'}, 'main': {}}
    cli.config_without_package_defaults = {'connection': {}}
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.logger = cast(Any, DummyLogger())
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(str(message))  # type: ignore[assignment]
    monkeypatch.setattr(main, 'WIN', False)
    monkeypatch.setattr(main, 'str_to_bool', lambda value: False)

    def fake_read_my_cnf(cnf: Any, keys: list[str]) -> dict[str, Any]:
        return {
            'database': None,
            'user': None,
            'password': None,
            'host': None,
            'port': None,
            'socket': None,
            'default_socket': None,
            'default-character-set': 'latin1',
            'local_infile': None,
            'local-infile': None,
            'loose_local_infile': None,
            'loose-local-infile': None,
            'ssl-ca': None,
            'ssl-cert': None,
            'ssl-key': None,
            'ssl-cipher': None,
            'ssl-verify-server-cert': None,
        }

    cli.read_my_cnf = fake_read_my_cnf  # type: ignore[assignment]

    class SuccessfulSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = []

    monkeypatch.setattr(main, 'SQLExecute', SuccessfulSQLExecute)
    monkeypatch.setattr(main, 'getpwuid', lambda uid: (_ for _ in ()).throw(KeyError()))
    original_stat = os.stat

    def fake_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if str(path) == '/tmp/mysql.sock':
            return os.stat_result((0, 0, 0, 0, 123, 0, 0, 0, 0, 0))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(main.os, 'stat', fake_stat)
    main.MyCli.connect(cli, host='', port='', socket='/tmp/mysql.sock', ssl={'mode': 'on'})
    assert 'owned by user <unknown>' in echo_calls[0]
    assert SuccessfulSQLExecute.calls[-1]['character_set'] == 'latin1'
    assert SuccessfulSQLExecute.calls[-1]['ssl']['capath'] == '/tmp/ca-path'

    with pytest.raises(ValueError):
        main.MyCli.connect(cli, host='db.example', port='not-a-port')

    class UnexpectedSocketErrorSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = [pymysql.OperationalError(9999, 'boom')]

    monkeypatch.setattr(main, 'SQLExecute', UnexpectedSocketErrorSQLExecute)
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='', port='', socket='/tmp/mysql.sock')


def test_connect_show_warnings_ssl_overrides_and_retry_password_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config = {'connection': {'default_character_set': 'utf8mb4'}, 'main': {}}
    cli.config_without_package_defaults = {
        'connection': {
            'default_local_infile': IntRaises(),
            'default_ssl_ca': '/tmp/ca.pem',
            'default_ssl_cert': '/tmp/cert.pem',
            'default_ssl_key': '/tmp/key.pem',
            'default_ssl_cipher': 'AES256',
            'default_ssl_verify_server_cert': 'true',
        }
    }
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.logger = cast(Any, DummyLogger())
    cli.echo = lambda *args, **kwargs: None  # type: ignore[assignment]

    def fake_read_my_cnf(cnf: Any, keys: list[str]) -> dict[str, Any]:
        return {
            'database': None,
            'user': None,
            'password': None,
            'host': None,
            'port': None,
            'socket': None,
            'default_socket': None,
            'default-character-set': None,
            'local_infile': None,
            'local-infile': None,
            'loose_local_infile': None,
            'loose-local-infile': None,
            'ssl-ca': None,
            'ssl-cert': None,
            'ssl-key': None,
            'ssl-cipher': None,
            'ssl-verify-server-cert': None,
        }

    cli.read_my_cnf = fake_read_my_cnf  # type: ignore[assignment]

    def fake_str_to_bool(value: Any) -> bool:
        if isinstance(value, IntRaises):
            raise ValueError('bad bool')
        return str(value).lower() == 'true'

    monkeypatch.setattr(main, 'str_to_bool', fake_str_to_bool)
    monkeypatch.setattr(main, 'SQLExecute', RecordingSQLExecute)
    RecordingSQLExecute.calls = []
    RecordingSQLExecute.side_effects = []
    main.MyCli.connect(cli, host='db', port=3307, local_infile=cast(Any, IntRaises()), show_warnings=True, ssl={'mode': 'on'})
    assert cli.show_warnings is True
    ssl = RecordingSQLExecute.calls[-1]['ssl']
    assert ssl['ca'] == '/tmp/ca.pem'
    assert ssl['cert'] == '/tmp/cert.pem'
    assert ssl['key'] == '/tmp/key.pem'
    assert ssl['cipher'] == 'AES256'
    assert ssl['check_hostname'] is True
    assert RecordingSQLExecute.calls[-1]['character_set'] == 'utf8mb4'

    access_error = pymysql.OperationalError(main.ACCESS_DENIED_ERROR, 'denied')
    RecordingSQLExecute.calls = []
    RecordingSQLExecute.side_effects = [access_error, access_error]
    monkeypatch.setattr(click, 'prompt', lambda *args, **kwargs: None)
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, user='bob', passwd=None, host='db', port=3307)


def test_connect_retries_ssl_password_and_handles_keyring_save_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config = {'connection': {}, 'main': {}}
    cli.config_without_package_defaults = {'connection': {}}
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.logger = cast(Any, DummyLogger())
    cli.echo = lambda *args, **kwargs: None  # type: ignore[assignment]

    def read_my_cnf_all_none(cnf: Any, keys: list[str]) -> dict[str, Any]:
        values = dict.fromkeys(keys)
        values['local_infile'] = None
        values['loose_local_infile'] = None
        values['default_character_set'] = None
        return values

    cli.read_my_cnf = read_my_cnf_all_none  # type: ignore[assignment]
    monkeypatch.setattr(main, 'WIN', False)
    monkeypatch.setattr(main, 'str_to_bool', lambda value: False)

    class HandshakeRetrySQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = [
            pymysql.OperationalError(main.HANDSHAKE_ERROR, 'ssl fail'),
            pymysql.OperationalError(main.HANDSHAKE_ERROR, 'ssl fail'),
        ]

    monkeypatch.setattr(main, 'SQLExecute', HandshakeRetrySQLExecute)
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='db.example', ssl={'mode': 'auto'})
    assert HandshakeRetrySQLExecute.calls[0]['ssl'] == {'mode': 'auto'}
    assert HandshakeRetrySQLExecute.calls[1]['ssl'] is None

    class PasswordRetrySQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = [
            pymysql.OperationalError(main.ACCESS_DENIED_ERROR, 'denied'),
            pymysql.OperationalError(main.ACCESS_DENIED_ERROR, 'denied'),
        ]

    monkeypatch.setattr(main, 'SQLExecute', PasswordRetrySQLExecute)
    monkeypatch.setattr(click, 'prompt', lambda *args, **kwargs: 'new-password')
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='db.example', passwd=None)
    assert PasswordRetrySQLExecute.calls[1]['password'] == 'new-password'

    class KeyringSaveSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = []

    saved_errors: list[str] = []
    monkeypatch.setattr(main, 'SQLExecute', KeyringSaveSQLExecute)
    monkeypatch.setattr(main.keyring, 'get_password', lambda domain, ident: 'old-password')
    monkeypatch.setattr(main.keyring, 'set_password', lambda domain, ident, password: (_ for _ in ()).throw(RuntimeError('no keyring')))
    monkeypatch.setattr(click, 'secho', lambda message, **kwargs: saved_errors.append(str(message)))
    main.MyCli.connect(cli, host='db.example', passwd='new-password', use_keyring=True, reset_keyring=True)
    assert any('Password not saved to the system keyring' in message for message in saved_errors)


def test_connect_covers_default_ssl_ca_path_and_late_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config = {'connection': {'default_ssl_ca_path': '/tmp/ca-path'}, 'main': {}}
    cli.config_without_package_defaults = {'connection': {}}
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.logger = cast(Any, DummyLogger())
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(str(message))  # type: ignore[assignment]
    cli.read_my_cnf = lambda cnf, keys: dict.fromkeys(keys) | {'local_infile': None, 'loose_local_infile': None}
    monkeypatch.setattr(main, 'WIN', False)
    monkeypatch.setattr(main, 'guess_socket_location', lambda: '')
    monkeypatch.setattr(main, 'str_to_bool', lambda value: False)
    monkeypatch.setattr(main.MyCli, 'merge_ssl_with_cnf', lambda self, ssl, cnf: None)

    class CaptureSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = []

    monkeypatch.setattr(main, 'SQLExecute', CaptureSQLExecute)
    main.MyCli.connect(cli, host='', port='', socket='')
    assert CaptureSQLExecute.calls[-1]['ssl'] is None

    class PortValue(ToggleBool):
        def __init__(self) -> None:
            super().__init__([False, False, True])

        def __int__(self) -> int:
            raise ValueError('bad port')

    cli.read_my_cnf = lambda cnf, keys: (
        dict.fromkeys(keys) | {'port': cast(Any, PortValue()), 'local_infile': None, 'loose_local_infile': None}
    )  # noqa: C420
    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='db.example', port='', socket='')
    assert any('Invalid port number' in msg for msg in echo_calls)


def test_format_sqlresult_run_query_reserved_space_and_last_query(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    cli.redirect_formatter = DummyFormatter()
    cli.sqlexecute = cast(Any, SimpleNamespace())
    monkeypatch.setattr(main, 'Cursor', FakeCursorBase)
    description = [('id', 3), ('name', 253)]
    rows = FakeCursorBase(rows=[(1, 'a')], rowcount=1, description=description)
    result = SQLResult(preamble='pre', header=['id', 'name'], rows=cast(Any, rows), postamble='post', status='SELECT 1')
    output = list(main.MyCli.format_sqlresult(cli, result, max_width=3))
    assert output[0] == 'pre'
    assert output[-1] == 'post'
    assert 'vertical output' in output

    redirected = list(main.MyCli.format_sqlresult(cli, SQLResult(header=['id'], rows=[(1,)]), is_redirected=True))
    assert redirected == ['plain output']

    cli.show_warnings = True
    warning_rows = FakeCursorBase(rows=[('Warning', 1, 'msg')], rowcount=1, description=description, warning_count=1)
    main_result = SQLResult(header=['id'], rows=cast(Any, warning_rows), status='select 1')
    warning_result = SQLResult(header=['level'], rows=[('Warning',)])
    cli.sqlexecute.run = cast(Any, lambda query: [main_result] if query == 'select 1' else [warning_result])
    cli.format_sqlresult = lambda *args, **kwargs: iter(['line'])  # type: ignore[assignment]
    outputs: list[str] = []
    monkeypatch.setattr(click, 'echo', lambda line, nl=True: outputs.append(line))
    checkpoint = StringIO()
    main.MyCli.run_query(cli, 'select 1', checkpoint=cast(Any, checkpoint), new_line=False)
    assert outputs == ['line', 'line']
    assert checkpoint.getvalue() == 'select 1\n'

    assert main.MyCli.get_reserved_space(cli) == 8
    assert main.MyCli.get_last_query(cli) is None
    cli.query_history = [main.Query('select 1', True, False)]
    assert main.MyCli.get_last_query(cli) == 'select 1'


def test_reconnect_logging_and_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cli = make_bare_mycli()
    sqlexecute = object.__new__(main.SQLExecute)

    class ThirdPassConnection:
        def __init__(self) -> None:
            self.select_db_calls: list[str] = []

        def ping(self, reconnect: bool = False) -> None:
            raise pymysql.err.Error()

        def select_db(self, dbname: str) -> None:
            self.select_db_calls.append(dbname)

    conn = ThirdPassConnection()
    sqlexecute.conn = cast(Any, conn)
    sqlexecute.dbname = 'prod'
    sqlexecute.connection_id = 10

    def fake_reset_connection_id() -> None:
        return None

    def fake_connect() -> None:
        return None

    sqlexecute.reset_connection_id = fake_reset_connection_id  # type: ignore[assignment]
    sqlexecute.connect = fake_connect  # type: ignore[assignment]
    cli.sqlexecute = cast(Any, sqlexecute)
    echoes: list[str] = []
    cli.echo = lambda message, **kwargs: echoes.append(str(message))  # type: ignore[assignment]
    assert main.MyCli.reconnect(cli) is True
    assert 'Creating new connection...' in echoes
    assert 'Any session state was reset.' in echoes

    def failing_connect() -> None:
        raise pymysql.OperationalError(2000, 'still down')

    sqlexecute.connect = failing_connect  # type: ignore[assignment]
    assert main.MyCli.reconnect(cli) is False
    assert 'still down' in echoes[-1]

    logfile = tmp_path / 'audit.log'
    with logfile.open('w+', encoding='utf-8') as handle:
        cli.logfile = handle
        main.MyCli.log_query(cli, 'select 1')
        main.MyCli.log_output(cli, main.ANSI('\x1b[31mhello\x1b[0m'))
        handle.seek(0)
        contents = handle.read()
    assert 'select 1' in contents
    assert 'hello' in contents

    printed_status: list[Any] = []
    echoed_lines: list[str] = []
    monkeypatch.setattr(main.special, 'is_redirected', lambda: True)
    monkeypatch.setattr(main.special, 'write_tee', lambda text: None)
    monkeypatch.setattr(main.special, 'write_once', lambda text: None)
    monkeypatch.setattr(main.special, 'write_pipe_once', lambda text: None)
    monkeypatch.setattr(main.special, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(main.MyCli, 'get_output_margin', lambda self, status=None: 1)
    monkeypatch.setattr(click, 'secho', lambda line, **kwargs: echoed_lines.append(str(line)))
    monkeypatch.setattr(main, 'print_formatted_text', lambda text, style=None: printed_status.append((text, style)))
    main.MyCli.output(cli, itertools.chain(['row 1']), SQLResult(status='status'))
    assert echoed_lines == []
    assert printed_status


def test_reconnect_first_and_second_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    echoes: list[str] = []
    cli.echo = lambda message, **kwargs: echoes.append(str(message))  # type: ignore[assignment]

    class FirstPassConnection:
        def ping(self, reconnect: bool = False) -> None:
            return None

    sqlexecute = object.__new__(main.SQLExecute)
    sqlexecute.conn = cast(Any, FirstPassConnection())
    sqlexecute.dbname = 'db'
    sqlexecute.connection_id = 1
    cli.sqlexecute = cast(Any, sqlexecute)
    assert main.MyCli.reconnect(cli) is True
    assert 'Already connected.' in echoes

    class SecondPassConnection:
        def __init__(self) -> None:
            self.calls: list[bool] = []
            self.selected: list[str] = []

        def ping(self, reconnect: bool = False) -> None:
            self.calls.append(reconnect)
            if not reconnect:
                raise pymysql.err.Error()

        def select_db(self, dbname: str) -> None:
            self.selected.append(dbname)

    second_conn = SecondPassConnection()
    sqlexecute.conn = cast(Any, second_conn)
    sqlexecute.connection_id = 10

    def fake_reset_connection_id() -> None:
        sqlexecute.connection_id = 11

    sqlexecute.reset_connection_id = fake_reset_connection_id  # type: ignore[assignment]
    assert main.MyCli.reconnect(cli, database='prod') is True
    assert second_conn.calls == [False, True]
    assert second_conn.selected == ['db']
    assert 'Reconnected successfully.' in echoes


def test_format_sqlresult_string_paths_and_close() -> None:
    cli = make_bare_mycli()
    closed: list[bool] = []
    cli.sqlexecute = cast(Any, SimpleNamespace(close=lambda: closed.append(True)))
    main.MyCli.close(cli)
    assert closed == [True]

    class StringFormatter(DummyFormatter):
        def format_output(self, rows: Any, header: Any, format_name: str | None = None, **kwargs: Any) -> str:
            if format_name == 'vertical':
                return 'vertical-a\nvertical-b'
            return 'short\nsecond'

    cli.main_formatter = StringFormatter()
    cli.redirect_formatter = StringFormatter()
    result = SQLResult(header=['id'], rows=[(1,)], status='ok')
    assert list(main.MyCli.format_sqlresult(cli, result)) == ['short', 'second']
    assert list(main.MyCli.format_sqlresult(cli, result, max_width=10)) == ['short', 'second']
    assert list(main.MyCli.format_sqlresult(cli, result, max_width=2)) == ['vertical-a', 'vertical-b']


def test_output_uses_stdout_and_pager_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.explicit_pager = False
    cli.prompt_lines = 1
    cli.prompt_session = None
    cli.log_output = lambda text: None  # type: ignore[assignment]
    monkeypatch.setattr(main.special, 'write_tee', lambda text: None)
    monkeypatch.setattr(main.special, 'write_once', lambda text: None)
    monkeypatch.setattr(main.special, 'write_pipe_once', lambda text: None)
    monkeypatch.setattr(main.special, 'is_redirected', lambda: False)
    pager_enabled = {'value': False}
    monkeypatch.setattr(main.special, 'is_pager_enabled', lambda: pager_enabled['value'])
    monkeypatch.setattr(main.MyCli, 'get_output_margin', lambda self, status=None: 1)
    printed_lines: list[str] = []
    paged_lines: list[str] = []
    monkeypatch.setattr(click, 'secho', lambda line, **kwargs: printed_lines.append(str(line)))
    monkeypatch.setattr(click, 'echo_via_pager', lambda gen: paged_lines.extend(list(gen)))
    monkeypatch.setattr(main, 'print_formatted_text', lambda text, style=None: None)

    main.MyCli.output(cli, itertools.chain(['a' * 81, 'tail']), SQLResult(status='ok'))
    assert printed_lines[:2] == ['a' * 81, 'tail']

    printed_lines.clear()
    pager_enabled['value'] = True
    cli.explicit_pager = True
    main.MyCli.output(cli, itertools.chain(['row1', 'row2']), SQLResult(status='ok'))
    assert paged_lines[-2:] == ['row1\n', 'row2\n']


def test_format_sqlresult_output_covers_extra_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    cli.redirect_formatter = DummyFormatter()
    cli.get_reserved_space = lambda: 1  # type: ignore[assignment]
    monkeypatch.setattr(main, 'Cursor', FakeCursorBase)
    rows = FakeCursorBase(rows=[], rowcount=0, description=[('id', 3, None, None, None, None, None)])
    result = SQLResult(
        header=['id'],
        rows=cast(Any, rows),
        preamble='preamble',
        status=main.FormattedText([('', 'formatted-status')]),
    )
    formatted = list(main.MyCli.format_sqlresult(cli, result, null_string='NULL'))
    assert 'preamble' in formatted
    _, kwargs = cli.main_formatter.calls[-1]
    assert kwargs['missing_value'] == 'NULL'
    assert kwargs['column_types'] == []
    assert kwargs['colalign'] == []

    paged_lines: list[str] = []
    printed_lines: list[str] = []
    status_prints: list[Any] = []
    monkeypatch.setattr(main.special, 'write_tee', lambda text: None)
    monkeypatch.setattr(main.special, 'write_once', lambda text: None)
    monkeypatch.setattr(main.special, 'write_pipe_once', lambda text: None)
    monkeypatch.setattr(main.special, 'is_redirected', lambda: False)
    monkeypatch.setattr(main.special, 'is_pager_enabled', lambda: True)
    monkeypatch.setattr(main.MyCli, 'get_output_margin', lambda self, status=None: 1)
    monkeypatch.setattr(click, 'echo_via_pager', lambda gen: paged_lines.extend(list(gen)))
    monkeypatch.setattr(click, 'secho', lambda line, **kwargs: printed_lines.append(str(line)))
    monkeypatch.setattr(main, 'print_formatted_text', lambda text, style=None: status_prints.append(text))
    cli.log_output = lambda text: None  # type: ignore[assignment]
    cli.explicit_pager = False
    main.MyCli.output(cli, itertools.chain(['x' * 81]), result)
    assert paged_lines[-1] == ('x' * 81) + '\n'
    monkeypatch.setattr(main.special, 'is_pager_enabled', lambda: False)
    main.MyCli.output(cli, itertools.chain(['short']), result)
    assert printed_lines[-1] == 'short'
    assert status_prints


def test_main_handles_click_exception_without_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoExitCode(click.ClickException):
        def __getattribute__(self, name: str) -> Any:
            if name == 'exit_code':
                raise AttributeError(name)
            return super().__getattribute__(name)

    monkeypatch.setattr(main, 'filtered_sys_argv', lambda: ['--help'])
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(NoExitCode('boom')))
    with pytest.raises(SystemExit) as excinfo:
        main.main()
    assert excinfo.value.code == 2


def test_filtered_sys_argv_covers_help_and_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.sys, 'argv', ['mycli', '-h'])
    assert main.filtered_sys_argv() == ['--help']
    monkeypatch.setattr(main.sys, 'argv', ['mycli', '-h', 'db.example'])
    assert main.filtered_sys_argv() == ['-h', 'db.example']


def test_main_wrapper_and_edit_and_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', lambda: ['--help'])
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: None)
    assert main.main() == 0

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: 7)
    assert main.main() == 7

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: 'bad')
    assert main.main() == 1

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(click.Abort()))
    with pytest.raises(SystemExit):
        main.main()

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(BrokenPipeError()))
    with pytest.raises(SystemExit):
        main.main()

    class ErrorWithCode(click.ClickException):
        exit_code = 9

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(ErrorWithCode('boom')))
    with pytest.raises(SystemExit):
        main.main()

    class ErrorNoCode(click.ClickException):
        pass

    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(ErrorNoCode('boom')))
    with pytest.raises(SystemExit):
        main.main()

    opened: list[bool] = []
    event = cast(
        Any,
        SimpleNamespace(
            current_buffer=SimpleNamespace(open_in_editor=lambda validate_and_handle=False: opened.append(validate_and_handle))
        ),
    )
    mycli.key_bindings.edit_and_execute(event)
    assert opened == [False]


def test_module_main_guard_calls_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_codes: list[int | None] = []
    monkeypatch.setattr(sys, 'exit', lambda code=0: exit_codes.append(code))
    monkeypatch.setattr(click.core.Command, 'main', lambda self, *args, **kwargs: 0)
    original_main = sys.modules.get('__main__')
    spec = importlib.util.spec_from_file_location('__main__', Path(main.__file__))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules['__main__'] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if original_main is not None:
            sys.modules['__main__'] = original_main
    assert exit_codes[-1] == 0


def test_click_entrypoint_branches_with_dummy_mycli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    monkeypatch.setattr(main, 'MyCli', make_dummy_mycli_class())
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: True)

    checkup_calls: list[Any] = []
    monkeypatch.setattr(main, 'main_checkup', lambda mycli: checkup_calls.append(mycli))
    result = runner.invoke(main.click_entrypoint, ['--checkup'])
    assert result.exit_code == 0
    assert len(checkup_calls) == 1

    result = runner.invoke(main.click_entrypoint, ['--csv', '--format', 'table'])
    assert result.exit_code == 1
    assert 'Conflicting --csv' in result.output

    result = runner.invoke(main.click_entrypoint, ['--table', '--format', 'csv'])
    assert result.exit_code == 1
    assert 'Conflicting --table' in result.output

    monkeypatch.setattr(main, 'MyCli', make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {'a': 'mysql://u:p@h/db'}}))
    result = runner.invoke(main.click_entrypoint, ['--list-dsn'])
    assert result.exit_code == 0
    assert 'a' in result.output

    monkeypatch.setattr(main, 'MyCli', make_dummy_mycli_class(config={'main': {}}))
    result = runner.invoke(main.click_entrypoint, ['--list-dsn'])
    assert result.exit_code == 1
    assert 'Invalid DSNs found' in result.output

    monkeypatch.setenv('MYSQL_UNIX_PORT', '/tmp/mysql.sock')
    monkeypatch.setenv('DSN', 'mysql://user:pw@host/db')
    monkeypatch.setattr(main, 'MyCli', make_dummy_mycli_class())
    result = runner.invoke(main.click_entrypoint, [])
    assert result.exit_code == 0
    assert 'MYSQL_UNIX_PORT environment variable is deprecated' in result.output
    assert 'DSN environment variable is deprecated' in result.output

    monkeypatch.delenv('MYSQL_UNIX_PORT', raising=False)
    monkeypatch.delenv('DSN', raising=False)
    monkeypatch.setattr(main, 'MyCli', make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {}}))
    result = runner.invoke(main.click_entrypoint, ['-d', 'missing-dsn'])
    assert result.exit_code == 1
    assert 'Could not find the specified DSN' in result.output

    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false'},
            'alias_dsn': {
                'prod': 'mysql://user:pw@host/db?ssl=true&ssl_ca=/tmp/ca.pem&socket=/tmp/mysql.sock&keepalive_ticks=9&character_set=utf8mb4'
            },
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    result = runner.invoke(main.click_entrypoint, ['-d', 'prod', '--ssl-mode', 'off', '--no-ssl'])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    connect_kwargs = dummy.connect_calls[-1]
    assert connect_kwargs['database'] == 'db'
    assert connect_kwargs['user'] == 'user'
    assert connect_kwargs['passwd'] == 'pw'
    assert connect_kwargs['socket'] == '/tmp/mysql.sock'
    assert connect_kwargs['character_set'] == 'utf8mb4'
    assert connect_kwargs['keepalive_ticks'] == 9

    dummy_class = make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {}})
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    result = runner.invoke(main.click_entrypoint, ['--execute', 'select 1\\G', '--format', 'csv', '--batch', 'queries.sql'])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.main_formatter.format_name == 'csv'
    assert dummy.run_query_calls[-1][0] == 'select 1'


def test_click_entrypoint_password_file_and_dsn_early_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = CliRunner()
    dummy_class = make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {}, 'connection': {'default_keepalive_ticks': 0}})
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)

    missing = runner.invoke(main.click_entrypoint, ['--password-file', str(tmp_path / 'missing.txt')])
    assert missing.exit_code == 1
    assert 'not found' in missing.output

    directory = runner.invoke(main.click_entrypoint, ['--password-file', str(tmp_path)])
    assert directory.exit_code == 1
    assert 'is a directory' in directory.output

    pw_file = tmp_path / 'pw.txt'
    pw_file.write_text('from-file\n', encoding='utf-8')
    result = runner.invoke(main.click_entrypoint, ['--password-file', str(pw_file)])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.connect_calls[-1]['passwd'] == 'from-file'

    monkeypatch.setenv('MYSQL_PWD', 'envpass')
    result = runner.invoke(main.click_entrypoint, [])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.connect_calls[-1]['passwd'] == 'envpass'
    monkeypatch.delenv('MYSQL_PWD', raising=False)

    monkeypatch.setattr(main, 'is_valid_connection_scheme', lambda text: (False, 'bogus'))
    result = runner.invoke(main.click_entrypoint, ['--password', 'bogus://dsn'])
    assert result.exit_code == 1
    assert 'Unknown connection scheme' in result.output

    monkeypatch.setattr(main, 'is_valid_connection_scheme', lambda text: (True, 'mysql'))
    result = runner.invoke(main.click_entrypoint, ['--password', 'mysql://dsn_user:dsn_pass@dsn_host/dsn_db'])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.connect_calls[-1]['database'] == 'dsn_db'


def test_click_entrypoint_list_and_dsn_option_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()

    class ErrorConfig(dict[str, Any]):
        def __getitem__(self, key: str) -> Any:
            if key == 'alias_dsn':
                raise RuntimeError('bad aliases')
            return super().__getitem__(key)

    dummy_class = make_dummy_mycli_class(config=cast(Any, ErrorConfig({'main': {}})))
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    result = runner.invoke(main.click_entrypoint, ['--list-dsn'])
    assert result.exit_code == 1
    assert 'bad aliases' in result.output

    dummy_class = make_dummy_mycli_class(
        config={'main': {}, 'alias_dsn': {'prod': 'mysql://u:p@h/db'}, 'connection': {'default_keepalive_ticks': 0}}
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    result = runner.invoke(main.click_entrypoint, ['prod'])
    assert result.exit_code == 0
    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.init_kwargs['myclirc'] == '~/.myclirc'
    assert dummy.dsn_alias == 'prod'

    result = runner.invoke(main.click_entrypoint, ['mysql://u:p@h/db'])
    assert result.exit_code == 0

    result = runner.invoke(main.click_entrypoint, ['--dsn', 'mysql://u:p@h/db'])
    assert result.exit_code == 0


def test_click_entrypoint_callback_covers_password_file_permission_and_generic_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {}, 'connection': {'default_keepalive_ticks': 0}})
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)
    cli_args = main.CliArgs()
    cli_args.password_file = '/tmp/secret'

    monkeypatch.setattr(builtins, 'open', lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)

    monkeypatch.setattr(builtins, 'open', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('boom')))
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)


def test_click_entrypoint_callback_covers_nested_empty_password_file_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    class TogglePasswordFile:
        def __init__(self) -> None:
            self.calls = 0

        def __bool__(self) -> bool:
            self.calls += 1
            return self.calls == 1

    dummy_class = make_dummy_mycli_class(config={'main': {}, 'alias_dsn': {}, 'connection': {'default_keepalive_ticks': 0}})
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)
    open_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_open(*args: Any, **kwargs: Any) -> None:
        open_calls.append((args, kwargs))
        return None

    monkeypatch.setattr(builtins, 'open', fake_open)
    cli_args = main.CliArgs()
    cli_args.password_file = cast(Any, TogglePasswordFile())
    call_click_entrypoint_direct(cli_args)

    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.connect_calls[-1]['passwd'] is None
    assert open_calls == []


def test_click_entrypoint_callback_covers_dsn_params_init_commands_and_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false', 'my_cnf_transition_done': 'true'},
            'connection': {'default_keepalive_ticks': 2},
            'alias_dsn': {
                'prod': (
                    'mysql://user:pw@db.example/prod_db'
                    '?ssl_mode=auto&ssl_ca=/tmp/ca.pem&ssl_capath=/tmp/capath'
                    '&ssl_cert=/tmp/cert.pem&ssl_key=/tmp/key.pem&ssl_cipher=AES256'
                    '&tls_version=TLSv1.2&ssl_verify_server_cert=true&socket=/tmp/mysql.sock'
                    '&keepalive_ticks=9&character_set=utf8mb4'
                )
            },
            'init-commands': {'a': 'set a=1', 'b': ['set b=2']},
            'alias_dsn.init-commands': {'prod': 'set c=3'},
        },
        my_cnf={'client': {}, 'mysqld': {}},
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)
    click_lines: list[str] = []
    monkeypatch.setattr(click, 'secho', lambda message='', **kwargs: click_lines.append(str(message)))
    monkeypatch.setattr(click, 'echo', lambda message='', **kwargs: click_lines.append(str(message)))

    cli_args = main.CliArgs()
    cli_args.database = 'prod'
    cli_args.init_command = 'set e=5'
    cli_args.use_keyring = 'reset'
    call_click_entrypoint_direct(cli_args)

    dummy = dummy_class.last_instance
    assert dummy is not None
    connect_kwargs = dummy.connect_calls[-1]
    assert connect_kwargs['database'] == 'prod_db'
    assert connect_kwargs['user'] == 'user'
    assert connect_kwargs['passwd'] == 'pw'
    assert connect_kwargs['ssl'] is None
    assert connect_kwargs['character_set'] == 'utf8mb4'
    assert connect_kwargs['keepalive_ticks'] == 9
    assert connect_kwargs['use_keyring'] is True
    assert connect_kwargs['reset_keyring'] is True
    assert connect_kwargs['init_command'] == 'set a=1; set b=2; set c=3; set e=5'
    assert any('Executing init-command:' in line for line in click_lines)


def test_click_entrypoint_callback_covers_database_dsn_and_verbose_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    click_lines: list[str] = []
    monkeypatch.setattr(click, 'secho', lambda message='', **kwargs: click_lines.append(str(message)))
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)

    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false', 'my_cnf_transition_done': 'true'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)

    cli_args = main.CliArgs()
    cli_args.list_dsn = True
    cli_args.verbose = True
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)
    assert 'prod : mysql://u:p@h/db' in click_lines

    click_lines.clear()

    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false', 'my_cnf_transition_done': 'true'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    cli_args = main.CliArgs()
    cli_args.database = (
        'mysql://dsn_user:dsn_pass@dsn_host/dsn_db'
        '?ssl_capath=/tmp/capath&ssl_cert=/tmp/cert.pem&ssl_key=/tmp/key.pem'
        '&ssl_cipher=AES256&tls_version=TLSv1.2&ssl_verify_server_cert=true'
    )
    cli_args.use_keyring = 'false'
    call_click_entrypoint_direct(cli_args)
    dummy = dummy_class.last_instance
    assert dummy is not None
    connect_kwargs = dummy.connect_calls[-1]
    assert connect_kwargs['database'] == 'dsn_db'
    assert connect_kwargs['user'] == 'dsn_user'
    assert connect_kwargs['passwd'] == 'dsn_pass'
    assert connect_kwargs['host'] == 'dsn_host'
    assert connect_kwargs['ssl']['capath'] == '/tmp/capath'
    assert connect_kwargs['ssl']['cert'] == '/tmp/cert.pem'
    assert connect_kwargs['ssl']['key'] == '/tmp/key.pem'
    assert connect_kwargs['ssl']['cipher'] == 'AES256'
    assert connect_kwargs['ssl']['tls_version'] == 'TLSv1.2'
    assert connect_kwargs['ssl']['check_hostname'] is True
    assert connect_kwargs['use_keyring'] is False


def test_click_entrypoint_callback_covers_misc_format_transition_and_execute_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    click_lines: list[str] = []
    monkeypatch.setattr(click, 'secho', lambda message='', **kwargs: click_lines.append(str(message)))
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(main.sys.stderr, 'isatty', lambda: False)

    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false', 'my_cnf_transition_done': 'false'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        },
        my_cnf={'client': {'prompt': 'mysql>'}, 'mysqld': {}},
        config_without_package_defaults={'main': {}},
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)

    pw_file = tmp_path / 'pw.txt'
    pw_file.write_text('from-file\n', encoding='utf-8')
    cli_args = main.CliArgs()
    cli_args.password_file = str(pw_file)
    call_click_entrypoint_direct(cli_args)
    assert dummy_class.last_instance is not None
    assert dummy_class.last_instance.connect_calls[-1]['passwd'] == 'from-file'

    cli_args = main.CliArgs()
    cli_args.csv = True
    call_click_entrypoint_direct(cli_args)
    assert cli_args.format == 'csv'

    cli_args = main.CliArgs()
    cli_args.table = True
    call_click_entrypoint_direct(cli_args)
    assert cli_args.format == 'table'

    assert any('Reading configuration from my.cnf files is deprecated.' in line for line in click_lines)

    execute_dummy_cls: type[Any] = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false', 'my_cnf_transition_done': 'true'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        }
    )
    monkeypatch.setattr(main, 'MyCli', execute_dummy_cls)
    monkeypatch.setattr(main.sys, 'stdin', SimpleNamespace(isatty=lambda: False))

    cli_args = main.CliArgs()
    cli_args.execute = 'select 1\\G'
    cli_args.format = 'tsv'
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)
    assert execute_dummy_cls.last_instance.main_formatter.format_name == 'tsv'
    assert execute_dummy_cls.last_instance.run_query_calls[-1][0] == 'select 1'

    cli_args = main.CliArgs()
    cli_args.execute = 'select 2\\G'
    cli_args.format = 'table'
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)
    assert execute_dummy_cls.last_instance.main_formatter.format_name == 'ascii'
    assert execute_dummy_cls.last_instance.run_query_calls[-1][0] == 'select 2'

    cli_args = main.CliArgs()
    cli_args.execute = 'select 3'
    cli_args.format = None
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)
    assert execute_dummy_cls.last_instance.main_formatter.format_name == 'tsv'

    def failing_run_query(self: Any, query: str, checkpoint: Any = None, new_line: bool = True) -> None:
        raise RuntimeError('execute failed')

    FailingExecuteMyCli = cast(Any, type('FailingExecuteMyCli', (execute_dummy_cls,), {'run_query': failing_run_query}))
    monkeypatch.setattr(main, 'MyCli', FailingExecuteMyCli)
    cli_args = main.CliArgs()
    cli_args.execute = 'select 4'
    with pytest.raises(SystemExit):
        call_click_entrypoint_direct(cli_args)
    assert any('execute failed' in line for line in click_lines)


def test_configure_pager_and_refresh_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.my_cnf = {'client': {}, 'mysqld': {}}
    cli.config = {'main': BoolSection({'pager': '', 'enable_pager': 'true'})}
    cli.read_my_cnf = lambda cnf, keys: {'pager': 'less', 'skip-pager': ''}  # type: ignore[assignment]
    set_pager_calls: list[str] = []
    disable_calls: list[bool] = []
    monkeypatch.delenv('LESS', raising=False)
    monkeypatch.setattr(main.special, 'set_pager', lambda pager: set_pager_calls.append(pager))
    monkeypatch.setattr(main.special, 'disable_pager', lambda: disable_calls.append(True))
    monkeypatch.setattr(main, 'WIN', True)
    monkeypatch.setattr(main.shutil, 'which', lambda name: None)
    main.MyCli.configure_pager(cli)
    assert os.environ['LESS'] == '-RXF'
    assert set_pager_calls == ['more']
    assert cli.explicit_pager is True

    class DisablePagerCalled(Exception):
        pass

    def fake_disable_pager() -> None:
        disable_calls.append(True)
        assert cli.explicit_pager is False
        raise DisablePagerCalled

    monkeypatch.setattr(main.special, 'disable_pager', fake_disable_pager)
    cli.read_my_cnf = lambda cnf, keys: {'pager': '', 'skip-pager': '1'}  # type: ignore[assignment]
    with pytest.raises(DisablePagerCalled):
        main.MyCli.configure_pager(cli)

    reset_calls: list[bool] = []
    refresh_calls: list[tuple[Any, Any, dict[str, Any]]] = []
    cli.completer = cast(Any, SimpleNamespace(keyword_casing='upper', reset_completions=lambda: reset_calls.append(True)))
    cli.main_formatter = SimpleNamespace(supported_formats=['ascii', 'csv'])
    cli.completion_refresher = SimpleNamespace(refresh=lambda sql, callback, options: refresh_calls.append((sql, callback, options)))
    cli.sqlexecute = 'sqlexecute'
    cli._on_completions_refreshed = lambda new_completer: None  # type: ignore[assignment]

    def fake_refresh(reset: bool = False) -> list[SQLResult]:
        return main.MyCli.refresh_completions(cli, reset=reset)

    result = fake_refresh(reset=True)
    assert reset_calls == [True]
    assert refresh_calls[0][2] == {
        'smart_completion': cli.smart_completion,
        'supported_formats': ['ascii', 'csv'],
        'keyword_casing': 'upper',
    }
    assert result[0].status == 'Auto-completion refresh started in the background.'

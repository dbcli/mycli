from __future__ import annotations

import builtins
import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Literal, cast

import pymysql
import pytest

from mycli import client_connection
from mycli.client_connection import ClientConnectionMixin
from mycli.constants import DEFAULT_CHARSET, EMPTY_PASSWORD_FLAG_SENTINEL, ER_MUST_CHANGE_PASSWORD_LOGIN


class DummyLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.error_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self.debug_calls.append((args, kwargs))

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.error_calls.append((args, kwargs))


class DummyClient(ClientConnectionMixin):
    def __init__(
        self,
        *,
        cnf: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        config_without_package_defaults: dict[str, Any] | None = None,
    ) -> None:
        self.cnf = cnf or default_cnf()
        self.mylogin_cnf = object()
        self.config = config or {'main': {}, 'connection': {}}
        self.config_without_package_defaults = config_without_package_defaults or {}
        self.keepalive_ticks: int | None = None
        self.sandbox_mode = False
        self.sqlexecute: Any = None
        self.logger = DummyLogger()
        self.echo_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def read_mylogin_cnf(self, cnf: Any) -> dict[str, Any]:
        assert cnf is self.mylogin_cnf
        return dict(self.cnf)

    def echo(self, *args: Any, **kwargs: Any) -> None:
        self.echo_calls.append((args, kwargs))


class WritableConfig(dict[str, Any]):
    encoding: str | None = None

    def __init__(self, value: dict[str, Any]) -> None:
        super().__init__(value)
        self.write_calls = 0

    def write(self) -> None:
        self.write_calls += 1


class FakeSQLExecute:
    calls: list[dict[str, Any]] = []
    effects: list[Any] = []
    sandbox_mode_value = False

    def __init__(self, **kwargs: Any) -> None:
        type(self).calls.append(dict(kwargs))
        if type(self).effects:
            effect = type(self).effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            if callable(effect):
                effect(kwargs)
        self.kwargs = kwargs
        self.sandbox_mode = type(self).sandbox_mode_value


def default_cnf() -> dict[str, Any]:
    return {
        'user': None,
        'password': None,
        'host': None,
        'port': None,
        'socket': None,
    }


@pytest.fixture(autouse=True)
def reset_fake_sql_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSQLExecute.calls = []
    FakeSQLExecute.effects = []
    FakeSQLExecute.sandbox_mode_value = False
    monkeypatch.setattr(client_connection, 'SQLExecute', FakeSQLExecute)
    monkeypatch.setattr(client_connection, 'WIN', False)
    monkeypatch.setattr(client_connection, 'guess_socket_location', lambda: None)


def op_error(code: int, message: str = 'error') -> pymysql.OperationalError:
    return pymysql.OperationalError(code, message)


def load_without_pwd_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    assert client_connection.__file__ is not None
    module_name = 'test_client_connection_without_pwd'
    spec = importlib.util.spec_from_file_location(module_name, client_connection.__file__)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'pwd':
            raise ImportError('no pwd')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_import_swallows_missing_pwd_module(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_without_pwd_module(monkeypatch)

    assert not hasattr(module, 'getpwuid')


def test_connect_defaults_to_port_socket_and_config_character_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DummyClient(config={'connection': {'default_character_set': 'latin1'}, 'main': {}})
    monkeypatch.setenv('USER', 'env_user')
    monkeypatch.setattr(client_connection, 'guess_socket_location', lambda: '/tmp/mysql.sock')
    monkeypatch.setattr(client_connection, 'WIN', True)

    client.connect(host='')

    call = FakeSQLExecute.calls[-1]
    assert call['user'] == 'env_user'
    assert call['port'] == 3306
    assert call['socket'] == '/tmp/mysql.sock'
    assert call['character_set'] == 'latin1'
    assert call['ssl'] == {}


def test_connect_uses_character_set_from_connection_config() -> None:
    client = DummyClient(config={'main': {}, 'connection': {'default_character_set': 'utf16'}})

    client.connect(host='db', port=3307)

    assert FakeSQLExecute.calls[-1]['character_set'] == 'utf16'


def test_connect_migrates_deprecated_character_set_from_main_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_wo = WritableConfig({'main': {'default_character_set': 'utf32'}})
    client = DummyClient(
        config={'main': {}, 'connection': {'default_character_set': 'utf16'}},
        config_without_package_defaults=config_wo,
    )
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        client_connection.click,
        'secho',
        lambda message, **kwargs: secho_calls.append((message, kwargs)),
    )

    client.connect(host='db', port=3307)

    assert FakeSQLExecute.calls[-1]['character_set'] == 'utf32'
    assert config_wo.encoding == 'utf-8'
    assert config_wo['connection']['default_character_set'] == 'utf32'
    assert 'default_character_set' not in config_wo['main']
    assert config_wo.write_calls == 1
    assert secho_calls == [
        (
            'Mycli 2.0 migration: automatically moving default_character_set from [main] to [connection] in ~/.myclirc .',
            {'err': True, 'fg': 'red'},
        )
    ]


def test_connect_uses_existing_connection_character_set_when_migrating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_wo = WritableConfig({
        'main': {'default_character_set': 'utf32'},
        'connection': {'default_character_set': 'utf16'},
    })
    client = DummyClient(
        config={'main': {}, 'connection': {'default_character_set': 'latin1'}},
        config_without_package_defaults=config_wo,
    )
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        client_connection.click,
        'secho',
        lambda message, **kwargs: secho_calls.append((message, kwargs)),
    )

    client.connect(host='db', port=3307)

    assert FakeSQLExecute.calls[-1]['character_set'] == 'utf16'
    assert config_wo['connection']['default_character_set'] == 'utf16'
    assert 'default_character_set' not in config_wo['main']
    assert config_wo.write_calls == 1
    assert secho_calls == [
        (
            'Mycli 2.0 migration: automatically moving default_character_set from [main] to [connection] in ~/.myclirc .',
            {'err': True, 'fg': 'red'},
        ),
        (
            'But connection.default_character_set already existed, with the value: "utf16".',
            {'err': True, 'fg': 'red'},
        ),
    ]


def test_connect_uses_default_character_set_when_none_configured() -> None:
    client = DummyClient()

    client.connect(host='db', port=3307)

    assert FakeSQLExecute.calls[-1]['character_set'] == DEFAULT_CHARSET


def test_connect_accepts_local_infile_true() -> None:
    client = DummyClient()

    client.connect(host='db', port=3307, local_infile=True)

    assert FakeSQLExecute.calls[-1]['local_infile'] is True


def test_connect_retrieves_password_from_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    get_password_calls: list[tuple[str, str]] = []

    def fake_get_password(domain: str, identifier: str) -> str:
        get_password_calls.append((domain, identifier))
        return 'from-keyring'

    monkeypatch.setattr(client_connection.keyring, 'get_password', fake_get_password)

    client.connect(user='alice', host='db', port=3307, passwd=None, use_keyring=True)

    assert FakeSQLExecute.calls[-1]['password'] == 'from-keyring'
    assert get_password_calls == [('mycli.net', 'alice@db:3307:')]


def test_connect_prompts_for_password_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    prompts: list[str] = []

    def fake_prompt(text: str, **_kwargs: Any) -> str:
        prompts.append(text)
        return 'prompted'

    monkeypatch.setattr(client_connection.click, 'prompt', fake_prompt)

    client.connect(user='alice', host='db', port=3307, passwd=EMPTY_PASSWORD_FLAG_SENTINEL)

    assert prompts == ['Enter password for alice']
    assert FakeSQLExecute.calls[-1]['password'] == 'prompted'


def test_connect_saves_password_to_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    set_password_calls: list[tuple[str, str, str]] = []
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(client_connection.keyring, 'get_password', lambda domain, identifier: 'old')
    monkeypatch.setattr(
        client_connection.keyring,
        'set_password',
        lambda domain, identifier, password: set_password_calls.append((domain, identifier, password)),
    )
    monkeypatch.setattr(client_connection.click, 'secho', lambda message, **kwargs: secho_calls.append((message, kwargs)))

    client.connect(user='alice', host='db', port=3307, passwd='new', use_keyring=True)

    assert set_password_calls == [('mycli.net', 'alice@db:3307:', 'new')]
    assert secho_calls == [('Password saved to the system keyring at mycli.net/alice@db:3307:', {'err': True})]


def test_connect_reports_keyring_save_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    secho_calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(client_connection.keyring, 'get_password', lambda domain, identifier: 'old')

    def fail_set_password(domain: str, identifier: str, password: str) -> None:
        raise RuntimeError('locked')

    monkeypatch.setattr(client_connection.keyring, 'set_password', fail_set_password)
    monkeypatch.setattr(client_connection.click, 'secho', lambda message, **kwargs: secho_calls.append((message, kwargs)))

    client.connect(user='alice', host='db', port=3307, passwd='new', use_keyring=True)

    assert secho_calls == [('Password not saved to the system keyring: locked', {'err': True, 'fg': 'red'})]


def test_connect_does_not_save_empty_password_to_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    set_password_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(client_connection.keyring, 'get_password', lambda domain, identifier: None)
    monkeypatch.setattr(
        client_connection.keyring,
        'set_password',
        lambda domain, identifier, password: set_password_calls.append((domain, identifier, password)),
    )

    client.connect(user='alice', host='db', port=3307, passwd='', use_keyring=True)

    assert set_password_calls == []


def test_connect_uses_ssh_jump_with_remote_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel_calls: list[dict[str, Any]] = []

    class FakeTunnel:
        local_socket = '/tmp/mycli-ssh.sock'
        remote_socket = '/var/run/mysqld/mysqld.sock'

        @classmethod
        def from_target(
            cls,
            ssh_jump: str,
            *,
            remote_host: str,
            remote_port: int,
            remote_socket: str | None = None,
            ssh_executable: str = 'ssh',
            ssh_config_options: str | None = None,
            ssh_cli_options: str | None = None,
            tunnel_method: Literal['auto', 'socket', 'port'] = 'auto',
        ) -> 'FakeTunnel':
            tunnel_calls.append({
                'ssh_jump': ssh_jump,
                'remote_host': remote_host,
                'remote_port': remote_port,
                'remote_socket': remote_socket,
                'ssh_executable': ssh_executable,
                'ssh_config_options': None,
                'ssh_cli_options': None,
            })
            return cls()

        def start(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(client_connection, 'SshTunnel', FakeTunnel)
    client = DummyClient(config={'main': {}, 'ssh': {'ssh_executable': '/opt/bin/ssh'}, 'connection': {}})

    client.connect(
        user='alice',
        host=None,
        port=None,
        socket='/var/run/mysqld/mysqld.sock',
        ssh_jump='bastion',
    )

    assert tunnel_calls == [
        {
            'ssh_jump': 'bastion',
            'remote_host': 'localhost',
            'remote_port': 3306,
            'remote_socket': '/var/run/mysqld/mysqld.sock',
            'ssh_executable': '/opt/bin/ssh',
            'ssh_config_options': None,
            'ssh_cli_options': None,
        }
    ]
    assert FakeSQLExecute.calls[-1]['host'] is None
    assert FakeSQLExecute.calls[-1]['port'] is None
    assert FakeSQLExecute.calls[-1]['socket'] == '/tmp/mycli-ssh.sock'
    assert FakeSQLExecute.calls[-1]['display_dsn'] == 'mysql://alice@localhost?socket=%2Fvar%2Frun%2Fmysqld%2Fmysqld.sock'


def test_connect_uses_ssh_jump_with_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTunnel:
        local_socket = None
        local_host = '127.0.0.1'
        local_port = 4406

        @classmethod
        def from_target(
            cls,
            _ssh_jump: str,
            *,
            remote_host: str,
            remote_port: int,
            remote_socket: str | None = None,
            ssh_executable: str = 'ssh',
            ssh_config_options: str | None = None,
            ssh_cli_options: str | None = None,
            tunnel_method: Literal['auto', 'socket', 'port'] = 'auto',
        ) -> 'FakeTunnel':
            return cls()

        def start(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(client_connection, 'SshTunnel', FakeTunnel)
    client = DummyClient()

    client.connect(user='alice', host='db.internal', port=3307, ssh_jump='bastion')

    assert FakeSQLExecute.calls[-1]['host'] == '127.0.0.1'
    assert FakeSQLExecute.calls[-1]['port'] == 4406
    assert FakeSQLExecute.calls[-1]['socket'] is None
    assert FakeSQLExecute.calls[-1]['display_dsn'] == 'mysql://alice@db.internal:3307'


def test_connect_passes_config_and_cli_ssh_options(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel_calls: list[dict[str, Any]] = []

    class FakeTunnel:
        local_socket = '/tmp/mycli-ssh.sock'

        @classmethod
        def from_target(
            cls,
            ssh_jump: str,
            *,
            remote_host: str,
            remote_port: int,
            remote_socket: str | None = None,
            ssh_executable: str = 'ssh',
            ssh_config_options: str | None = None,
            ssh_cli_options: str | None = None,
            tunnel_method: Literal['auto', 'socket', 'port'] = 'auto',
        ) -> 'FakeTunnel':
            tunnel_calls.append({
                'ssh_jump': ssh_jump,
                'ssh_config_options': ssh_config_options,
                'ssh_cli_options': ssh_cli_options,
            })
            return cls()

        def start(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(client_connection, 'SshTunnel', FakeTunnel)
    client = DummyClient(config={'main': {}, 'ssh': {'ssh_options': '-o LogLevel=ERROR'}, 'connection': {}})

    client.connect(host='db.internal', ssh_jump='bastion', ssh_cli_options='-o Compression=yes')

    assert tunnel_calls == [
        {
            'ssh_jump': 'bastion',
            'ssh_config_options': '-o LogLevel=ERROR',
            'ssh_cli_options': '-o Compression=yes',
        }
    ]


def test_connect_reports_ssh_jump_start_error_and_closes_tunnel(monkeypatch: pytest.MonkeyPatch) -> None:
    close_calls: list[bool] = []
    secho_calls: list[tuple[str, dict[str, Any]]] = []

    class FakeTunnel:
        local_socket = '/tmp/mycli-ssh.sock'
        remote_socket = None

        @classmethod
        def from_target(
            cls,
            _ssh_jump: str,
            *,
            remote_host: str,
            remote_port: int,
            remote_socket: str | None = None,
            ssh_executable: str = 'ssh',
            ssh_config_options: str | None = None,
            ssh_cli_options: str | None = None,
            tunnel_method: Literal['auto', 'socket', 'port'] = 'auto',
        ) -> 'FakeTunnel':
            return cls()

        def start(self) -> None:
            raise client_connection.SshTunnelError('no tunnel')

        def close(self) -> None:
            close_calls.append(True)

    monkeypatch.setattr(client_connection, 'SshTunnel', FakeTunnel)
    monkeypatch.setattr(client_connection.click, 'secho', lambda message, **kwargs: secho_calls.append((message, kwargs)))
    client = DummyClient()

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db.internal', ssh_jump='bastion')

    assert excinfo.value.code == 1
    assert close_calls == [True]
    assert secho_calls == [('Error: Unable to start SSH tunnel: no tunnel', {'err': True, 'fg': 'red'})]
    assert FakeSQLExecute.calls == []


def test_connect_swallows_ssh_jump_cleanup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTunnel:
        local_socket = '/tmp/mycli-ssh.sock'
        remote_socket = None

        @classmethod
        def from_target(
            cls,
            _ssh_jump: str,
            *,
            remote_host: str,
            remote_port: int,
            remote_socket: str | None = None,
            ssh_executable: str = 'ssh',
            ssh_config_options: str | None = None,
            ssh_cli_options: str | None = None,
            tunnel_method: Literal['auto', 'socket', 'port'] = 'auto',
        ) -> 'FakeTunnel':
            return cls()

        def start(self) -> None:
            raise OSError('no process')

        def close(self) -> None:
            raise RuntimeError('close failed')

    monkeypatch.setattr(client_connection, 'SshTunnel', FakeTunnel)
    client = DummyClient()

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db.internal', ssh_jump='bastion')

    assert excinfo.value.code == 1


def test_connect_retries_without_ssl_for_auto_handshake_error() -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(client_connection.HANDSHAKE_ERROR), None]

    client.connect(host='db', port=3307, ssl={'mode': 'auto', 'ca': '/ca.pem'})

    assert len(FakeSQLExecute.calls) == 2
    assert FakeSQLExecute.calls[0]['ssl'] == {'mode': 'auto', 'ca': '/ca.pem'}
    assert FakeSQLExecute.calls[1]['ssl'] is None


def test_connect_adds_default_ssl_ca_path() -> None:
    client = DummyClient(config={'main': {}, 'connection': {'default_ssl_ca_path': '/ca/path'}})

    client.connect(host='db', port=3307, ssl={'mode': 'on'})

    assert FakeSQLExecute.calls[-1]['ssl'] == {'mode': 'on', 'capath': '/ca/path'}


def test_connect_exits_when_ssl_retry_also_fails() -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [
        op_error(client_connection.HANDSHAKE_ERROR, 'first'),
        op_error(client_connection.HANDSHAKE_ERROR, 'second'),
    ]

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db', port=3307, ssl={'mode': 'auto'})

    assert excinfo.value.code == 1
    assert len(FakeSQLExecute.calls) == 2


def test_connect_prompts_and_retries_after_access_denied_without_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(client_connection.ACCESS_DENIED_ERROR), None]
    monkeypatch.setattr(client_connection.click, 'prompt', lambda *_args, **_kwargs: 'new-secret')

    client.connect(user='alice', host='db', port=3307, passwd=None)

    assert len(FakeSQLExecute.calls) == 2
    assert FakeSQLExecute.calls[0]['password'] is None
    assert FakeSQLExecute.calls[1]['password'] == 'new-secret'


def test_connect_exits_when_password_retry_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [
        op_error(client_connection.ACCESS_DENIED_ERROR, 'first'),
        op_error(client_connection.ACCESS_DENIED_ERROR, 'second'),
    ]
    monkeypatch.setattr(client_connection.click, 'prompt', lambda *_args, **_kwargs: 'new-secret')

    with pytest.raises(SystemExit) as excinfo:
        client.connect(user='alice', host='db', port=3307, passwd=None)

    assert excinfo.value.code == 1


def test_connect_exits_when_password_retry_still_has_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [
        op_error(client_connection.ACCESS_DENIED_ERROR, 'first'),
        op_error(client_connection.ACCESS_DENIED_ERROR, 'second'),
    ]
    monkeypatch.setattr(client_connection.click, 'prompt', lambda *_args, **_kwargs: None)

    with pytest.raises(SystemExit) as excinfo:
        client.connect(user='alice', host='db', port=3307, passwd=None)

    assert excinfo.value.code == 1


def test_connect_reports_expired_password_login_error() -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(ER_MUST_CHANGE_PASSWORD_LOGIN, 'expired')]

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db', port=3307)

    assert excinfo.value.code == 1
    assert any('password has expired' in call[0][0] for call in client.echo_calls)


def test_connect_sets_sandbox_mode_when_sqlexecute_enters_sandbox() -> None:
    client = DummyClient()
    FakeSQLExecute.sandbox_mode_value = True

    client.connect(host='db', port=3307)

    assert client.sandbox_mode is True
    assert any('password has expired' in call[0][0] for call in client.echo_calls)


@pytest.mark.parametrize(
    ('code', 'message'),
    (
        (
            client_connection.CR_SERVER_LOST,
            'Connection to server lost. If this error persists',
        ),
        (9999, 'other failure'),
    ),
)
def test_connect_exits_for_server_lost_and_other_operational_errors(code: int, message: str) -> None:
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(code, 'other failure')]

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db', port=3307)

    assert excinfo.value.code == 1
    assert any(message in call[0][0] for call in client.echo_calls)


def test_connect_reports_socket_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    socket_path = tmp_path / 'mysql.sock'
    socket_path.write_text('', encoding='utf-8')
    client = DummyClient()
    monkeypatch.setattr(client_connection, 'getpwuid', lambda uid: SimpleNamespace(pw_name='socket-owner'))

    client.connect(user='alice', socket=str(socket_path), port=None)

    assert any(f'Connecting to socket {socket_path}, owned by user socket-owner' in call[0][0] for call in client.echo_calls)
    assert len(FakeSQLExecute.calls) == 1


def test_connect_falls_back_to_tcp_after_socket_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    socket_path = tmp_path / 'mysql.sock'
    socket_path.write_text('', encoding='utf-8')
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(2002, 'no socket'), None]
    monkeypatch.setattr(client_connection, 'getpwuid', lambda uid: SimpleNamespace(pw_name='socket-owner'))

    client.connect(user='alice', socket=str(socket_path), port=None)

    assert any('Retrying over TCP/IP' in call[0][0] for call in client.echo_calls)
    assert len(FakeSQLExecute.calls) == 2


def test_connect_reports_unknown_socket_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    socket_path = tmp_path / 'mysql.sock'
    socket_path.write_text('', encoding='utf-8')
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(9999, 'bad socket')]

    def fail_getpwuid(uid: int) -> Any:
        raise KeyError(uid)

    monkeypatch.setattr(client_connection, 'getpwuid', fail_getpwuid)

    with pytest.raises(SystemExit):
        client.connect(socket=str(socket_path), port=None)

    assert any(f'Connecting to socket {socket_path}, owned by user <unknown>' in call[0][0] for call in client.echo_calls)


def test_connect_exits_for_unhandled_socket_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    socket_path = tmp_path / 'mysql.sock'
    socket_path.write_text('', encoding='utf-8')
    client = DummyClient()
    FakeSQLExecute.effects = [op_error(9999, 'bad socket')]
    monkeypatch.setattr(client_connection, 'getpwuid', lambda uid: SimpleNamespace(pw_name='socket-owner'))

    with pytest.raises(SystemExit) as excinfo:
        client.connect(socket=str(socket_path), port=None)

    assert excinfo.value.code == 1


def test_connect_exits_for_invalid_port() -> None:
    client = DummyClient()

    class BadPort:
        def __init__(self) -> None:
            self.truth_values = iter([True, False, False, True])

        def __bool__(self) -> bool:
            return next(self.truth_values)

        def __int__(self) -> int:
            raise ValueError

        def __str__(self) -> str:
            return 'not-a-port'

    with pytest.raises(SystemExit) as excinfo:
        client.connect(host='db', port=cast(Any, BadPort()))

    assert excinfo.value.code == 1
    assert client.echo_calls == [(("Error: Invalid port number: 'not-a-port'.",), {'err': True, 'fg': 'red'})]


class FakeConn:
    def __init__(self, ping_effects: list[Any]) -> None:
        self.ping_effects = ping_effects
        self.select_db_calls: list[str] = []

    def ping(self, reconnect: bool = False) -> None:
        effect = self.ping_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect

    def select_db(self, dbname: str) -> None:
        self.select_db_calls.append(dbname)


class FakeReconnectSQLExecute:
    def __init__(self, conn: FakeConn, *, connection_id: int = 1, dbname: str = 'db') -> None:
        self.conn = conn
        self.connection_id = connection_id
        self.next_connection_id = connection_id + 1
        self.dbname = dbname
        self.connect_calls = 0

    def reset_connection_id(self) -> None:
        self.connection_id = self.next_connection_id

    def connect(self) -> None:
        self.connect_calls += 1


def test_reconnect_returns_true_when_ping_succeeds() -> None:
    client = DummyClient()
    client.sqlexecute = FakeReconnectSQLExecute(FakeConn([None]))

    assert client.reconnect() is True
    assert client.echo_calls == [(('Already connected.',), {'fg': 'yellow'})]


def test_reconnect_uses_ping_reconnect_and_selects_current_database() -> None:
    client = DummyClient()
    conn = FakeConn([pymysql.err.Error('stale'), None])
    client.sqlexecute = FakeReconnectSQLExecute(conn, connection_id=10, dbname='selected')
    client.sqlexecute.next_connection_id = 10

    assert client.reconnect(database='newdb') is True
    assert conn.select_db_calls == ['selected']


def test_reconnect_reports_session_reset_when_connection_id_changes() -> None:
    client = DummyClient()
    conn = FakeConn([pymysql.err.Error('stale'), None])
    client.sqlexecute = FakeReconnectSQLExecute(conn, connection_id=10, dbname='')

    assert client.reconnect(database='newdb') is True
    assert any(call[0] == ('Any session state was reset.',) for call in client.echo_calls)


def test_reconnect_creates_new_connection_after_ping_reconnect_fails() -> None:
    client = DummyClient()
    conn = FakeConn([pymysql.err.Error('stale'), pymysql.err.Error('still stale')])
    client.sqlexecute = FakeReconnectSQLExecute(conn)

    assert client.reconnect() is True
    assert client.sqlexecute.connect_calls == 1
    assert any(call[0] == ('New connection created successfully.',) for call in client.echo_calls)


def test_reconnect_returns_false_when_new_connection_fails() -> None:
    client = DummyClient()
    conn = FakeConn([pymysql.err.Error('stale'), pymysql.err.Error('still stale')])
    sqlexecute = FakeReconnectSQLExecute(conn)

    def fail_connect() -> None:
        raise pymysql.OperationalError(2003, 'no route')

    sqlexecute.connect = fail_connect  # type: ignore[method-assign]
    client.sqlexecute = sqlexecute

    assert client.reconnect() is False
    assert any('no route' in call[0][0] for call in client.echo_calls)

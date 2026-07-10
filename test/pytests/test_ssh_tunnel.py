from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, cast

import pytest

from mycli import ssh_tunnel
from mycli.ssh_tunnel import SshTunnel, SshTunnelError, SshTunnelTarget


def test_find_free_local_port_binds_default_host(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    class FakeSocket:
        def __enter__(self) -> 'FakeSocket':
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def bind(self, address: tuple[str, int]) -> None:
            calls.append(('bind', address))

        def getsockname(self) -> tuple[str, int]:
            return ('localhost', 4406)

    def fake_socket(family: int, kind: int) -> FakeSocket:
        calls.append(('socket', (family, kind)))
        return FakeSocket()

    monkeypatch.setattr(ssh_tunnel.socket, 'socket', fake_socket)

    assert ssh_tunnel._find_free_local_port(None) == 4406
    assert calls == [
        ('socket', (ssh_tunnel.socket.AF_INET, ssh_tunnel.socket.SOCK_STREAM)),
        ('bind', ('localhost', 0)),
    ]


def test_make_local_socket_path_unlinks_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    def fake_mkstemp(*, prefix: str, suffix: str) -> tuple[int, str]:
        calls.append(('mkstemp', (prefix, suffix)))
        return (7, '/tmp/mycli-ssh.sock')

    monkeypatch.setattr(ssh_tunnel.tempfile, 'mkstemp', fake_mkstemp)
    monkeypatch.setattr(ssh_tunnel.os, 'close', lambda fd: calls.append(('close', fd)))
    monkeypatch.setattr(ssh_tunnel.os, 'unlink', lambda path: calls.append(('unlink', path)))

    assert ssh_tunnel._make_local_socket_path() == '/tmp/mycli-ssh.sock'
    assert calls == [
        ('mkstemp', ('mycli-ssh-', '.sock')),
        ('close', 7),
        ('unlink', '/tmp/mycli-ssh.sock'),
    ]


def test_check_local_socket_path_limit_accepts_maximum_length() -> None:
    path = '/' + 's' * (ssh_tunnel.MAX_UNIX_SOCKET_PATH_BYTES - 1)

    ssh_tunnel._check_local_socket_path_limit(path)


def test_check_local_socket_path_limit_rejects_too_long_path() -> None:
    path = '/' + 's' * ssh_tunnel.MAX_UNIX_SOCKET_PATH_BYTES

    with pytest.raises(SshTunnelError, match='Local SSH socket path is too long for sockaddr_un'):
        ssh_tunnel._check_local_socket_path_limit(path)


def test_ssh_tunnel_target_parse_handles_target_with_port() -> None:
    target = SshTunnelTarget.parse('alice@bastion:2222')

    assert target.ssh_target == 'alice@bastion'
    assert target.ssh_port == 2222


def test_ssh_tunnel_target_parse_handles_target_without_port() -> None:
    target = SshTunnelTarget.parse('alice@bastion')

    assert target.ssh_target == 'alice@bastion'
    assert target.ssh_port is None


def test_ssh_tunnel_command_includes_forward_and_ssh_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        ssh_port=2222,
        remote_host='db.internal',
        remote_port=3307,
    )

    assert tunnel.command()[0] == 'ssh'
    assert '/tmp/mycli-ssh.sock:db.internal:3307' in tunnel.command()
    assert 'alice@bastion' in tunnel.command()
    assert '2222' in tunnel.command()


def test_ssh_tunnel_command_uses_configured_ssh_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        ssh_executable='/opt/bin/ssh',
    )

    assert tunnel.command()[0] == '/opt/bin/ssh'


def test_ssh_tunnel_command_appends_cli_options_after_config_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        ssh_config_options='-o LogLevel=ERROR',
        ssh_cli_options='-o Compression=yes',
    )

    assert tunnel.command() == [
        'ssh',
        '-o',
        'LogLevel=ERROR',
        '-o',
        'Compression=yes',
        '-N',
        '-L',
        '/tmp/mycli-ssh.sock:db.internal:3307',
        'alice@bastion',
    ]


def test_ssh_tunnel_command_forwards_remote_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        remote_socket='/var/run/mysqld/mysqld.sock',
    )

    assert '/tmp/mycli-ssh.sock:/var/run/mysqld/mysqld.sock' in tunnel.command()
    assert '/tmp/mycli-ssh.sock:db.internal:3307' not in tunnel.command()


def test_ssh_tunnel_command_uses_local_port_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_find_free_local_port', lambda local_host: 4406)

    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        tunnel_method='port',
    )

    assert tunnel.true_tunnel_method == 'port'
    assert 'localhost:4406:db.internal:3307' in tunnel.command()


def test_ssh_tunnel_command_uses_local_port_forward_for_remote_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_find_free_local_port', lambda local_host: 4406)

    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        remote_socket='/var/run/mysqld/mysqld.sock',
        tunnel_method='port',
    )

    assert 'localhost:4406:/var/run/mysqld/mysqld.sock' in tunnel.command()
    assert 'localhost:4406:db.internal:3307' not in tunnel.command()


def test_ssh_tunnel_from_target_allocates_local_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')

    tunnel = SshTunnel.from_target('alice@bastion:2222', remote_host='db.internal', remote_port=3307)

    assert tunnel.ssh_target == 'alice@bastion'
    assert tunnel.ssh_port == 2222
    assert tunnel.remote_host == 'db.internal'
    assert tunnel.remote_port == 3307


def test_ssh_tunnel_from_target_uses_configured_ssh_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')

    tunnel = SshTunnel.from_target(
        'alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        ssh_executable='/opt/bin/ssh',
    )

    assert tunnel.ssh_executable == '/opt/bin/ssh'


def test_ssh_tunnel_auto_uses_port_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, 'WIN', True)
    monkeypatch.setattr(ssh_tunnel, '_find_free_local_port', lambda local_host: 4406)

    tunnel = SshTunnel.from_target('alice@bastion', remote_host='db.internal', remote_port=3307)

    assert tunnel.tunnel_method == 'auto'
    assert tunnel.true_tunnel_method == 'port'
    assert tunnel.local_host == 'localhost'
    assert tunnel.local_port == 4406
    assert tunnel.local_socket is None


def test_ssh_tunnel_start_waits_until_local_socket_listens(monkeypatch: pytest.MonkeyPatch) -> None:
    started_commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self, command: list[str], **_kwargs: Any) -> None:
            started_commands.append(command)

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def kill(self) -> None:
            pass

    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', FakeProcess)
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    checks = iter([False, True])
    monkeypatch.setattr(tunnel, '_is_listening', lambda: next(checks))

    tunnel.start()
    tunnel.close()

    assert started_commands == [tunnel.command()]


def test_ssh_tunnel_start_reports_process_exit_before_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 255

        def poll(self) -> int:
            return 255

    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', FakeProcess)
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(SshTunnelError, match='exited before it was ready'):
        tunnel.start()


def test_ssh_tunnel_start_reports_process_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError('missing ssh')

    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', fail_popen)
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(SshTunnelError, match='Unable to start SSH tunnel process: missing ssh') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_ssh_tunnel_start_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        ready_timeout=0,
    )
    monkeypatch.setattr(tunnel, '_run', lambda: None)

    with pytest.raises(SshTunnelError, match='Timed out waiting for SSH tunnel'):
        tunnel.start()


def test_ssh_tunnel_close_terminates_running_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            return 0

    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5']


def test_ssh_tunnel_close_kills_process_after_terminate_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeProcess:
        def __init__(self) -> None:
            self.wait_calls = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            self.wait_calls += 1
            if self.wait_calls == 1:
                assert timeout is not None
                raise subprocess.TimeoutExpired('ssh', timeout)
            return 0

        def kill(self) -> None:
            calls.append('kill')

    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5', 'kill', 'wait:None']


def test_ssh_tunnel_close_joins_running_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeThread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            calls.append(f'join:{timeout}')

    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )
    tunnel._thread = cast(Any, FakeThread())

    tunnel.close()

    assert calls == ['join:5']


def test_ssh_tunnel_close_removes_local_socket_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_socket = tmp_path / 'mycli-ssh.sock'
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: str(local_socket))
    local_socket.touch()
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )

    tunnel.close()

    assert not local_socket.exists()


def test_ssh_tunnel_is_listening_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []

    class FakeSocket:
        def __enter__(self) -> 'FakeSocket':
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def settimeout(self, timeout: float) -> None:
            calls.append(('settimeout', timeout))

        def connect(self, address: str) -> None:
            calls.append(('connect', address))

    def fake_socket(family: int, kind: int) -> FakeSocket:
        calls.append(('socket', (family, kind)))
        return FakeSocket()

    monkeypatch.setattr(ssh_tunnel.socket, 'socket', fake_socket)
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )

    assert tunnel._is_listening() is True
    assert calls == [
        ('socket', (ssh_tunnel.socket.AF_UNIX, ssh_tunnel.socket.SOCK_STREAM)),
        ('settimeout', 0.05),
        ('connect', '/tmp/mycli-ssh.sock'),
    ]


def test_ssh_tunnel_is_listening_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSocket:
        def __enter__(self) -> 'FakeSocket':
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def settimeout(self, _timeout: float) -> None:
            pass

        def connect(self, _address: str) -> None:
            raise OSError

    def fake_socket(*_args: Any, **_kwargs: Any) -> FakeSocket:
        return FakeSocket()

    monkeypatch.setattr(ssh_tunnel.socket, 'socket', fake_socket)
    monkeypatch.setattr(ssh_tunnel, '_make_local_socket_path', lambda: '/tmp/mycli-ssh.sock')
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
    )

    assert tunnel._is_listening() is False


def test_ssh_tunnel_is_listening_checks_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, int], float]] = []

    class FakeConnection:
        def __enter__(self) -> 'FakeConnection':
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

    def fake_create_connection(address: tuple[str, int], timeout: float) -> FakeConnection:
        calls.append((address, timeout))
        return FakeConnection()

    monkeypatch.setattr(ssh_tunnel.socket, 'create_connection', fake_create_connection)
    monkeypatch.setattr(ssh_tunnel, '_find_free_local_port', lambda local_host: 4406)
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        tunnel_method='port',
    )

    assert tunnel._is_listening() is True
    assert calls == [(('localhost', 4406), 0.05)]


def test_ssh_tunnel_is_listening_returns_false_without_local_endpoint() -> None:
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        tunnel_method='port',
    )
    tunnel.local_host = None
    tunnel.local_port = None

    assert tunnel._is_listening() is False

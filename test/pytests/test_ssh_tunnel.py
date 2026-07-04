from __future__ import annotations

import socket
import subprocess
from typing import Any, cast

import pytest

from mycli import ssh_tunnel
from mycli.ssh_tunnel import SshTunnel, SshTunnelError, SshTunnelTarget


def test_ssh_tunnel_target_parse_handles_target_with_port() -> None:
    target = SshTunnelTarget.parse('alice@bastion:2222')

    assert target.ssh_target == 'alice@bastion'
    assert target.ssh_port == 2222


def test_ssh_tunnel_target_parse_handles_target_without_port() -> None:
    target = SshTunnelTarget.parse('alice@bastion')

    assert target.ssh_target == 'alice@bastion'
    assert target.ssh_port is None


def test_ssh_tunnel_command_includes_forward_and_ssh_port() -> None:
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        ssh_port=2222,
        remote_host='db.internal',
        remote_port=3307,
        local_port=4406,
    )

    assert tunnel.command()[0] == 'ssh'
    assert '127.0.0.1:4406:db.internal:3307' in tunnel.command()
    assert 'alice@bastion' in tunnel.command()
    assert '2222' in tunnel.command()


def test_ssh_tunnel_command_uses_configured_ssh_executable() -> None:
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        local_port=4406,
        ssh_executable='/opt/bin/ssh',
    )

    assert tunnel.command()[0] == '/opt/bin/ssh'


def test_ssh_tunnel_command_forwards_remote_socket() -> None:
    tunnel = SshTunnel(
        ssh_target='alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        remote_socket='/var/run/mysqld/mysqld.sock',
        local_port=4406,
    )

    assert '127.0.0.1:4406:/var/run/mysqld/mysqld.sock' in tunnel.command()
    assert '127.0.0.1:4406:db.internal:3307' not in tunnel.command()


def test_ssh_tunnel_from_target_allocates_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_tunnel, '_find_free_local_port', lambda: 4406)

    tunnel = SshTunnel.from_target('alice@bastion:2222', remote_host='db.internal', remote_port=3307)

    assert tunnel.ssh_target == 'alice@bastion'
    assert tunnel.ssh_port == 2222
    assert tunnel.local_port == 4406
    assert tunnel.remote_host == 'db.internal'
    assert tunnel.remote_port == 3307


def test_ssh_tunnel_from_target_uses_configured_ssh_executable() -> None:
    tunnel = SshTunnel.from_target(
        'alice@bastion',
        remote_host='db.internal',
        remote_port=3307,
        ssh_executable='/opt/bin/ssh',
    )

    assert tunnel.ssh_executable == '/opt/bin/ssh'


def test_ssh_tunnel_start_waits_until_local_port_listens(monkeypatch: pytest.MonkeyPatch) -> None:
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
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
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
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(SshTunnelError, match='exited before it was ready'):
        tunnel.start()


def test_ssh_tunnel_start_reports_process_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError('missing ssh')

    monkeypatch.setattr(ssh_tunnel.subprocess, 'Popen', fail_popen)
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(SshTunnelError, match='Unable to start SSH tunnel process: missing ssh') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_ssh_tunnel_start_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
        ready_timeout=0,
    )
    monkeypatch.setattr(tunnel, '_run', lambda: None)

    with pytest.raises(SshTunnelError, match='Timed out waiting for SSH tunnel'):
        tunnel.start()


def test_ssh_tunnel_close_terminates_running_process() -> None:
    calls: list[str] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            return 0

    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5']


def test_ssh_tunnel_close_kills_process_after_terminate_timeout() -> None:
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

    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5', 'kill', 'wait:None']


def test_ssh_tunnel_close_joins_running_thread() -> None:
    calls: list[str] = []

    class FakeThread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            calls.append(f'join:{timeout}')

    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )
    tunnel._thread = cast(Any, FakeThread())

    tunnel.close()

    assert calls == ['join:5']


def test_ssh_tunnel_is_listening_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
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
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )

    assert tunnel._is_listening() is True
    assert calls == [(('127.0.0.1', 4406), 0.05)]


def test_ssh_tunnel_is_listening_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_create_connection(*_args: Any, **_kwargs: Any) -> None:
        raise socket.timeout

    monkeypatch.setattr(ssh_tunnel.socket, 'create_connection', fail_create_connection)
    tunnel = SshTunnel(
        ssh_target='bastion',
        remote_host='db.internal',
        remote_port=3306,
        local_port=4406,
    )

    assert tunnel._is_listening() is False

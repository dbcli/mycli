from __future__ import annotations

import os
import socket
import subprocess
import threading
from typing import Any, cast

import pytest

from mycli import boundary_tunnel
from mycli.boundary_tunnel import BoundaryTunnel, BoundaryTunnelError

CONNECTION_DETAILS = (
    '{"address":"127.0.0.1","credentials":[{"secret":{"decoded":{"username":"1234","password":"5678"}}}],'
    '"expiration":"2030-01-02T03:04:05.000000+0000"}\n'
)


@pytest.mark.parametrize('address', [None, ''])
def test_boundary_tunnel_command_uses_target_and_local_listener(address: str | None) -> None:
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_executable='/opt/bin/boundary',
        address=address,
        local_port=4406,
    )

    assert tunnel.command() == [
        '/opt/bin/boundary',
        'connect',
        '-target-id=ttcp_123',
        '-listen-addr=127.0.0.1',
        '-listen-port=4406',
        '-format=json',
    ]


def test_boundary_tunnel_command_uses_configured_address() -> None:
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        address='https://boundary.example.com',
        local_port=4406,
    )

    assert tunnel.command()[-1] == '-addr=https://boundary.example.com'


@pytest.mark.parametrize('boundary_options', [None, ''])
def test_boundary_tunnel_command_ignores_empty_options(boundary_options: str | None) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', boundary_options=boundary_options, local_port=4406)

    assert tunnel.command()[2] == '-target-id=ttcp_123'


def test_boundary_tunnel_command_splits_options_before_generated_flags() -> None:
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_options='-name "my database" -target-id=ignored',
        local_port=4406,
    )

    assert tunnel.command()[2:6] == [
        '-name',
        'my database',
        '-target-id=ignored',
        '-target-id=ttcp_123',
    ]


@pytest.mark.parametrize('auth_method_id', [None, ''])
def test_boundary_tunnel_environment_uses_parent_default(auth_method_id: str | None) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', auth_method_id=auth_method_id)

    assert tunnel._environment() is None


def test_boundary_tunnel_environment_sets_configured_auth_method(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('BOUNDARY_AUTH_METHOD_ID', 'ampw_parent')
    tunnel = BoundaryTunnel(target_id='ttcp_123', auth_method_id='ampw_config')

    environment = tunnel._environment()

    assert environment is not None
    assert environment['BOUNDARY_AUTH_METHOD_ID'] == 'ampw_config'
    assert os.environ['BOUNDARY_AUTH_METHOD_ID'] == 'ampw_parent'


def test_boundary_tunnel_allocates_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boundary_tunnel, '_find_free_local_port', lambda: 4406)

    tunnel = BoundaryTunnel(target_id='ttcp_123')

    assert tunnel.local_port == 4406


def test_find_free_local_port_returns_available_port() -> None:
    port = boundary_tunnel._find_free_local_port()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', port))


def test_boundary_tunnel_start_reads_stdout_in_worker_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    read_threads: list[str] = []

    class FakeProcess:
        returncode = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def fake_run() -> None:
        tunnel.process = cast(Any, FakeProcess())
        tunnel._started.set()
        tunnel._read_stdout()
        tunnel._output_ready.set()

    def fake_read_stdout() -> None:
        read_threads.append(threading.current_thread().name)
        tunnel.stdout = CONNECTION_DETAILS

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    monkeypatch.setattr(tunnel, '_run', fake_run)
    monkeypatch.setattr(tunnel, '_read_stdout', fake_read_stdout)
    checks = iter([False, True])
    monkeypatch.setattr(tunnel, '_is_listening', lambda: next(checks))

    tunnel.start()

    assert read_threads == ['mycli-boundary-tunnel']
    assert tunnel.stdout == CONNECTION_DETAILS
    assert tunnel.username == '1234'
    assert tunnel.password == '5678'
    assert tunnel.expiry is not None


def test_boundary_tunnel_start_waits_for_process_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        tunnel._started.set()
        tunnel.stdout = CONNECTION_DETAILS
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_run', lambda: None)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: True)
    monkeypatch.setattr(boundary_tunnel.time, 'sleep', fake_sleep)

    tunnel.start()

    assert sleeps == [0.05]


def test_boundary_tunnel_start_reports_cli_status_code(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.stdout = '{"status_code":403}'

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)

    with pytest.raises(BoundaryTunnelError, match='Boundary tunnel CLI raised status code 403'):
        tunnel.start()


@pytest.mark.parametrize(
    'connection_details',
    [
        '{"credentials":[]}',
        '{"credentials":[{}]}',
    ],
)
def test_boundary_tunnel_start_reports_missing_credentials(monkeypatch: pytest.MonkeyPatch, connection_details: str) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.stdout = connection_details

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)

    with pytest.raises(BoundaryTunnelError, match='Boundary tunnel CLI did not return credentials'):
        tunnel.start()


def test_boundary_tunnel_start_reports_process_exit_before_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStdout:
        def readline(self) -> bytes:
            return b'{"error":"failed"}\n'

    class FakeProcess:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.returncode = 1
            self.stdout = FakeStdout()

        def poll(self) -> int:
            return 1

        def wait(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(boundary_tunnel.subprocess, 'Popen', FakeProcess)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(BoundaryTunnelError, match='exited before it was ready'):
        tunnel.start()


def test_boundary_tunnel_start_reports_process_exit_after_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._read_stdout()
        tunnel._output_ready.set()

    def fake_read_stdout() -> None:
        tunnel.stdout = CONNECTION_DETAILS
        tunnel._failed.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)
    monkeypatch.setattr(tunnel, '_read_stdout', fake_read_stdout)

    with pytest.raises(BoundaryTunnelError, match='exited before it was ready'):
        tunnel.start()


def test_boundary_tunnel_start_reports_startup_error_after_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._read_stdout()
        tunnel._output_ready.set()

    def fake_read_stdout() -> None:
        tunnel.stdout = CONNECTION_DETAILS
        tunnel._startup_error = OSError('boundary failed')
        tunnel._failed.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)
    monkeypatch.setattr(tunnel, '_read_stdout', fake_read_stdout)

    with pytest.raises(BoundaryTunnelError, match='Unable to start Boundary tunnel process: boundary failed') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, OSError)


def test_boundary_tunnel_start_reports_process_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError('missing boundary')

    monkeypatch.setattr(boundary_tunnel.subprocess, 'Popen', fail_popen)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(BoundaryTunnelError, match='Unable to start Boundary tunnel process: missing boundary') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_boundary_tunnel_start_reports_invalid_options() -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', boundary_options='"unterminated', local_port=4406)

    with pytest.raises(BoundaryTunnelError, match='Unable to start Boundary tunnel process: No closing quotation') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_boundary_tunnel_start_reports_process_start_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406, ready_timeout=0)
    monkeypatch.setattr(tunnel, '_run', lambda: None)

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for Boundary tunnel process to start'):
        tunnel.start()


def test_boundary_tunnel_start_reports_process_output_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    output_released = threading.Event()

    class BlockingStdout:
        def readline(self) -> bytes:
            calls.append('read')
            output_released.wait()
            return b''

    class FakeProcess:
        stdout = BlockingStdout()

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')
            output_released.set()

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            return 0

    monkeypatch.setattr(boundary_tunnel.subprocess, 'Popen', lambda *_args, **_kwargs: FakeProcess())
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406, ready_timeout=0.1)

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for Boundary tunnel process output'):
        tunnel.start()

    assert calls[:2] == ['read', 'terminate']
    assert sorted(calls[2:]) == ['wait:5', 'wait:None']


def test_boundary_tunnel_start_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.stdout = CONNECTION_DETAILS

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)
    monotonic_values = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(boundary_tunnel.time, 'monotonic', lambda: next(monotonic_values))

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for Boundary tunnel'):
        tunnel.start()


def test_boundary_tunnel_read_stdout_ignores_missing_process_or_stdout() -> None:
    class FakeProcess:
        stdout = None

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    tunnel._read_stdout()
    assert tunnel.stdout == ''

    tunnel.process = cast(Any, FakeProcess())
    tunnel._read_stdout()
    assert tunnel.stdout == ''


def test_boundary_tunnel_read_stdout_decodes_process_output() -> None:
    class FakeStdout:
        def readline(self) -> bytes:
            return CONNECTION_DETAILS.encode('utf-8')

    class FakeProcess:
        stdout = FakeStdout()

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.process = cast(Any, FakeProcess())

    tunnel._read_stdout()

    assert tunnel.stdout == CONNECTION_DETAILS


@pytest.mark.parametrize(
    ('return_code', 'ready', 'expected_failed'),
    [(0, False, False), (1, True, False), (1, False, True)],
)
def test_boundary_tunnel_run_tracks_process_status(
    monkeypatch: pytest.MonkeyPatch,
    return_code: int,
    ready: bool,
    expected_failed: bool,
) -> None:
    popen_calls: list[tuple[list[str], dict[str, Any]]] = []

    class FakeProcess:
        stdout = None

        def wait(self) -> int:
            return return_code

    def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
        popen_calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(boundary_tunnel.subprocess, 'Popen', fake_popen)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    if ready:
        tunnel._ready.set()

    tunnel._run()

    assert tunnel._started.is_set()
    assert tunnel._failed.is_set() is expected_failed
    assert popen_calls == [
        (
            tunnel.command(),
            {
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.DEVNULL,
                'start_new_session': True,
                'env': None,
            },
        )
    ]


def test_boundary_tunnel_close_terminates_running_process() -> None:
    calls: list[str] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            return 0

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5']


def test_boundary_tunnel_close_kills_process_after_terminate_timeout() -> None:
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
                raise subprocess.TimeoutExpired('boundary', timeout)
            return 0

        def kill(self) -> None:
            calls.append('kill')

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5', 'kill', 'wait:None']


def test_boundary_tunnel_close_joins_running_thread() -> None:
    calls: list[str] = []

    class FakeThread:
        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float | None = None) -> None:
            calls.append(f'join:{timeout}')

    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel._thread = cast(Any, FakeThread())

    tunnel.close()

    assert calls == ['join:5']


def test_boundary_tunnel_is_listening_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[str, int], float]] = []

    class FakeConnection:
        def __enter__(self) -> 'FakeConnection':
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

    def fake_create_connection(address: tuple[str, int], timeout: float) -> FakeConnection:
        calls.append((address, timeout))
        return FakeConnection()

    monkeypatch.setattr(boundary_tunnel.socket, 'create_connection', fake_create_connection)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    assert tunnel._is_listening() is True
    assert calls == [(('127.0.0.1', 4406), 0.05)]


def test_boundary_tunnel_is_listening_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_create_connection(*_args: Any, **_kwargs: Any) -> None:
        raise socket.timeout

    monkeypatch.setattr(boundary_tunnel.socket, 'create_connection', fail_create_connection)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)

    assert tunnel._is_listening() is False

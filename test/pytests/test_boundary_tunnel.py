from __future__ import annotations

from contextlib import nullcontext
from io import StringIO
import os
import socket
import subprocess
import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mycli import boundary_tunnel
from mycli.boundary_tunnel import (
    TUNNEL_STABILIZATION_PAUSE,
    BoundaryTunnel,
    BoundaryTunnelError,
)

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

    environment = tunnel._environment()

    assert environment is not None
    assert environment == dict(os.environ)


def test_boundary_tunnel_environment_sets_configured_auth_method(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('BOUNDARY_AUTH_METHOD_ID', 'ampw_parent')
    tunnel = BoundaryTunnel(target_id='ttcp_123', auth_method_id='ampw_config')

    environment = tunnel._environment()

    assert environment is not None
    assert environment['BOUNDARY_AUTH_METHOD_ID'] == 'ampw_config'
    assert os.environ['BOUNDARY_AUTH_METHOD_ID'] == 'ampw_parent'


def test_boundary_tunnel_environment_sets_configured_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('BOUNDARY_ADDR', 'https://parent.example.com')
    tunnel = BoundaryTunnel(target_id='ttcp_123', address='https://config.example.com')

    environment = tunnel._environment()

    assert environment is not None
    assert environment['BOUNDARY_ADDR'] == 'https://config.example.com'
    assert os.environ['BOUNDARY_ADDR'] == 'https://parent.example.com'


@pytest.mark.parametrize(
    ('test_command', 'auth_command'),
    [
        (None, 'boundary authenticate'),
        ('boundary authenticate status', None),
        ('', 'boundary authenticate'),
        ('boundary authenticate status', ''),
    ],
)
def test_boundary_tunnel_authentication_requires_both_commands(
    monkeypatch: pytest.MonkeyPatch,
    test_command: str | None,
    auth_command: str | None,
) -> None:
    monkeypatch.setattr(boundary_tunnel.subprocess, 'run', lambda *_args, **_kwargs: pytest.fail('unexpected command'))
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command=test_command,
        boundary_auth_command=auth_command,
        local_port=4406,
    )

    tunnel._authenticate_if_needed()


def test_boundary_tunnel_authentication_skips_auth_when_test_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(boundary_tunnel.subprocess, 'run', fake_run)
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        auth_method_id='ampw_123',
        boundary_test_command='boundary authenticate status -name "my auth"',
        boundary_auth_command='boundary authenticate password',
        local_port=4406,
    )

    tunnel._authenticate_if_needed()

    assert calls == [
        (
            ['boundary', 'authenticate', 'status', '-name', 'my auth'],
            {
                'check': False,
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.DEVNULL,
                'env': {**os.environ, 'BOUNDARY_AUTH_METHOD_ID': 'ampw_123'},
            },
        )
    ]


def test_boundary_tunnel_authentication_runs_auth_after_failed_test(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTerminal(StringIO):
        def __init__(self, responses: str) -> None:
            super().__init__(responses)
            self.output = StringIO()

        def write(self, value: str) -> int:
            return self.output.write(value)

        def flush(self) -> None:
            self.output.flush()

        def close(self) -> None:
            pass

    calls: list[tuple[list[str], dict[str, Any]]] = []
    return_codes = iter([1, 0])
    sql_input = StringIO('select 1;\n')
    redirected_error = StringIO()
    terminal = FakeTerminal('\n\n')
    opened_paths: list[tuple[str, str, str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=next(return_codes))

    def fake_open(path: str, mode: str, *, encoding: str) -> FakeTerminal:
        opened_paths.append((path, mode, encoding))
        return terminal

    monkeypatch.setattr(boundary_tunnel.subprocess, 'run', fake_run)
    monkeypatch.setattr(boundary_tunnel, 'WIN', False)
    monkeypatch.setattr(boundary_tunnel.sys, 'stdin', sql_input)
    monkeypatch.setattr(boundary_tunnel.sys, 'stderr', redirected_error)
    monkeypatch.setattr(boundary_tunnel, 'open', fake_open, raising=False)
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command='boundary authenticate status',
        boundary_auth_command='boundary authenticate password -login-name "Jane Doe"',
        local_port=4406,
    )

    tunnel._authenticate_if_needed()

    assert calls == [
        (
            ['boundary', 'authenticate', 'status'],
            {
                'check': False,
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.DEVNULL,
                'env': {**os.environ},
            },
        ),
        (
            ['boundary', 'authenticate', 'password', '-login-name', 'Jane Doe'],
            {
                'check': False,
                'stdin': terminal,
                'stdout': terminal,
                'stderr': terminal,
                'env': {**os.environ},
            },
        ),
    ]
    assert opened_paths == [('/dev/tty', 'r+', 'utf-8')]
    assert sql_input.read() == 'select 1;\n'
    assert redirected_error.getvalue() == ''
    assert terminal.output.getvalue() == (
        'Authenticate with Boundary before connecting? [Yn] Press return to continue after authenticating: '
    )


def test_boundary_tunnel_authentication_uses_tty_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal_input = StringIO('response\n')
    terminal_output = StringIO()
    monkeypatch.setattr(terminal_input, 'isatty', lambda: True)
    monkeypatch.setattr(terminal_output, 'isatty', lambda: True)
    monkeypatch.setattr(boundary_tunnel.sys, 'stdin', terminal_input)
    monkeypatch.setattr(boundary_tunnel.sys, 'stderr', terminal_output)

    with boundary_tunnel._authentication_terminal() as (authentication_input, authentication_output):
        assert authentication_input is terminal_input
        assert authentication_output is terminal_output


def test_boundary_tunnel_authentication_opens_windows_console(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal_input = StringIO('response\n')
    terminal_output = StringIO()
    opened_paths: list[tuple[str, str, str]] = []

    def fake_open(path: str, mode: str, *, encoding: str) -> StringIO:
        opened_paths.append((path, mode, encoding))
        return terminal_input if path == 'CONIN$' else terminal_output

    monkeypatch.setattr(boundary_tunnel, 'WIN', True)
    monkeypatch.setattr(boundary_tunnel.sys, 'stdin', StringIO())
    monkeypatch.setattr(boundary_tunnel.sys, 'stderr', StringIO())
    monkeypatch.setattr(boundary_tunnel, 'open', fake_open, raising=False)

    with boundary_tunnel._authentication_terminal() as (authentication_input, authentication_output):
        assert authentication_input is terminal_input
        assert authentication_output is terminal_output

    assert opened_paths == [
        ('CONIN$', 'r', 'utf-8'),
        ('CONOUT$', 'w', 'utf-8'),
    ]


def test_boundary_tunnel_authentication_reports_missing_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    sql_input = StringIO('select 1;\n')

    def fail_open(*_args: Any, **_kwargs: Any) -> None:
        raise OSError('no terminal')

    monkeypatch.setattr(boundary_tunnel.sys, 'stdin', sql_input)
    monkeypatch.setattr(boundary_tunnel.sys, 'stderr', StringIO())
    monkeypatch.setattr(boundary_tunnel, 'open', fail_open, raising=False)

    with pytest.raises(BoundaryTunnelError, match='Unable to open a terminal') as excinfo:
        with boundary_tunnel._authentication_terminal():
            pass

    assert isinstance(excinfo.value.__cause__, OSError)
    assert sql_input.read() == 'select 1;\n'


def test_boundary_tunnel_authentication_reports_terminal_eof() -> None:
    with pytest.raises(BoundaryTunnelError, match='Unable to read a response from the terminal'):
        boundary_tunnel._prompt_for_authentication(StringIO(), StringIO(), 'Prompt: ')


def test_boundary_tunnel_authentication_reports_declined_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        boundary_tunnel.subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr(
        boundary_tunnel,
        '_authentication_terminal',
        lambda: nullcontext((StringIO('n\n'), StringIO())),
    )
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command='boundary authenticate status',
        boundary_auth_command='boundary authenticate password',
        local_port=4406,
    )

    with pytest.raises(BoundaryTunnelError, match='Not authenticated'):
        tunnel._authenticate_if_needed()


@pytest.mark.parametrize(
    ('command', 'expected'),
    [
        (
            r'C:\boundary\boundary.exe authenticate status',
            [r'C:\boundary\boundary.exe', 'authenticate', 'status'],
        ),
        (
            r'"C:\Program Files\Boundary\boundary.exe" authenticate -name "Jane Doe"',
            [r'C:\Program Files\Boundary\boundary.exe', 'authenticate', '-name', 'Jane Doe'],
        ),
    ],
)
def test_boundary_tunnel_authentication_parses_windows_commands(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    expected: list[str],
) -> None:
    monkeypatch.setattr(boundary_tunnel, 'WIN', True)

    assert BoundaryTunnel._parse_authentication_command(command, 'test') == expected


def test_boundary_tunnel_authentication_reports_failed_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    return_codes = iter([1, 2])
    monkeypatch.setattr(
        boundary_tunnel.subprocess,
        'run',
        lambda *_args, **_kwargs: SimpleNamespace(returncode=next(return_codes)),
    )
    monkeypatch.setattr(
        boundary_tunnel,
        '_authentication_terminal',
        lambda: nullcontext((StringIO('\n'), StringIO())),
    )
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command='boundary authenticate status',
        boundary_auth_command='boundary authenticate password',
        local_port=4406,
    )

    with pytest.raises(BoundaryTunnelError, match='Authentication command exited with status 2'):
        tunnel._authenticate_if_needed()


@pytest.mark.parametrize(
    ('test_command', 'auth_command', 'error_match'),
    [
        ('"unterminated', 'boundary authenticate', 'Unable to parse test command'),
        ('   ', 'boundary authenticate', 'test command is empty'),
        ('boundary test', '"unterminated', 'Unable to parse authentication command'),
        ('boundary test', '   ', 'authentication command is empty'),
    ],
)
def test_boundary_tunnel_authentication_reports_invalid_commands(
    monkeypatch: pytest.MonkeyPatch,
    test_command: str,
    auth_command: str,
    error_match: str,
) -> None:
    monkeypatch.setattr(boundary_tunnel.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(returncode=1))
    monkeypatch.setattr(
        boundary_tunnel,
        '_authentication_terminal',
        lambda: nullcontext((StringIO('\n'), StringIO())),
    )
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command=test_command,
        boundary_auth_command=auth_command,
        local_port=4406,
    )

    with pytest.raises(BoundaryTunnelError, match=error_match):
        tunnel._authenticate_if_needed()


@pytest.mark.parametrize(
    ('return_codes', 'error_match'),
    [
        ([], 'Unable to run test command: command failed'),
        ([1], 'Unable to run authentication command: command failed'),
    ],
)
def test_boundary_tunnel_authentication_reports_process_errors(
    monkeypatch: pytest.MonkeyPatch,
    return_codes: list[int],
    error_match: str,
) -> None:
    remaining_codes = iter(return_codes)

    def fake_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        try:
            return SimpleNamespace(returncode=next(remaining_codes))
        except StopIteration:
            raise OSError('command failed') from None

    monkeypatch.setattr(boundary_tunnel.subprocess, 'run', fake_run)
    monkeypatch.setattr(
        boundary_tunnel,
        '_authentication_terminal',
        lambda: nullcontext((StringIO('\n'), StringIO())),
    )
    tunnel = BoundaryTunnel(
        target_id='ttcp_123',
        boundary_test_command='boundary authenticate status',
        boundary_auth_command='boundary authenticate password',
        local_port=4406,
    )

    with pytest.raises(BoundaryTunnelError, match=error_match) as excinfo:
        tunnel._authenticate_if_needed()

    assert isinstance(excinfo.value.__cause__, OSError)


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
    monkeypatch.setattr(boundary_tunnel.time, 'sleep', lambda _seconds: None)

    tunnel.start()

    assert read_threads == ['mycli-boundary-tunnel']
    assert tunnel.stdout == CONNECTION_DETAILS
    assert tunnel.username == '1234'
    assert tunnel.password == '5678'
    assert tunnel.expiry is not None


def test_boundary_tunnel_start_authenticates_before_starting_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.stdout = CONNECTION_DETAILS

    def fake_authenticate() -> None:
        calls.append('authenticate')

    def fake_run() -> None:
        calls.append('run')
        tunnel._started.set()
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_authenticate_if_needed', fake_authenticate)
    monkeypatch.setattr(tunnel, '_run', fake_run)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: True)
    monkeypatch.setattr(boundary_tunnel.time, 'sleep', lambda _seconds: None)

    tunnel.start()

    assert calls == ['authenticate', 'run']


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

    assert sleeps == [0.05, TUNNEL_STABILIZATION_PAUSE]


def test_boundary_tunnel_start_reports_cli_status_code(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    tunnel.stdout = '{"status_code":403}'

    def fake_run() -> None:
        tunnel._started.set()
        tunnel._output_ready.set()

    monkeypatch.setattr(tunnel, '_run', fake_run)

    with pytest.raises(BoundaryTunnelError, match='Tunnel CLI raised status code 403'):
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

    with pytest.raises(BoundaryTunnelError, match='Tunnel CLI did not return credentials'):
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

    with pytest.raises(BoundaryTunnelError, match='Unable to start tunnel process: boundary failed') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, OSError)


def test_boundary_tunnel_start_reports_process_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError('missing boundary')

    monkeypatch.setattr(boundary_tunnel.subprocess, 'Popen', fail_popen)
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406)
    monkeypatch.setattr(tunnel, '_is_listening', lambda: False)

    with pytest.raises(BoundaryTunnelError, match='Unable to start tunnel process: missing boundary') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_boundary_tunnel_start_reports_invalid_options() -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', boundary_options='"unterminated', local_port=4406)

    with pytest.raises(BoundaryTunnelError, match='Unable to start tunnel process: No closing quotation') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_boundary_tunnel_start_reports_process_start_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    tunnel = BoundaryTunnel(target_id='ttcp_123', local_port=4406, ready_timeout=0)
    monkeypatch.setattr(tunnel, '_run', lambda: None)

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for tunnel process to start'):
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

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for tunnel process output'):
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

    with pytest.raises(BoundaryTunnelError, match='Timed out waiting for tunnel'):
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
                'env': {**os.environ},
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

from __future__ import annotations

import subprocess
import tempfile
from typing import Any, cast

import pytest

from mycli import kubectl_tunnel
from mycli.kubectl_tunnel import KubectlTunnel, KubectlTunnelError


def test_split_options_handles_windows_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kubectl_tunnel, 'WIN', True)

    assert kubectl_tunnel._split_options('--context "prod cluster"') == ['--context', 'prod cluster']


def test_split_options_reports_invalid_quoting() -> None:
    with pytest.raises(KubectlTunnelError, match='Unable to parse kubectl options') as excinfo:
        kubectl_tunnel._split_options('--context "unterminated')

    assert isinstance(excinfo.value.__cause__, ValueError)


@pytest.mark.parametrize(
    ('resource', 'remote_port', 'message'),
    [
        ('', 3306, 'resource must not be empty'),
        ('   ', 3306, 'resource must not be empty'),
        ('service/mysql', 0, 'remote port must be an integer between'),
        ('service/mysql', 65536, 'remote port must be an integer between'),
    ],
)
def test_kubectl_tunnel_rejects_invalid_target(resource: str, remote_port: int, message: str) -> None:
    with pytest.raises(KubectlTunnelError, match=message):
        KubectlTunnel(resource=resource, remote_port=remote_port)


def test_command_combines_config_and_cli_options() -> None:
    tunnel = KubectlTunnel(
        resource='service/mysql',
        remote_port=3307,
        kubectl_executable='/opt/bin/kubectl',
        kubectl_config_options='--context prod --namespace database',
        kubectl_cli_options='--pod-running-timeout 20s',
    )

    assert tunnel.command() == [
        '/opt/bin/kubectl',
        'port-forward',
        '--context',
        'prod',
        '--namespace',
        'database',
        '--pod-running-timeout',
        '20s',
        '--address=127.0.0.1',
        'service/mysql',
        ':3307',
    ]


def test_start_waits_for_local_port(monkeypatch: pytest.MonkeyPatch) -> None:
    popen_calls: list[tuple[list[str], dict[str, Any]]] = []
    sleep_calls: list[float] = []

    class FakeProcess:
        def __init__(self, command: list[str], stdout: Any, **kwargs: Any) -> None:
            popen_calls.append((command, kwargs))

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(kubectl_tunnel.subprocess, 'Popen', FakeProcess)
    tunnel = KubectlTunnel(resource='service/mysql', remote_port=3306)

    def finish_startup(seconds: float) -> None:
        sleep_calls.append(seconds)
        assert tunnel._output_file is not None
        tunnel._output_file.write(b'Forwarding from 127.0.0.1:4406 -> 3306\n')

    monkeypatch.setattr(kubectl_tunnel.time, 'sleep', finish_startup)

    tunnel.start()
    tunnel.close()

    assert popen_calls[0][0] == [
        'kubectl',
        'port-forward',
        '--address=127.0.0.1',
        'service/mysql',
        ':3306',
    ]
    assert popen_calls[0][1]['stdin'] is subprocess.DEVNULL
    assert popen_calls[0][1]['stderr'] is not None
    assert popen_calls[0][1]['start_new_session'] is True
    assert sleep_calls == [0.05]
    assert tunnel.local_port == 4406


def test_start_reports_process_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError('missing kubectl')

    monkeypatch.setattr(kubectl_tunnel.subprocess, 'Popen', fail_popen)
    tunnel = KubectlTunnel(resource='service/mysql', remote_port=3306, local_port=4406)

    with pytest.raises(KubectlTunnelError, match='Unable to start kubectl port-forward process: missing kubectl') as excinfo:
        tunnel.start()

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)
    assert tunnel._output_file is None


def test_start_closes_output_after_invalid_options() -> None:
    tunnel = KubectlTunnel(
        resource='service/mysql',
        remote_port=3306,
        local_port=4406,
        kubectl_cli_options='"unterminated',
    )

    with pytest.raises(KubectlTunnelError, match='Unable to parse kubectl options'):
        tunnel.start()

    assert tunnel._output_file is None


def test_start_reports_process_output_on_early_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        def __init__(self, *_args: Any, stdout: Any, **_kwargs: Any) -> None:
            stdout.write(b'pods "mysql" not found\n')

        def poll(self) -> int:
            return 1

    monkeypatch.setattr(kubectl_tunnel.subprocess, 'Popen', FakeProcess)
    tunnel = KubectlTunnel(resource='pod/mysql', remote_port=3306, local_port=4406)

    with pytest.raises(KubectlTunnelError, match='exited with status 1: pods "mysql" not found'):
        tunnel.start()

    assert tunnel._output_file is None


def test_start_reports_timeout_with_process_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeProcess:
        def __init__(self, *_args: Any, stdout: Any, **_kwargs: Any) -> None:
            stdout.write(b'waiting for pod\n')

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append('terminate')

        def wait(self, timeout: float | None = None) -> int:
            calls.append(f'wait:{timeout}')
            return 0

    monkeypatch.setattr(kubectl_tunnel.subprocess, 'Popen', FakeProcess)
    tunnel = KubectlTunnel(resource='deployment/mysql', remote_port=3306, local_port=4406, ready_timeout=0)

    with pytest.raises(KubectlTunnelError, match='Timed out.*: waiting for pod'):
        tunnel.start()

    assert calls == ['terminate', 'wait:5']
    assert tunnel._output_file is None


def test_close_kills_process_after_terminate_timeout() -> None:
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
                raise subprocess.TimeoutExpired('kubectl', timeout)
            return 0

        def kill(self) -> None:
            calls.append('kill')

    tunnel = KubectlTunnel(resource='service/mysql', remote_port=3306, local_port=4406)
    tunnel.process = cast(Any, FakeProcess())

    tunnel.close()

    assert calls == ['terminate', 'wait:5', 'kill', 'wait:None']


def test_captured_output_is_empty_before_start() -> None:
    tunnel = KubectlTunnel(resource='service/mysql', remote_port=3306, local_port=4406)

    assert tunnel._captured_output() == ''


@pytest.mark.parametrize(
    ('output', 'expected'),
    [
        ('Forwarding from 127.0.0.1:4406 -> 3306', 4406),
        ('waiting for pod', None),
    ],
)
def test_forwarded_local_port(output: str, expected: int | None) -> None:
    tunnel = KubectlTunnel(resource='service/mysql', remote_port=3306, local_port=4406)
    with tempfile.TemporaryFile(mode='w+b') as output_file:
        output_file.write(output.encode())
        tunnel._output_file = output_file

        assert tunnel._forwarded_local_port() == expected

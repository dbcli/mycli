from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
import time
from typing import IO

from mycli.compat import WIN

DEFAULT_KUBECTL_EXECUTABLE = 'kubectl'
LOCAL_HOST = '127.0.0.1'


class KubectlTunnelError(RuntimeError):
    pass


def _split_options(options: str | None) -> list[str]:
    try:
        arguments = shlex.split(options or '', posix=not WIN)
    except ValueError as exc:
        raise KubectlTunnelError(f'Unable to parse kubectl options: {exc}') from exc
    if WIN:
        arguments = [
            argument[1:-1] if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in ('"', "'") else argument
            for argument in arguments
        ]
    return arguments


class KubectlTunnel:
    def __init__(
        self,
        *,
        resource: str,
        remote_port: int,
        kubectl_executable: str = DEFAULT_KUBECTL_EXECUTABLE,
        kubectl_config_options: str | None = None,
        kubectl_cli_options: str | None = None,
        local_port: int | None = None,
        ready_timeout: float = 30.0,
    ) -> None:
        if not resource.strip():
            raise KubectlTunnelError('Kubernetes resource must not be empty.')
        if not 1 <= remote_port <= 65535:
            raise KubectlTunnelError('Kubernetes remote port must be an integer between 1 and 65535.')
        self.resource = resource
        self.remote_port = remote_port
        self.kubectl_executable = kubectl_executable
        self.kubectl_config_options = kubectl_config_options
        self.kubectl_cli_options = kubectl_cli_options
        self.local_host = LOCAL_HOST
        self.local_port = local_port
        self.ready_timeout = ready_timeout
        self.process: subprocess.Popen | None = None
        self._output_file: IO[bytes] | None = None

    def command(self) -> list[str]:
        options = _split_options(self.kubectl_config_options)
        options.extend(_split_options(self.kubectl_cli_options))
        return [
            self.kubectl_executable,
            'port-forward',
            *options,
            f'--address={self.local_host}',
            self.resource,
            f'{self.local_port or ""}:{self.remote_port}',
        ]

    def start(self) -> None:
        self._output_file = tempfile.TemporaryFile(mode='w+b')
        try:
            self.process = subprocess.Popen(
                self.command(),
                stdin=subprocess.DEVNULL,
                stdout=self._output_file,
                stderr=self._output_file,
                start_new_session=True,
            )
        except KubectlTunnelError:
            self.close()
            raise
        except (OSError, ValueError) as exc:
            self.close()
            raise KubectlTunnelError(f'Unable to start kubectl port-forward process: {exc}') from exc

        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            return_code = self.process.poll()
            if return_code is not None:
                output = self._captured_output()
                self.close()
                detail = f': {output}' if output else ''
                raise KubectlTunnelError(f'kubectl port-forward exited with status {return_code}{detail}')
            if local_port := self._forwarded_local_port():
                self.local_port = local_port
                return
            time.sleep(0.05)

        output = self._captured_output()
        self.close()
        detail = f': {output}' if output else ''
        raise KubectlTunnelError(f'Timed out waiting for kubectl port-forward to become ready{detail}')

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if self._output_file is not None:
            self._output_file.close()
            self._output_file = None

    def _captured_output(self) -> str:
        if self._output_file is None:
            return ''
        self._output_file.seek(0)
        return self._output_file.read().decode('utf-8', errors='replace').strip()

    def _forwarded_local_port(self) -> int | None:
        match = re.search(rf'Forwarding from {re.escape(self.local_host)}:(\d+) ->', self._captured_output())
        return int(match.group(1)) if match else None

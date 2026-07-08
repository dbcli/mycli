from __future__ import annotations

from dataclasses import dataclass
import shlex
import socket
import subprocess
import threading
import time


class SshTunnelError(RuntimeError):
    pass


def _find_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


@dataclass(slots=True)
class SshTunnelTarget:
    ssh_target: str
    ssh_port: int | None = None

    @classmethod
    def parse(cls, value: str) -> SshTunnelTarget:
        target, separator, port = value.rpartition(':')
        if separator and port.isdigit() and ']' not in port:
            return cls(target, int(port))
        return cls(value, None)


class SshTunnel:
    def __init__(
        self,
        *,
        ssh_target: str,
        remote_host: str,
        remote_port: int,
        remote_socket: str | None = None,
        ssh_executable: str = 'ssh',
        ssh_options: str | None = None,
        ssh_port: int | None = None,
        local_port: int | None = None,
        ready_timeout: float = 30.0,
    ) -> None:
        self.ssh_executable = ssh_executable
        self.ssh_options = ssh_options
        self.ssh_target = ssh_target
        self.ssh_port = ssh_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.remote_socket = remote_socket
        self.local_host = '127.0.0.1'
        self.local_port = local_port or _find_free_local_port()
        self.ready_timeout = ready_timeout
        self.process: subprocess.Popen | None = None
        self._startup_error: OSError | None = None
        self._ready = threading.Event()
        self._failed = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_target(
        cls,
        ssh_jump_spec: str,
        *,
        remote_host: str,
        remote_port: int,
        remote_socket: str | None = None,
        ssh_executable: str = 'ssh',
        ssh_options: str | None = None,
    ) -> SshTunnel:
        target = SshTunnelTarget.parse(ssh_jump_spec)
        return cls(
            ssh_target=target.ssh_target,
            ssh_port=target.ssh_port,
            remote_host=remote_host,
            remote_port=remote_port,
            remote_socket=remote_socket,
            ssh_executable=ssh_executable,
            ssh_options=ssh_options,
        )

    def _forward_spec(self) -> str:
        if self.remote_socket:
            return f'{self.local_host}:{self.local_port}:{self.remote_socket}'
        return f'{self.local_host}:{self.local_port}:{self.remote_host}:{self.remote_port}'

    def command(self) -> list[str]:
        opts = shlex.split(self.ssh_options or '')
        command = [
            self.ssh_executable,
            *opts,
            '-N',
            '-L',
            self._forward_spec(),
        ]
        if self.ssh_port is not None:
            command.extend(['-p', str(self.ssh_port)])
        command.append(self.ssh_target)
        return command

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name='mycli-ssh-tunnel', daemon=True)
        self._thread.start()
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            if self._failed.is_set():
                self.close()
                if self._startup_error is not None:
                    raise SshTunnelError(f'Unable to start SSH tunnel process: {self._startup_error}') from self._startup_error
                raise SshTunnelError('SSH tunnel process exited before it was ready.')
            if self._is_listening():
                self._ready.set()
                return
            time.sleep(0.05)
        self.close()
        raise SshTunnelError('Timed out waiting for SSH tunnel to become ready.')

    def close(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            self.process = subprocess.Popen(
                self.command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._startup_error = exc
            self._failed.set()
            return
        return_code = self.process.wait()
        if return_code != 0 and not self._ready.is_set():
            self._failed.set()

    def _is_listening(self) -> bool:
        try:
            with socket.create_connection((self.local_host, self.local_port), timeout=0.05):
                return True
        except OSError:
            return False

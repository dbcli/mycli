from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
import socket
import subprocess
import tempfile
import threading
import time
from typing import Literal

from mycli.compat import WIN

DEFAULT_LOCALHOST = 'localhost'
DEFAULT_SSH_EXECUTABLE = 'ssh'
DEFAULT_TUNNEL_METHOD: Literal['auto', 'socket', 'port'] = 'auto'
MAX_UNIX_SOCKET_PATH_BYTES = 103


class SshTunnelError(RuntimeError):
    pass


def _find_free_local_port(local_host: str | None) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((local_host or DEFAULT_LOCALHOST, 0))
        return int(sock.getsockname()[1])


def _make_local_socket_path() -> str:
    fd, path = tempfile.mkstemp(prefix='mycli-ssh-', suffix='.sock')
    os.close(fd)
    os.unlink(path)
    _check_local_socket_path_limit(path)
    return path


def _check_local_socket_path_limit(path: str) -> None:
    path_bytes = len(os.fsencode(path))
    if path_bytes > MAX_UNIX_SOCKET_PATH_BYTES:
        raise SshTunnelError(
            f'Local SSH socket path is too long for sockaddr_un: {path_bytes} bytes > {MAX_UNIX_SOCKET_PATH_BYTES} bytes: {path}'
        )


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
        ssh_executable: str = DEFAULT_SSH_EXECUTABLE,
        ssh_config_options: str | None = None,
        ssh_cli_options: str | None = None,
        ssh_port: int | None = None,
        ready_timeout: float = 30.0,
        tunnel_method: Literal['auto', 'socket', 'port'] = DEFAULT_TUNNEL_METHOD,
    ) -> None:
        self.ssh_executable = ssh_executable
        self.ssh_config_options = ssh_config_options
        self.ssh_cli_options = ssh_cli_options
        self.ssh_target = ssh_target
        self.ssh_port = ssh_port
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.remote_socket = remote_socket
        self.tunnel_method = tunnel_method
        if tunnel_method == 'auto':
            self.true_tunnel_method: Literal['socket', 'port'] = 'port' if WIN else 'socket'
        else:
            self.true_tunnel_method = tunnel_method
        self.local_socket = _make_local_socket_path() if self.true_tunnel_method == 'socket' else None
        self.local_host = DEFAULT_LOCALHOST if self.true_tunnel_method == 'port' else None
        self.local_port = _find_free_local_port(self.local_host) if self.true_tunnel_method == 'port' else None
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
        ssh_executable: str = DEFAULT_SSH_EXECUTABLE,
        ssh_config_options: str | None = None,
        ssh_cli_options: str | None = None,
        tunnel_method: Literal['auto', 'socket', 'port'] = DEFAULT_TUNNEL_METHOD,
    ) -> SshTunnel:
        target = SshTunnelTarget.parse(ssh_jump_spec)
        return cls(
            ssh_target=target.ssh_target,
            ssh_port=target.ssh_port,
            remote_host=remote_host,
            remote_port=remote_port,
            remote_socket=remote_socket,
            ssh_executable=ssh_executable,
            ssh_config_options=ssh_config_options,
            ssh_cli_options=ssh_cli_options,
            tunnel_method=tunnel_method,
        )

    def _forward_spec(self) -> str:
        if self.local_socket:
            if self.remote_socket:
                return f'{self.local_socket}:{self.remote_socket}'
            return f'{self.local_socket}:{self.remote_host}:{self.remote_port}'
        else:
            if self.remote_socket:
                return f'{self.local_host}:{self.local_port}:{self.remote_socket}'
            return f'{self.local_host}:{self.local_port}:{self.remote_host}:{self.remote_port}'

    def command(self) -> list[str]:
        opts = shlex.split(self.ssh_config_options or '')
        opts.extend(shlex.split(self.ssh_cli_options or ''))
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
        try:
            if self.local_socket:
                os.unlink(self.local_socket)
        except FileNotFoundError:
            pass

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
            if self.local_socket:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.05)
                    sock.connect(self.local_socket)
                    return True
            elif self.local_host and self.local_port:
                with socket.create_connection((self.local_host, self.local_port), timeout=0.05):
                    return True
            else:
                return False
        except OSError:
            return False

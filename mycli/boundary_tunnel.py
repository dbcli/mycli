from __future__ import annotations

import datetime
import json
import os
import shlex
import socket
import subprocess
import threading
import time


class BoundaryTunnelError(RuntimeError):
    pass


def _find_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


class BoundaryTunnel:
    def __init__(
        self,
        *,
        target_id: str,
        boundary_executable: str = 'boundary',
        address: str | None = None,
        auth_method_id: str | None = None,
        boundary_options: str | None = None,
        local_port: int | None = None,
        ready_timeout: float = 30.0,
    ) -> None:
        self.target_id = target_id
        self.boundary_executable = boundary_executable
        self.address = address
        self.auth_method_id = auth_method_id
        self.boundary_options = boundary_options
        self.local_host = '127.0.0.1'
        self.local_port = local_port or _find_free_local_port()
        self.ready_timeout = ready_timeout
        self.process: subprocess.Popen | None = None
        self.stdout = ''
        self._startup_error: OSError | ValueError | None = None
        self._started = threading.Event()
        self._output_ready = threading.Event()
        self._ready = threading.Event()
        self._failed = threading.Event()
        self._thread: threading.Thread | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.expiry: str | None = None

    def command(self) -> list[str]:
        options = shlex.split(self.boundary_options or '')
        command = [
            self.boundary_executable,
            'connect',
            *options,
            f'-target-id={self.target_id}',
            f'-listen-addr={self.local_host}',
            f'-listen-port={self.local_port}',
            '-format=json',
        ]
        if self.address:
            command.append(f'-addr={self.address}')
        return command

    def start(self, *, show_expiration_warning: bool = True) -> None:
        self._thread = threading.Thread(target=self._run, name='mycli-boundary-tunnel', daemon=True)
        self._thread.start()
        deadline = time.monotonic() + self.ready_timeout
        while time.monotonic() < deadline:
            self._raise_if_failed()
            if self._started.is_set():
                break
            time.sleep(0.05)
        else:
            self.close()
            raise BoundaryTunnelError('Timed out waiting for Boundary tunnel process to start.')

        while time.monotonic() < deadline:
            self._raise_if_failed()
            if self._output_ready.is_set():
                break
            time.sleep(0.05)
        else:
            self.close()
            raise BoundaryTunnelError('Timed out waiting for Boundary tunnel process output.')

        connection_details = json.loads(self.stdout)
        self.username = connection_details['credentials'][0]['secret']['decoded']['username']
        self.password = connection_details['credentials'][0]['secret']['decoded']['password']
        expiry_raw = connection_details['expiration']
        expiry_utc = datetime.datetime.strptime(expiry_raw, '%Y-%m-%dT%H:%M:%S.%f%z')
        expiry_local = datetime.datetime.fromtimestamp(expiry_utc.timestamp())
        self.expiry = datetime.datetime.strftime(expiry_local, '%H:%M:%S %a %d %b %Y')

        while time.monotonic() < deadline:
            self._raise_if_failed()
            if self._is_listening():
                self._ready.set()
                return
            time.sleep(0.05)
        self.close()
        raise BoundaryTunnelError('Timed out waiting for Boundary tunnel to become ready.')

    def _raise_if_failed(self) -> None:
        if not self._failed.is_set():
            return
        self.close()
        if self._startup_error is not None:
            raise BoundaryTunnelError(f'Unable to start Boundary tunnel process: {self._startup_error}') from self._startup_error
        raise BoundaryTunnelError('Boundary tunnel process exited before it was ready.')

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        self.stdout = process.stdout.readline().decode('utf-8')

    def _environment(self) -> dict[str, str] | None:
        if not self.auth_method_id:
            return None
        environment = os.environ.copy()
        environment['BOUNDARY_AUTH_METHOD_ID'] = self.auth_method_id
        return environment

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
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=self._environment(),
            )
            self._started.set()
            self._read_stdout()
            self._output_ready.set()
        except (OSError, ValueError) as exc:
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

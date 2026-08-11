from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
import datetime
import json
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
from typing import IO

from mycli.compat import WIN

TUNNEL_STABILIZATION_PAUSE = 0.25


class BoundaryTunnelError(RuntimeError):
    pass


def _find_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


@contextmanager
def _authentication_terminal() -> Iterator[tuple[IO[str], IO[str]]]:
    if sys.stdin.isatty() and sys.stderr.isatty():
        yield sys.stdin, sys.stderr
        return

    with ExitStack() as stack:
        try:
            if WIN:
                terminal_input = stack.enter_context(open('CONIN$', 'r', encoding='utf-8'))
                terminal_output = stack.enter_context(open('CONOUT$', 'w', encoding='utf-8'))
            else:
                terminal_input = terminal_output = stack.enter_context(open('/dev/tty', 'r+', encoding='utf-8'))
        except OSError as exc:
            raise BoundaryTunnelError('Unable to open a terminal for Boundary authentication.') from exc
        yield terminal_input, terminal_output


def _prompt_for_authentication(terminal_input: IO[str], terminal_output: IO[str], prompt: str) -> str:
    print(prompt, file=terminal_output, end='', flush=True)
    response = terminal_input.readline()
    if not response:
        raise BoundaryTunnelError('Unable to read a response from the terminal.')
    return response.rstrip('\r\n')


class BoundaryTunnel:
    def __init__(
        self,
        *,
        target_id: str,
        boundary_executable: str = 'boundary',
        address: str | None = None,
        auth_method_id: str | None = None,
        boundary_options: str | None = None,
        boundary_test_command: str | None = None,
        boundary_auth_command: str | None = None,
        local_port: int | None = None,
        ready_timeout: float = 30.0,
    ) -> None:
        self.target_id = target_id
        self.boundary_executable = boundary_executable
        self.address = address
        self.auth_method_id = auth_method_id
        self.boundary_options = boundary_options
        self.boundary_test_command = boundary_test_command
        self.boundary_auth_command = boundary_auth_command
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
        self._authenticate_if_needed()
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
            raise BoundaryTunnelError('Timed out waiting for tunnel process to start.')

        while time.monotonic() < deadline:
            self._raise_if_failed()
            if self._output_ready.is_set():
                break
            time.sleep(0.05)
        else:
            self.close()
            raise BoundaryTunnelError('Timed out waiting for tunnel process output.')

        connection_details = json.loads(self.stdout)

        if 'status_code' in connection_details:
            raise BoundaryTunnelError(f'Tunnel CLI raised status code {connection_details["status_code"]}.')

        try:
            self.username = connection_details['credentials'][0]['secret']['decoded']['username']
            self.password = connection_details['credentials'][0]['secret']['decoded']['password']
        except (IndexError, KeyError):
            raise BoundaryTunnelError('Tunnel CLI did not return credentials.') from None

        expiry_raw = connection_details['expiration']
        expiry_utc = datetime.datetime.strptime(expiry_raw, '%Y-%m-%dT%H:%M:%S.%f%z')
        expiry_local = datetime.datetime.fromtimestamp(expiry_utc.timestamp())
        self.expiry = datetime.datetime.strftime(expiry_local, '%H:%M:%S %a %d %b %Y')

        while time.monotonic() < deadline:
            self._raise_if_failed()
            if self._is_listening():
                self._ready.set()
                # todo: if this works to ward off SSL errors at connection time,
                # try making the pause as small as possible
                time.sleep(TUNNEL_STABILIZATION_PAUSE)
                return
            time.sleep(0.05)
        self.close()
        raise BoundaryTunnelError('Timed out waiting for tunnel to become ready.')

    def _raise_if_failed(self) -> None:
        if not self._failed.is_set():
            return
        self.close()
        if self._startup_error is not None:
            raise BoundaryTunnelError(f'Unable to start tunnel process: {self._startup_error}') from self._startup_error
        raise BoundaryTunnelError('Tunnel process exited before it was ready.')

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        self.stdout = process.stdout.readline().decode('utf-8')

    def _environment(self) -> dict[str, str] | None:
        environment = os.environ.copy()
        if self.auth_method_id:
            environment['BOUNDARY_AUTH_METHOD_ID'] = self.auth_method_id
        if self.address:
            environment['BOUNDARY_ADDR'] = self.address
        return environment

    def _authenticate_if_needed(self) -> None:
        if not self.boundary_test_command or not self.boundary_auth_command:
            return

        test_command = self._parse_authentication_command(self.boundary_test_command, 'test')
        try:
            completed_process = subprocess.run(
                test_command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._environment(),
            )
        except OSError as exc:
            raise BoundaryTunnelError(f'Unable to run test command: {exc}') from exc
        if completed_process.returncode == 0:
            return

        with _authentication_terminal() as (terminal_input, terminal_output):
            yn = _prompt_for_authentication(
                terminal_input,
                terminal_output,
                'Authenticate with Boundary before connecting? [Yn] ',
            ).lower()
            if yn not in ('y', ''):
                raise BoundaryTunnelError('Not authenticated.')

            auth_command = self._parse_authentication_command(self.boundary_auth_command, 'authentication')
            try:
                completed_process = subprocess.run(
                    auth_command,
                    check=False,
                    stdin=terminal_input,
                    stdout=terminal_output,
                    stderr=terminal_output,
                    env=self._environment(),
                )
            except OSError as exc:
                raise BoundaryTunnelError(f'Unable to run authentication command: {exc}') from exc
            if completed_process.returncode != 0:
                raise BoundaryTunnelError(f'Authentication command exited with status {completed_process.returncode}.')

            _prompt_for_authentication(
                terminal_input,
                terminal_output,
                'Press return to continue after authenticating: ',
            )

    @staticmethod
    def _parse_authentication_command(command: str, name: str) -> list[str]:
        try:
            arguments = shlex.split(command, posix=not WIN)
        except ValueError as exc:
            raise BoundaryTunnelError(f'Unable to parse {name} command: {exc}') from exc
        if WIN:
            arguments = [
                argument[1:-1] if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in ('"', "'") else argument
                for argument in arguments
            ]
        if not arguments:
            raise BoundaryTunnelError(f'{name} command is empty.')
        return arguments

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

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, cast

import pexpect

FEATURES_DIR = Path(__file__).resolve().parents[1] / 'features'
sys.path.append(str(FEATURES_DIR))

environment_spec = importlib.util.spec_from_file_location('feature_environment', FEATURES_DIR / 'environment.py')
assert environment_spec is not None
assert environment_spec.loader is not None
environment_module = importlib.util.module_from_spec(environment_spec)
environment_spec.loader.exec_module(environment_module)
environment = cast(Any, environment_module)


class TimeoutOnEofCli:
    def __init__(self) -> None:
        self.sent_controls: list[str] = []
        self.terminated_force: bool | None = None

    def sendcontrol(self, key: str) -> None:
        self.sent_controls.append(key)

    def expect_exact(self, expected: object, timeout: int) -> None:
        if expected == pexpect.EOF:
            raise pexpect.TIMEOUT('process still running')

        raise AssertionError(f'unexpected expectation: {expected!r}')

    def terminate(self, force: bool = False) -> None:
        self.terminated_force = force


def test_after_scenario_terminates_when_teardown_eof_times_out(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / 'mycli.test.log'
    log_file.write_text('')
    monkeypatch.setattr(environment, 'test_log_file', str(log_file))
    monkeypatch.setattr(environment, 'MY_CNF_BACKUP_PATH', str(tmp_path / '.my.cnf.backup'))
    monkeypatch.setattr(environment, 'MYLOGIN_CNF_BACKUP_PATH', str(tmp_path / '.mylogin.cnf.backup'))
    monkeypatch.setattr(environment, 'MYLOGIN_CNF_PATH', str(tmp_path / '.mylogin.cnf'))

    cli = TimeoutOnEofCli()
    context = SimpleNamespace(
        atprompt=True,
        cli=cli,
        exit_sent=False,
    )

    environment.after_scenario(context, SimpleNamespace())

    assert cli.sent_controls == ['c', 'd']
    assert cli.terminated_force is True

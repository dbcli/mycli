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


class PromptRaceCli:
    def __init__(self) -> None:
        self.interrupt_prompt_seen = False
        self.closed = False

    def expect_exact(self, expected: object, timeout: int) -> None:
        if expected == pexpect.EOF:
            if not self.closed:
                raise pexpect.TIMEOUT('process still running')
            return

        if expected == 'root@127.0.0.1:mycli_behave_tests>':
            self.interrupt_prompt_seen = True
            return

        raise AssertionError(f'unexpected expectation: {expected!r}')

    def sendcontrol(self, key: str) -> None:
        if key == 'c':
            return
        if key == 'd':
            self.closed = self.interrupt_prompt_seen


def test_after_scenario_waits_for_prompt_after_interrupt(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / 'mycli.test.log'
    log_file.write_text('')
    monkeypatch.setattr(environment, 'test_log_file', str(log_file))
    monkeypatch.setattr(environment, 'MY_CNF_BACKUP_PATH', str(tmp_path / '.my.cnf.backup'))
    monkeypatch.setattr(environment, 'MYLOGIN_CNF_BACKUP_PATH', str(tmp_path / '.mylogin.cnf.backup'))
    monkeypatch.setattr(environment, 'MYLOGIN_CNF_PATH', str(tmp_path / '.mylogin.cnf'))

    context = SimpleNamespace(
        atprompt=True,
        cli=PromptRaceCli(),
        conf={
            'user': 'root',
            'host': '127.0.0.1',
            'dbname': 'mycli_behave_tests',
        },
        currentdb='mycli_behave_tests',
        exit_sent=False,
    )

    environment.after_scenario(context, SimpleNamespace())

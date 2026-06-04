import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, cast

FEATURE_STEPS_DIR = Path(__file__).resolve().parents[1] / 'features' / 'steps'
sys.path.append(str(FEATURE_STEPS_DIR))

iocommands_spec = importlib.util.spec_from_file_location('feature_iocommands', FEATURE_STEPS_DIR / 'iocommands.py')
assert iocommands_spec is not None
assert iocommands_spec.loader is not None
iocommands_module = importlib.util.module_from_spec(iocommands_spec)
iocommands_spec.loader.exec_module(iocommands_module)
iocommands = cast(Any, iocommands_module)


class FakeCli:
    def __init__(self) -> None:
        self.sent_controls: list[str] = []

    def sendcontrol(self, key: str) -> None:
        self.sent_controls.append(key)


def test_external_editor_prompt_cleanup_waits_for_prompt(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []

    def expect_exact(context: object, expected: object, timeout: int) -> None:
        calls.append(('expect', expected))

    def wait_prompt(context: object) -> None:
        calls.append(('wait_prompt', None))

    monkeypatch.setattr(iocommands.wrappers, 'expect_exact', expect_exact)
    monkeypatch.setattr(iocommands.wrappers, 'wait_prompt', wait_prompt)

    editor_file = tmp_path / 'query.sql'
    editor_file.write_text('select * from abc')
    context = SimpleNamespace(cli=FakeCli(), editor_file_name=str(editor_file))

    iocommands.step_edit_done_sql(context, 'select * from abc')

    assert calls == [
        ('expect', 'select'),
        ('expect', '*'),
        ('expect', 'from'),
        ('expect', 'abc'),
        ('wait_prompt', None),
    ]
    assert context.cli.sent_controls == ['c']
    assert not editor_file.exists()

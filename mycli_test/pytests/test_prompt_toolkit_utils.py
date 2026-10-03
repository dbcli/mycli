from dataclasses import dataclass, field
from typing import Any, cast

from mycli.packages.prompt_toolkit import utils as prompt_toolkit_utils


@dataclass
class DummyApp:
    print_calls: list[str] = field(default_factory=list)

    def print_text(self, text: str) -> None:
        self.print_calls.append(text)


def test_safe_invalidate_display_runs_empty_terminal_print(monkeypatch) -> None:
    app = DummyApp()
    callbacks: list[object] = []

    def fake_run_in_terminal(callback) -> None:
        callbacks.append(callback)
        callback()

    monkeypatch.setattr(prompt_toolkit_utils, 'run_in_terminal', fake_run_in_terminal)

    prompt_toolkit_utils.safe_invalidate_display(cast(Any, app))

    assert len(callbacks) == 1
    assert app.print_calls == ['']


def test_safe_invalidate_display_swallows_runtime_error(monkeypatch) -> None:
    app = DummyApp()

    def fail_run_in_terminal(_callback) -> None:
        raise RuntimeError('application is exiting')

    monkeypatch.setattr(prompt_toolkit_utils, 'run_in_terminal', fail_run_in_terminal)

    prompt_toolkit_utils.safe_invalidate_display(cast(Any, app))

    assert app.print_calls == []

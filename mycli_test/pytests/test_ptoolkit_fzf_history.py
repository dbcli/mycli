from types import SimpleNamespace
from typing import Any, cast

import pytest

from mycli.packages.integrations.fzf import fzf as fzf_wrapper
from mycli.packages.prompt_toolkit import fzf_history as fzf_module
from mycli.packages.prompt_toolkit.history import FileHistoryWithTimestamp


class DummyHistory(FileHistoryWithTimestamp):
    def __init__(self, items: list[tuple[str, str]]) -> None:
        self._items = items

    def load_history_with_timestamp(self) -> list[tuple[str, str]]:
        return self._items


def make_event(history: Any) -> SimpleNamespace:
    buffer = SimpleNamespace(history=history, text='original', cursor_position=0)
    return SimpleNamespace(
        current_buffer=buffer,
        app=SimpleNamespace(),
    )


@pytest.mark.parametrize('available', [True, False])
def test_fzf_init_and_is_available(monkeypatch: pytest.MonkeyPatch, available: bool) -> None:
    monkeypatch.setattr(fzf_wrapper, 'which', lambda executable: '/usr/bin/fzf' if available and executable == 'fzf' else None)

    fzf = fzf_module.Fzf()

    assert fzf.executable == ('fzf' if available else None)
    assert fzf.is_available() is available


def test_search_history_falls_back_to_prompt_toolkit_search(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    event = make_event(history=object())

    monkeypatch.setattr(
        fzf_module.search,
        'start_search',
        lambda **kwargs: calls.append(kwargs),
    )

    fzf_module.search_history(cast(Any, event), incremental=True)

    assert calls == [{'direction': fzf_module.search.SearchDirection.BACKWARD}]


def test_search_history_falls_back_when_fzf_unavailable_or_history_type_is_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    unavailable_event = make_event(history=DummyHistory([]))
    wrong_history_event = make_event(history=[])

    class UnavailableFzf:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(
        fzf_module.search,
        'start_search',
        lambda **kwargs: calls.append(kwargs),
    )

    monkeypatch.setattr(fzf_module, 'Fzf', UnavailableFzf)
    fzf_module.search_history(cast(Any, unavailable_event))

    class AvailableFzf:
        def is_available(self) -> bool:
            return True

    monkeypatch.setattr(fzf_module, 'Fzf', AvailableFzf)
    fzf_module.search_history(cast(Any, wrong_history_event))

    assert calls == [
        {'direction': fzf_module.search.SearchDirection.BACKWARD},
        {'direction': fzf_module.search.SearchDirection.BACKWARD},
    ]


def test_search_history_formats_preview_updates_buffer_and_deduplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt_calls: list[dict[str, Any]] = []
    invalidated_apps: list[Any] = []

    history = DummyHistory([
        ('SELECT  1\nFROM dual', '2026-01-02 03:04:05.678'),
        ('SELECT 1 FROM dual', '2026-01-01 00:00:00'),
        ('SELECT 2', '2026-01-03 12:00:00'),
    ])
    event = make_event(history=history)

    class PromptingFzf:
        def is_available(self) -> bool:
            return True

        def prompt(self, items: list[str], options: list[str]) -> str:
            prompt_calls.append({'items': items, 'options': options})
            return items[0]

    monkeypatch.setattr(fzf_module, 'Fzf', PromptingFzf)
    monkeypatch.setattr(
        fzf_module,
        'which',
        lambda executable: '/usr/bin/pygmentize' if executable == 'pygmentize' else None,
    )
    monkeypatch.setattr(fzf_module, 'safe_invalidate_display', lambda app: invalidated_apps.append(app))

    fzf_module.search_history(
        cast(Any, event),
        highlight_preview=True,
        highlight_style='monokai style',
    )

    assert prompt_calls == [
        {
            'items': [
                '2026-01-02 03:04:05  SELECT 1 FROM dual',
                '2026-01-03 12:00:00  SELECT 2',
            ],
            'options': [
                '--info=hidden',
                '--scheme=history',
                '--tiebreak=index',
                '--bind=ctrl-r:up,alt-r:up',
                '--preview-window=down:wrap:nohidden',
                '--no-height',
                "--preview=printf '%s' {} | pygmentize -l mysql -P style='monokai style'",
            ],
        }
    ]
    assert invalidated_apps == [event.app]
    assert event.current_buffer.text == 'SELECT  1\nFROM dual'
    assert event.current_buffer.cursor_position == len('SELECT  1\nFROM dual')


@pytest.mark.parametrize(
    ("highlight_preview", "pygmentize_available"),
    [
        (False, False),
        (False, True),
        (True, False),
    ],
)
def test_search_history_without_result_keeps_buffer_and_uses_plain_preview(
    monkeypatch: pytest.MonkeyPatch,
    highlight_preview: bool,
    pygmentize_available: bool,
) -> None:
    prompt_calls: list[dict[str, Any]] = []
    invalidated_apps: list[Any] = []

    event = make_event(history=DummyHistory([('SELECT 1', '2026-01-01 00:00:00')]))

    class PromptingFzf:
        def is_available(self) -> bool:
            return True

        def prompt(self, items: list[str], options: list[str]) -> None:
            prompt_calls.append({'items': items, 'options': options})
            return None

    monkeypatch.setattr(fzf_module, 'Fzf', PromptingFzf)
    monkeypatch.setattr(
        fzf_module,
        'which',
        lambda executable: '/usr/bin/pygmentize' if pygmentize_available and executable == 'pygmentize' else None,
    )
    monkeypatch.setattr(fzf_module, 'safe_invalidate_display', lambda app: invalidated_apps.append(app))

    fzf_module.search_history(cast(Any, event), highlight_preview=highlight_preview)

    assert prompt_calls == [
        {
            'items': ['2026-01-01 00:00:00  SELECT 1'],
            'options': [
                '--info=hidden',
                '--scheme=history',
                '--tiebreak=index',
                '--bind=ctrl-r:up,alt-r:up',
                '--preview-window=down:wrap:nohidden',
                '--no-height',
                "--preview=printf '%s' {}",
            ],
        }
    ]
    assert invalidated_apps == [event.app]
    assert event.current_buffer.text == 'original'
    assert event.current_buffer.cursor_position == 0

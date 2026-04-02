from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, cast

import prompt_toolkit
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import BufferControl, SearchBufferControl
from prompt_toolkit.selection import SelectionType
import pytest

from mycli import key_bindings


@dataclass
class DummyKeysConfig:
    behaviors: dict[str, list[str]] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)

    def as_list(self, name: str) -> list[str]:
        return self.behaviors[name]

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.options.get(name, default)


@dataclass
class DummyOutput:
    bell_calls: int = 0

    def bell(self) -> None:
        self.bell_calls += 1


@dataclass
class DummyBuffer:
    text: str = ''
    complete_state: object | None = None
    complete_next_calls: int = 0
    cancel_completion_calls: int = 0
    start_completion_calls: list[dict[str, bool]] = field(default_factory=list)
    start_selection_calls: list[SelectionType] = field(default_factory=list)
    transform_calls: list[tuple[int, int, Callable[[str], str]]] = field(default_factory=list)
    inserted_text: list[str] = field(default_factory=list)
    validate_calls: int = 0

    def complete_next(self) -> None:
        self.complete_next_calls += 1

    def start_completion(
        self,
        select_first: bool = False,
        insert_common_part: bool = False,
    ) -> None:
        self.start_completion_calls.append({
            'select_first': select_first,
            'insert_common_part': insert_common_part,
        })
        self.complete_state = object()

    def cancel_completion(self) -> None:
        self.cancel_completion_calls += 1
        self.complete_state = None

    def start_selection(self, selection_type: SelectionType) -> None:
        self.start_selection_calls.append(selection_type)

    def transform_region(self, start: int, end: int, handler: Callable[[str], str]) -> None:
        self.transform_calls.append((start, end, handler))

    def insert_text(self, text: str) -> None:
        self.inserted_text.append(text)

    def validate_and_handle(self) -> None:
        self.validate_calls += 1


@dataclass
class DummyApp:
    current_buffer: DummyBuffer
    editing_mode: EditingMode = EditingMode.VI
    ttimeoutlen: float | None = None
    output: DummyOutput = field(default_factory=DummyOutput)
    exit_calls: list[dict[str, Any]] = field(default_factory=list)
    print_calls: list[Any] = field(default_factory=list)

    def exit(self, exception: type[BaseException], style: str) -> None:
        self.exit_calls.append({'exception': exception, 'style': style})

    def print_text(self, text: Any) -> None:
        self.print_calls.append(text)


@dataclass
class DummyMyCli:
    key_config: DummyKeysConfig
    smart_completion: bool = True
    multi_line: bool = False
    key_bindings_mode: str = 'vi'
    highlight_preview: bool = True
    syntax_style: str = 'native'
    emacs_ttimeoutlen: float = 1.5
    vi_ttimeoutlen: float = 0.5
    sqlexecute: object = field(default_factory=object)
    prettify_calls: list[str] = field(default_factory=list)
    unprettify_calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.completer = SimpleNamespace(smart_completion=self.smart_completion)
        self.key_bindings = self.key_bindings_mode
        self.config = {'keys': self.key_config}

    def handle_prettify_binding(self, text: str) -> str:
        self.prettify_calls.append(text)
        return text

    def handle_unprettify_binding(self, text: str) -> str:
        self.unprettify_calls.append(text)
        return text


def make_event(buffer: DummyBuffer | None = None) -> SimpleNamespace:
    active_buffer = buffer or DummyBuffer()
    app = DummyApp(current_buffer=active_buffer)
    return SimpleNamespace(app=app, current_buffer=active_buffer)


def binding_handler(kb: prompt_toolkit.key_binding.KeyBindings, *keys: str | Keys) -> Callable[[Any], None]:
    expected = tuple(keys)
    for binding in kb.bindings:
        if binding.keys == expected:
            return cast(Callable[[Any], None], binding.handler)
    raise AssertionError(f'binding not found for keys={expected!r}')


def binding_filter(kb: prompt_toolkit.key_binding.KeyBindings, *keys: str | Keys) -> Any:
    expected = tuple(keys)
    for binding in kb.bindings:
        if binding.keys == expected:
            return binding.filter
    raise AssertionError(f'binding not found for keys={expected!r}')


def binding(kb: prompt_toolkit.key_binding.KeyBindings, *keys: str | Keys) -> Any:
    expected = tuple(keys)
    for entry in kb.bindings:
        if entry.keys == expected:
            return entry
    raise AssertionError(f'binding not found for keys={expected!r}')


def patch_filter_app(monkeypatch, app: DummyApp) -> None:
    monkeypatch.setitem(key_bindings.emacs_mode.func.__globals__, 'get_app', lambda: app)
    monkeypatch.setitem(key_bindings.completion_is_selected.func.__globals__, 'get_app', lambda: app)
    monkeypatch.setitem(key_bindings.control_is_searchable.func.__globals__, 'get_app', lambda: app)


def test_ctrl_d_condition_depends_on_empty_buffer(monkeypatch) -> None:
    monkeypatch.setattr(key_bindings, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='')))
    assert key_bindings.ctrl_d_condition() is True

    monkeypatch.setattr(key_bindings, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(text='select 1')))
    assert key_bindings.ctrl_d_condition() is False


def test_in_completion_depends_on_complete_state(monkeypatch) -> None:
    monkeypatch.setattr(key_bindings, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(complete_state=object())))
    assert key_bindings.in_completion() is True

    monkeypatch.setattr(key_bindings, 'get_app', lambda: SimpleNamespace(current_buffer=SimpleNamespace(complete_state=None)))
    assert key_bindings.in_completion() is False


def test_print_f1_help_prints_inline_help_and_docs_url(monkeypatch) -> None:
    app = DummyApp(current_buffer=DummyBuffer())
    monkeypatch.setattr(key_bindings, 'get_app', lambda: app)

    key_bindings.print_f1_help()

    assert app.print_calls == [
        '\n',
        [
            ('', 'Inline help — type "'),
            ('bold', 'help'),
            ('', '" or "'),
            ('bold', r'\?'),
            ('', '"\n'),
        ],
        [
            ('', 'Docs index — '),
            ('bold', key_bindings.DOCS_URL),
            ('', '\n'),
        ],
        '\n',
    ]


@pytest.mark.parametrize('keys', ((Keys.F1,), (Keys.Escape, '[', 'P')))
def test_f1_bindings_open_docs_show_help_and_invalidate(monkeypatch, keys: tuple[str | Keys, ...]) -> None:
    mycli = DummyMyCli(DummyKeysConfig())
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()
    browser_calls: list[str] = []
    terminal_calls: list[Callable[[], None]] = []
    invalidated: list[DummyApp] = []

    monkeypatch.setattr(key_bindings.webbrowser, 'open_new_tab', lambda url: browser_calls.append(url))
    monkeypatch.setattr(
        key_bindings.prompt_toolkit.application,
        'run_in_terminal',
        lambda fn: terminal_calls.append(fn),
    )
    monkeypatch.setattr(key_bindings, 'safe_invalidate_display', lambda app: invalidated.append(app))

    binding_handler(kb, *keys)(event)

    assert browser_calls == [key_bindings.DOCS_URL]
    assert terminal_calls == [key_bindings.print_f1_help]
    assert invalidated == [event.app]


@pytest.mark.parametrize('keys', ((Keys.F2,), (Keys.Escape, '[', 'Q')))
def test_f2_bindings_toggle_smart_completion(keys: tuple[str | Keys, ...]) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), smart_completion=True)
    kb = key_bindings.mycli_bindings(mycli)

    binding_handler(kb, *keys)(make_event())

    assert mycli.completer.smart_completion is False


@pytest.mark.parametrize('keys', ((Keys.F3,), (Keys.Escape, '[', 'R')))
def test_f3_bindings_toggle_multiline_mode(keys: tuple[str | Keys, ...]) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), multi_line=False)
    kb = key_bindings.mycli_bindings(mycli)

    binding_handler(kb, *keys)(make_event())

    assert mycli.multi_line is True


@pytest.mark.parametrize(
    ('keys', 'initial_mode', 'expected_mode', 'expected_editing_mode', 'expected_timeout'),
    (
        ((Keys.F4,), 'vi', 'emacs', EditingMode.EMACS, 1.5),
        ((Keys.F4,), 'emacs', 'vi', EditingMode.VI, 0.5),
        ((Keys.Escape, '[', 'S'), 'vi', 'emacs', EditingMode.EMACS, 1.5),
        ((Keys.Escape, '[', 'S'), 'emacs', 'vi', EditingMode.VI, 0.5),
    ),
)
def test_f4_bindings_toggle_key_binding_modes(
    keys: tuple[str | Keys, ...],
    initial_mode: str,
    expected_mode: str,
    expected_editing_mode: EditingMode,
    expected_timeout: float,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), key_bindings_mode=initial_mode)
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()

    binding_handler(kb, *keys)(event)

    assert mycli.key_bindings == expected_mode
    assert event.app.editing_mode == expected_editing_mode
    assert event.app.ttimeoutlen == expected_timeout


def test_tab_binding_uses_toolkit_default_to_start_completion() -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'tab': ['toolkit_default']}))
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text='sel'))

    binding_handler(kb, Keys.ControlI)(event)

    assert event.app.current_buffer.start_completion_calls == [{'select_first': True, 'insert_common_part': False}]
    assert event.app.current_buffer.complete_next_calls == 0


def test_tab_binding_uses_toolkit_default_to_advance_existing_completion() -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'tab': ['toolkit_default']}))
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text='sel', complete_state=object()))

    binding_handler(kb, Keys.ControlI)(event)

    assert event.app.current_buffer.complete_next_calls == 1


@pytest.mark.parametrize(
    ('behaviors', 'expected_start', 'expected_complete_next', 'expected_cancel'),
    (
        (['advance'], [], 1, 0),
        (['cancel'], [], 0, 1),
        (['advancing_summon'], [{'select_first': True, 'insert_common_part': False}], 0, 0),
        (['prefixing_summon'], [{'select_first': False, 'insert_common_part': True}], 0, 0),
        (['summon'], [{'select_first': False, 'insert_common_part': False}], 0, 0),
    ),
)
def test_tab_binding_supports_configured_behaviors(
    behaviors: list[str],
    expected_start: list[dict[str, bool]],
    expected_complete_next: int,
    expected_cancel: int,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'tab': behaviors}))
    kb = key_bindings.mycli_bindings(mycli)
    complete_state = object() if behaviors[0] in {'advance', 'cancel'} else None
    event = make_event(DummyBuffer(text='sel', complete_state=complete_state))

    binding_handler(kb, Keys.ControlI)(event)

    assert event.app.current_buffer.start_completion_calls == expected_start
    assert event.app.current_buffer.complete_next_calls == expected_complete_next
    assert event.app.current_buffer.cancel_completion_calls == expected_cancel


def test_escape_binding_cancels_completion_menu(monkeypatch) -> None:
    mycli = DummyMyCli(DummyKeysConfig())
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(complete_state=object()))
    monkeypatch.setattr(key_bindings, 'get_app', lambda: event.app)

    assert binding(kb, Keys.Escape).eager() is True
    assert binding_filter(kb, Keys.Escape)() is True

    inactive_event = make_event(DummyBuffer(complete_state=None))
    monkeypatch.setattr(key_bindings, 'get_app', lambda: inactive_event.app)
    assert binding_filter(kb, Keys.Escape)() is False

    monkeypatch.setattr(key_bindings, 'get_app', lambda: event.app)

    binding_handler(kb, Keys.Escape)(event)

    assert event.app.current_buffer.cancel_completion_calls == 1
    assert event.app.current_buffer.complete_state is None


def test_control_space_toolkit_default_starts_selection_for_non_empty_text() -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'control_space': ['toolkit_default']}))
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text='abc'))

    binding_handler(kb, Keys.ControlAt)(event)

    assert event.app.current_buffer.start_selection_calls == [SelectionType.CHARACTERS]


def test_control_space_toolkit_default_is_noop_for_empty_text() -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'control_space': ['toolkit_default']}))
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text=''))

    binding_handler(kb, Keys.ControlAt)(event)

    assert event.app.current_buffer.start_selection_calls == []
    assert event.app.current_buffer.start_completion_calls == []


@pytest.mark.parametrize(
    ('behaviors', 'expected_start', 'expected_complete_next', 'expected_cancel'),
    (
        (['advance'], [], 1, 0),
        (['cancel'], [], 0, 1),
        (['advancing_summon'], [{'select_first': True, 'insert_common_part': False}], 0, 0),
        (['prefixing_summon'], [{'select_first': False, 'insert_common_part': True}], 0, 0),
        (['summon'], [{'select_first': False, 'insert_common_part': False}], 0, 0),
    ),
)
def test_control_space_supports_completion_behaviors(
    behaviors: list[str],
    expected_start: list[dict[str, bool]],
    expected_complete_next: int,
    expected_cancel: int,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(behaviors={'control_space': behaviors}))
    kb = key_bindings.mycli_bindings(mycli)
    complete_state = object() if behaviors[0] in {'advance', 'cancel'} else None
    event = make_event(DummyBuffer(text='sel', complete_state=complete_state))

    binding_handler(kb, Keys.ControlAt)(event)

    assert event.app.current_buffer.start_completion_calls == expected_start
    assert event.app.current_buffer.complete_next_calls == expected_complete_next
    assert event.app.current_buffer.cancel_completion_calls == expected_cancel


@pytest.mark.parametrize(
    ('keys', 'text', 'handler_name'),
    (
        ((Keys.ControlX, 'p'), 'select 1', 'handle_prettify_binding'),
        ((Keys.ControlX, 'u'), 'select 1', 'handle_unprettify_binding'),
    ),
)
def test_prettify_bindings_transform_non_empty_text(
    monkeypatch,
    keys: tuple[str | Keys, ...],
    text: str,
    handler_name: str,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), key_bindings_mode='emacs')
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text=text))
    event.app.editing_mode = EditingMode.EMACS
    patch_filter_app(monkeypatch, event.app)

    assert binding_filter(kb, *keys)() is True

    inactive_event = make_event(DummyBuffer(text=text))
    inactive_event.app.editing_mode = EditingMode.VI
    patch_filter_app(monkeypatch, inactive_event.app)
    assert binding_filter(kb, *keys)() is False

    patch_filter_app(monkeypatch, event.app)

    binding_handler(kb, *keys)(event)

    start, end, handler = event.app.current_buffer.transform_calls[0]
    assert (start, end) == (0, len(text))
    assert handler.__func__ is getattr(DummyMyCli, handler_name)


@pytest.mark.parametrize(('keys'), (((Keys.ControlX, 'p')), ((Keys.ControlX, 'u'))))
def test_prettify_bindings_ignore_empty_text(monkeypatch, keys: tuple[str | Keys, ...]) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), key_bindings_mode='emacs')
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text=''))
    event.app.editing_mode = EditingMode.EMACS
    patch_filter_app(monkeypatch, event.app)

    assert binding_filter(kb, *keys)() is True

    inactive_event = make_event(DummyBuffer(text=''))
    inactive_event.app.editing_mode = EditingMode.VI
    patch_filter_app(monkeypatch, inactive_event.app)
    assert binding_filter(kb, *keys)() is False

    patch_filter_app(monkeypatch, event.app)

    binding_handler(kb, *keys)(event)

    assert event.app.current_buffer.transform_calls == []


@pytest.mark.parametrize(
    ('keys', 'expected_text'),
    (
        ((Keys.ControlO, 'd'), 'DATE'),
        ((Keys.ControlO, Keys.ControlD), "'DATE'"),
        ((Keys.ControlO, 't'), 'DATETIME'),
        ((Keys.ControlO, Keys.ControlT), "'DATETIME'"),
    ),
)
def test_date_and_datetime_bindings_insert_shortcuts(
    monkeypatch,
    keys: tuple[str | Keys, ...],
    expected_text: str,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), key_bindings_mode='emacs')
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()
    event.app.editing_mode = EditingMode.EMACS
    patch_filter_app(monkeypatch, event.app)

    monkeypatch.setattr(
        key_bindings.shortcuts,
        'server_date',
        lambda _sqlexecute, quoted=False: "'DATE'" if quoted else 'DATE',
    )
    monkeypatch.setattr(
        key_bindings.shortcuts,
        'server_datetime',
        lambda _sqlexecute, quoted=False: "'DATETIME'" if quoted else 'DATETIME',
    )

    assert binding_filter(kb, *keys)() is True

    inactive_event = make_event()
    inactive_event.app.editing_mode = EditingMode.VI
    patch_filter_app(monkeypatch, inactive_event.app)
    assert binding_filter(kb, *keys)() is False

    patch_filter_app(monkeypatch, event.app)

    binding_handler(kb, *keys)(event)

    assert event.app.current_buffer.inserted_text == [expected_text]


def test_control_r_uses_reverse_isearch_mode_when_configured(monkeypatch) -> None:
    mycli = DummyMyCli(DummyKeysConfig(options={'control_r': 'reverse_isearch'}), key_bindings_mode='emacs')
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()
    event.app.editing_mode = EditingMode.EMACS
    event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    vi_mode_event = make_event()
    vi_mode_event.app.editing_mode = EditingMode.VI
    vi_mode_event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    calls: list[dict[str, Any]] = []
    patch_filter_app(monkeypatch, event.app)

    monkeypatch.setattr(
        key_bindings,
        'search_history',
        lambda *args, **kwargs: calls.append({'args': args, 'kwargs': kwargs}),
    )

    assert binding_filter(kb, Keys.ControlR)() is True

    inactive_event = make_event()
    inactive_event.app.editing_mode = EditingMode.EMACS
    inactive_event.app.layout = SimpleNamespace(current_control=object())
    patch_filter_app(monkeypatch, inactive_event.app)
    assert binding_filter(kb, Keys.ControlR)() is False

    patch_filter_app(monkeypatch, vi_mode_event.app)
    assert binding_filter(kb, Keys.ControlR)() is True

    patch_filter_app(monkeypatch, event.app)

    binding_handler(kb, Keys.ControlR)(event)
    patch_filter_app(monkeypatch, vi_mode_event.app)
    binding_handler(kb, Keys.ControlR)(vi_mode_event)

    assert calls == [
        {'args': (event,), 'kwargs': {'incremental': True}},
        {'args': (vi_mode_event,), 'kwargs': {'incremental': True}},
    ]


def test_control_r_and_alt_r_use_fzf_search_options(monkeypatch) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), key_bindings_mode='emacs')
    kb = key_bindings.mycli_bindings(mycli)
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        key_bindings,
        'search_history',
        lambda *args, **kwargs: calls.append({'args': args, 'kwargs': kwargs}),
    )

    control_r_event = make_event()
    alt_r_event = make_event()
    control_r_event.app.editing_mode = EditingMode.EMACS
    alt_r_event.app.editing_mode = EditingMode.EMACS
    control_r_event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    alt_r_event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    patch_filter_app(monkeypatch, control_r_event.app)
    assert binding_filter(kb, Keys.ControlR)() is True

    inactive_control_r_event = make_event()
    inactive_control_r_event.app.editing_mode = EditingMode.EMACS
    inactive_control_r_event.app.layout = SimpleNamespace(current_control=object())
    patch_filter_app(monkeypatch, inactive_control_r_event.app)
    assert binding_filter(kb, Keys.ControlR)() is False

    vi_mode_control_r_event = make_event()
    vi_mode_control_r_event.app.editing_mode = EditingMode.VI
    vi_mode_control_r_event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    patch_filter_app(monkeypatch, vi_mode_control_r_event.app)
    assert binding_filter(kb, Keys.ControlR)() is True

    patch_filter_app(monkeypatch, control_r_event.app)
    binding_handler(kb, Keys.ControlR)(control_r_event)
    patch_filter_app(monkeypatch, vi_mode_control_r_event.app)
    binding_handler(kb, Keys.ControlR)(vi_mode_control_r_event)
    patch_filter_app(monkeypatch, alt_r_event.app)
    assert binding_filter(kb, Keys.Escape, 'r')() is True

    vi_mode_event = make_event()
    vi_mode_event.app.editing_mode = EditingMode.VI
    vi_mode_event.app.layout = SimpleNamespace(current_control=BufferControl(search_buffer_control=SearchBufferControl()))
    patch_filter_app(monkeypatch, vi_mode_event.app)
    assert binding_filter(kb, Keys.Escape, 'r')() is False

    non_searchable_event = make_event()
    non_searchable_event.app.editing_mode = EditingMode.EMACS
    non_searchable_event.app.layout = SimpleNamespace(current_control=object())
    patch_filter_app(monkeypatch, non_searchable_event.app)
    assert binding_filter(kb, Keys.Escape, 'r')() is False

    patch_filter_app(monkeypatch, alt_r_event.app)
    binding_handler(kb, Keys.Escape, 'r')(alt_r_event)

    assert calls == [
        {
            'args': (control_r_event,),
            'kwargs': {
                'highlight_preview': True,
                'highlight_style': 'native',
            },
        },
        {
            'args': (vi_mode_control_r_event,),
            'kwargs': {
                'highlight_preview': True,
                'highlight_style': 'native',
            },
        },
        {
            'args': (alt_r_event,),
            'kwargs': {
                'highlight_preview': True,
                'highlight_style': 'native',
            },
        },
    ]


@pytest.mark.parametrize(
    ('mode', 'expected_exit_calls', 'expected_bells'),
    (
        ('exit', [{'exception': EOFError, 'style': 'class:exiting'}], 0),
        ('bell', [], 1),
    ),
)
def test_control_d_binding_exits_or_bells(
    monkeypatch,
    mode: str,
    expected_exit_calls: list[dict[str, Any]],
    expected_bells: int,
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(options={'control_d': mode}))
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()
    monkeypatch.setattr(key_bindings, 'get_app', lambda: event.app)

    assert binding_filter(kb, Keys.ControlD)() is True

    inactive_event = make_event(DummyBuffer(text='select 1'))
    monkeypatch.setattr(key_bindings, 'get_app', lambda: inactive_event.app)
    assert binding_filter(kb, Keys.ControlD)() is False

    monkeypatch.setattr(key_bindings, 'get_app', lambda: event.app)

    binding_handler(kb, Keys.ControlD)(event)

    assert event.app.exit_calls == expected_exit_calls
    assert event.app.output.bell_calls == expected_bells


def test_enter_binding_closes_completion_menu(monkeypatch) -> None:
    mycli = DummyMyCli(DummyKeysConfig())
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event(DummyBuffer(text='sel', complete_state=SimpleNamespace(current_completion=object())))
    patch_filter_app(monkeypatch, event.app)

    assert binding_filter(kb, Keys.ControlM)() is True

    inactive_event = make_event(DummyBuffer(text='sel', complete_state=SimpleNamespace(current_completion=None)))
    patch_filter_app(monkeypatch, inactive_event.app)
    assert binding_filter(kb, Keys.ControlM)() is False

    patch_filter_app(monkeypatch, event.app)

    binding_handler(kb, Keys.ControlM)(event)

    assert event.current_buffer.complete_state is None
    assert event.app.current_buffer.complete_state is None


@pytest.mark.parametrize(
    ('multi_line', 'expected_validate_calls', 'expected_inserted_text'),
    (
        (True, 1, []),
        (False, 0, ['\n']),
    ),
)
def test_alt_enter_binding_validates_or_inserts_newline(
    multi_line: bool,
    expected_validate_calls: int,
    expected_inserted_text: list[str],
) -> None:
    mycli = DummyMyCli(DummyKeysConfig(), multi_line=multi_line)
    kb = key_bindings.mycli_bindings(mycli)
    event = make_event()

    binding_handler(kb, Keys.Escape, Keys.ControlM)(event)

    assert event.app.current_buffer.validate_calls == expected_validate_calls
    assert event.app.current_buffer.inserted_text == expected_inserted_text

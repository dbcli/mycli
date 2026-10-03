from __future__ import annotations

from collections.abc import Callable, Generator
import importlib
import sys
from types import ModuleType

import pytest

import mycli.packages


@pytest.fixture
def load_special_commands(monkeypatch: pytest.MonkeyPatch) -> Generator[Callable[[bool], ModuleType], None, None]:
    original_module = sys.modules.get('mycli.packages.special_commands')
    parent_had_special_commands = hasattr(mycli.packages, 'special_commands')
    original_parent_special_commands = getattr(mycli.packages, 'special_commands', None)

    def load(llm_off: bool) -> ModuleType:
        if llm_off:
            monkeypatch.setenv('MYCLI_LLM_OFF', '1')
        else:
            monkeypatch.delenv('MYCLI_LLM_OFF', raising=False)
        sys.modules.pop('mycli.packages.special_commands', None)
        if hasattr(mycli.packages, 'special_commands'):
            delattr(mycli.packages, 'special_commands')
        return importlib.import_module('mycli.packages.special_commands')

    yield load

    sys.modules.pop('mycli.packages.special_commands', None)
    if original_module is not None:
        sys.modules['mycli.packages.special_commands'] = original_module
    if parent_had_special_commands:
        mycli.packages.special_commands = original_parent_special_commands  # type: ignore[attr-defined]
    elif hasattr(mycli.packages, 'special_commands'):
        delattr(mycli.packages, 'special_commands')


def test_special_commands_init_exports_public_names(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(False)

    for name in special_commands.__all__:
        assert hasattr(special_commands, name)


def test_special_commands_init_reexports_special_command_api(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(False)
    special_commands_main = importlib.import_module('mycli.packages.special_commands.main')

    assert special_commands.execute is special_commands_main.execute
    assert special_commands.special_command is special_commands_main.special_command
    assert special_commands.CommandNotFound is special_commands_main.CommandNotFound


def test_special_commands_init_reexports_io_state_api(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(False)
    io_commands = importlib.import_module('mycli.packages.special_commands.io_commands')

    assert special_commands.set_pager_enabled is io_commands.set_pager_enabled
    assert special_commands.is_pager_enabled is io_commands.is_pager_enabled
    assert special_commands.write_tee is io_commands.write_tee


def test_special_commands_init_reexports_dbcommands(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(False)
    db_commands = importlib.import_module('mycli.packages.special_commands.db_commands')

    assert special_commands.list_databases is db_commands.list_databases
    assert special_commands.list_tables is db_commands.list_tables
    assert special_commands.ping is db_commands.ping
    assert special_commands.status is db_commands.status


def test_special_commands_init_uses_llm_implementation_when_enabled(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(False)
    llm = importlib.import_module('mycli.packages.special_commands.llm')

    assert special_commands.FinishIteration is llm.FinishIteration
    assert special_commands.is_llm_command is llm.is_llm_command
    assert special_commands.handle_llm is llm.handle_llm
    assert special_commands.sql_using_llm is llm.sql_using_llm


def test_special_commands_init_uses_llm_stubs_when_disabled(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(True)

    assert special_commands.is_llm_command(r'/llm prompt') is False
    with pytest.raises(special_commands.FinishIteration) as handle_exc:
        special_commands.handle_llm(cast_args := object())
    with pytest.raises(special_commands.FinishIteration) as sql_exc:
        special_commands.sql_using_llm(cast_args)

    assert handle_exc.value.results is None
    assert sql_exc.value.results is None


def test_special_commands_init_stub_finish_iteration_stores_results(load_special_commands: Callable[[bool], ModuleType]) -> None:
    special_commands = load_special_commands(True)

    error = special_commands.FinishIteration(results=['done'])

    assert error.results == ['done']

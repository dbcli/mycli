from __future__ import annotations

from collections.abc import Callable, Generator
import importlib
import sys
from types import ModuleType

import pytest

import mycli.packages


@pytest.fixture
def load_special(monkeypatch: pytest.MonkeyPatch) -> Generator[Callable[[bool], ModuleType], None, None]:
    original_module = sys.modules.get('mycli.packages.special')
    parent_had_special = hasattr(mycli.packages, 'special')
    original_parent_special = getattr(mycli.packages, 'special', None)

    def load(llm_off: bool) -> ModuleType:
        if llm_off:
            monkeypatch.setenv('MYCLI_LLM_OFF', '1')
        else:
            monkeypatch.delenv('MYCLI_LLM_OFF', raising=False)
        sys.modules.pop('mycli.packages.special', None)
        if hasattr(mycli.packages, 'special'):
            delattr(mycli.packages, 'special')
        return importlib.import_module('mycli.packages.special')

    yield load

    sys.modules.pop('mycli.packages.special', None)
    if original_module is not None:
        sys.modules['mycli.packages.special'] = original_module
    if parent_had_special:
        mycli.packages.special = original_parent_special  # type: ignore[attr-defined]
    elif hasattr(mycli.packages, 'special'):
        delattr(mycli.packages, 'special')


def test_special_init_exports_public_names(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(False)

    for name in special.__all__:
        assert hasattr(special, name)


def test_special_init_reexports_special_command_api(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(False)
    special_main = importlib.import_module('mycli.packages.special.main')

    assert special.execute is special_main.execute
    assert special.special_command is special_main.special_command
    assert special.CommandNotFound is special_main.CommandNotFound


def test_special_init_reexports_io_state_api(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(False)
    iocommands = importlib.import_module('mycli.packages.special.iocommands')

    assert special.set_pager_enabled is iocommands.set_pager_enabled
    assert special.is_pager_enabled is iocommands.is_pager_enabled
    assert special.write_tee is iocommands.write_tee


def test_special_init_reexports_dbcommands(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(False)
    dbcommands = importlib.import_module('mycli.packages.special.dbcommands')

    assert special.list_databases is dbcommands.list_databases
    assert special.list_tables is dbcommands.list_tables
    assert special.status is dbcommands.status


def test_special_init_uses_llm_implementation_when_enabled(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(False)
    llm = importlib.import_module('mycli.packages.special.llm')

    assert special.FinishIteration is llm.FinishIteration
    assert special.is_llm_command is llm.is_llm_command
    assert special.handle_llm is llm.handle_llm
    assert special.sql_using_llm is llm.sql_using_llm


def test_special_init_uses_llm_stubs_when_disabled(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(True)

    assert special.is_llm_command(r'\llm prompt') is False
    with pytest.raises(special.FinishIteration) as handle_exc:
        special.handle_llm(cast_args := object())
    with pytest.raises(special.FinishIteration) as sql_exc:
        special.sql_using_llm(cast_args)

    assert handle_exc.value.results is None
    assert sql_exc.value.results is None


def test_special_init_stub_finish_iteration_stores_results(load_special: Callable[[bool], ModuleType]) -> None:
    special = load_special(True)

    error = special.FinishIteration(results=['done'])

    assert error.results == ['done']

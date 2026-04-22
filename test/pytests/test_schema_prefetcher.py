# type: ignore

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from mycli import schema_prefetcher as schema_prefetcher_module
from mycli.schema_prefetcher import SchemaPrefetcher, parse_prefetch_config
from mycli.sqlcompleter import SQLCompleter


def test_parse_prefetch_config_never() -> None:
    assert parse_prefetch_config('never', '') == []
    assert parse_prefetch_config('NEVER', 'ignored,values') == []
    assert parse_prefetch_config('  never  ', None) == []


def test_parse_prefetch_config_always() -> None:
    assert parse_prefetch_config('always', '') is None
    assert parse_prefetch_config('ALWAYS', None) is None
    assert parse_prefetch_config('  always  ', 'ignored') is None


def test_parse_prefetch_config_listed() -> None:
    assert parse_prefetch_config('listed', 'foo, bar , baz') == ['foo', 'bar', 'baz']
    assert parse_prefetch_config('LISTED', 'solo') == ['solo']
    assert parse_prefetch_config('listed', '') == []
    assert parse_prefetch_config('listed', None) == []
    # configobj pre-splits multi-value entries into a list of strings.
    assert parse_prefetch_config('listed', ['foo', ' bar ', 'baz']) == ['foo', 'bar', 'baz']
    assert parse_prefetch_config('listed', []) == []


def make_mycli(
    prefetch_mode: str = 'listed',
    prefetch_list: str = '',
    dbname: str = 'current',
    databases=None,
):
    if databases is None:
        databases = ['current', 'other1', 'other2']
    completer = SQLCompleter(smart_completion=True)
    completer.set_dbname(dbname)
    sqlexecute = SimpleNamespace(
        dbname=dbname,
        user='u',
        password='p',
        host='h',
        port=3306,
        socket=None,
        character_set='utf8mb4',
        local_infile=False,
        ssl=None,
        ssh_user=None,
        ssh_host=None,
        ssh_port=22,
        ssh_password=None,
        ssh_key_filename=None,
        databases=MagicMock(return_value=list(databases)),
    )
    return SimpleNamespace(
        completer=completer,
        sqlexecute=sqlexecute,
        prefetch_schemas_mode=prefetch_mode,
        prefetch_schemas_list=prefetch_list,
        _completer_lock=threading.Lock(),
        prompt_session=None,
    )


def _fake_executor_factory(per_schema_tables, databases=None):
    """Build an executor stub whose schema-aware methods yield prebuilt rows."""

    def make(*_args, **_kwargs):
        executor = MagicMock()
        executor.databases.return_value = list(databases) if databases is not None else []
        executor.table_columns.side_effect = lambda schema=None: iter(per_schema_tables.get(schema, []))
        executor.foreign_keys.side_effect = lambda schema=None: iter([])
        executor.enum_values.side_effect = lambda schema=None: iter([])
        executor.functions.side_effect = lambda schema=None: iter([])
        executor.procedures.side_effect = lambda schema=None: iter([])
        executor.close = MagicMock()
        return executor

    return make


def test_start_configured_skips_current_and_prefetches_others(monkeypatch):
    mycli = make_mycli(prefetch_mode='listed', prefetch_list='other1, current, other2')
    tables = {
        'other1': [('users', 'id'), ('users', 'email')],
        'other2': [('orders', 'id')],
    }
    monkeypatch.setattr(schema_prefetcher_module, 'SQLExecute', _fake_executor_factory(tables))

    prefetcher = SchemaPrefetcher(mycli)
    prefetcher.start_configured()
    assert prefetcher._thread is not None
    prefetcher._thread.join(timeout=5)

    tables_meta = mycli.completer.dbmetadata['tables']
    assert 'other1' in tables_meta
    assert 'other2' in tables_meta
    # Current schema must be untouched by the prefetcher.
    assert 'current' not in tables_meta
    assert set(tables_meta['other1'].keys()) == {'users'}
    # Column list starts with '*' marker and contains escaped column names.
    assert tables_meta['other1']['users'][0] == '*'
    assert 'id' in tables_meta['other1']['users']


def test_start_configured_all_resolves_from_databases(monkeypatch):
    mycli = make_mycli(prefetch_mode='always', databases=['current', 'alpha', 'beta'])
    tables = {
        'alpha': [('t_a', 'c')],
        'beta': [('t_b', 'c')],
    }
    monkeypatch.setattr(
        schema_prefetcher_module,
        'SQLExecute',
        _fake_executor_factory(tables, databases=['current', 'alpha', 'beta']),
    )

    prefetcher = SchemaPrefetcher(mycli)
    prefetcher.start_configured()
    assert prefetcher._thread is not None
    prefetcher._thread.join(timeout=5)

    tables_meta = mycli.completer.dbmetadata['tables']
    assert 'alpha' in tables_meta
    assert 'beta' in tables_meta
    assert 'current' not in tables_meta


def test_start_configured_noop_when_disabled(monkeypatch):
    mycli = make_mycli(prefetch_mode='never')
    make_executor = MagicMock()
    monkeypatch.setattr(schema_prefetcher_module, 'SQLExecute', make_executor)

    prefetcher = SchemaPrefetcher(mycli)
    prefetcher.start_configured()

    assert prefetcher._thread is None
    make_executor.assert_not_called()


def test_prefetch_schema_now_loads_single_schema(monkeypatch):
    mycli = make_mycli(prefetch_mode='never')
    tables = {'target': [('t1', 'c1')]}
    monkeypatch.setattr(schema_prefetcher_module, 'SQLExecute', _fake_executor_factory(tables))

    prefetcher = SchemaPrefetcher(mycli)
    prefetcher.prefetch_schema_now('target')
    assert prefetcher._thread is not None
    prefetcher._thread.join(timeout=5)

    assert 'target' in mycli.completer.dbmetadata['tables']


def test_stop_interrupts_running_prefetch(monkeypatch):
    mycli = make_mycli(prefetch_mode='listed', prefetch_list='a, b')
    monkeypatch.setattr(
        schema_prefetcher_module,
        'SQLExecute',
        _fake_executor_factory({'a': [], 'b': []}),
    )

    prefetcher = SchemaPrefetcher(mycli)
    # Immediately cancel before any work runs.
    prefetcher._cancel.set()
    prefetcher._start(['a', 'b'])
    if prefetcher._thread is not None:
        prefetcher._thread.join(timeout=5)
    # stop() must be idempotent and leave the prefetcher ready to run again.
    prefetcher.stop()
    assert prefetcher._thread is None


def test_start_skips_schemas_already_in_completer(monkeypatch):
    """Previously-loaded schemas must not be re-fetched on refresh."""
    mycli = make_mycli(prefetch_mode='listed', prefetch_list='keep, fresh')
    # Simulate a schema that was already loaded (e.g., preserved via
    # copy_other_schemas_from after a completion refresh).
    mycli.completer.dbmetadata['tables']['keep'] = {'cached_table': ['*', 'c1']}

    executor_calls: list[str] = []

    def make(*_args, **_kwargs):
        executor = MagicMock()

        def _track(schema=None):
            executor_calls.append(schema)
            return iter([])

        executor.table_columns.side_effect = _track
        executor.foreign_keys.side_effect = lambda schema=None: iter([])
        executor.enum_values.side_effect = lambda schema=None: iter([])
        executor.functions.side_effect = lambda schema=None: iter([])
        executor.procedures.side_effect = lambda schema=None: iter([])
        executor.close = MagicMock()
        return executor

    monkeypatch.setattr(schema_prefetcher_module, 'SQLExecute', make)

    prefetcher = SchemaPrefetcher(mycli)
    prefetcher.start_configured()
    if prefetcher._thread is not None:
        prefetcher._thread.join(timeout=5)

    # Only 'fresh' is queried; 'keep' and 'current' are skipped.
    assert executor_calls == ['fresh']
    # Cached data for 'keep' is untouched.
    assert mycli.completer.dbmetadata['tables']['keep'] == {'cached_table': ['*', 'c1']}

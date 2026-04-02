# type: ignore

import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import mycli.completion_refresher as completion_refresher


@pytest.fixture
def refresher():
    return completion_refresher.CompletionRefresher()


class FakeThread:
    def __init__(self, target, args, name) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.daemon = False
        self.started = False
        self.alive = False

    def start(self) -> None:
        self.started = True
        self.alive = True

    def run_target(self) -> None:
        try:
            self.target(*self.args)
        finally:
            self.alive = False

    def is_alive(self) -> bool:
        return self.alive


def make_sqlexecute() -> SimpleNamespace:
    return SimpleNamespace(
        dbname='db',
        user='user',
        password='pw',
        host='host',
        port=3306,
        socket='/tmp/mysql.sock',
        character_set='utf8mb4',
        local_infile=False,
        ssl={'ca': 'ca.pem'},
        ssh_user='ssh-user',
        ssh_host='ssh-host',
        ssh_port=22,
        ssh_password='ssh-pw',
        ssh_key_filename='id_rsa',
    )


def test_ctor(refresher) -> None:
    assert len(refresher.refreshers) > 0
    assert list(refresher.refreshers.keys()) == [
        "databases",
        "schemata",
        "tables",
        "foreign_keys",
        "enum_values",
        "users",
        "functions",
        "procedures",
        'character_sets',
        'collations',
        "special_commands",
        "show_commands",
        "keywords",
    ]


def test_refresh_called_once(refresher):
    """

    :param refresher:
    :return:
    """
    callbacks = Mock()
    sqlexecute = Mock()

    with patch.object(refresher, "_bg_refresh") as bg_refresh:
        actual = refresher.refresh(sqlexecute, callbacks)
        time.sleep(1)  # Wait for the thread to work.
        assert actual[0].preamble is None
        assert actual[0].header is None
        assert actual[0].rows is None
        assert actual[0].status == "Auto-completion refresh started in the background."
        bg_refresh.assert_called_with(sqlexecute, callbacks, {})


def test_refresh_called_twice(refresher):
    """If refresh is called a second time, it should be restarted.

    :param refresher:
    :return:

    """
    callbacks = Mock()

    sqlexecute = Mock()

    def dummy_bg_refresh(*args):
        time.sleep(3)  # seconds

    refresher._bg_refresh = dummy_bg_refresh

    actual1 = refresher.refresh(sqlexecute, callbacks)
    time.sleep(1)  # Wait for the thread to work.
    assert actual1[0].preamble is None
    assert actual1[0].header is None
    assert actual1[0].rows is None
    assert actual1[0].status == "Auto-completion refresh started in the background."

    actual2 = refresher.refresh(sqlexecute, callbacks)
    time.sleep(1)  # Wait for the thread to work.
    assert actual2[0].preamble is None
    assert actual2[0].header is None
    assert actual2[0].rows is None
    assert actual2[0].status == "Auto-completion refresh restarted."
    assert refresher._completer_thread is not None
    refresher._completer_thread.join()


def test_refresh_with_callbacks(refresher):
    """Callbacks must be called.

    :param refresher:

    """
    callbacks = [Mock()]
    sqlexecute_class = Mock()
    sqlexecute = Mock()

    with patch("mycli.completion_refresher.SQLExecute", sqlexecute_class):
        # Set refreshers to 0: we're not testing refresh logic here
        refresher.refreshers = {}
        refresher.refresh(sqlexecute, callbacks)
        time.sleep(1)  # Wait for the thread to work.
        assert callbacks[0].call_count == 1


def test_refresh_starts_background_thread(monkeypatch, refresher) -> None:
    calls: list[tuple[object, object, dict]] = []

    def fake_bg_refresh(executor, callbacks, options) -> None:
        calls.append((executor, callbacks, options))

    monkeypatch.setattr(completion_refresher.threading, 'Thread', FakeThread)
    monkeypatch.setattr(refresher, '_bg_refresh', fake_bg_refresh)

    sqlexecute = Mock()
    callbacks = Mock()

    actual = refresher.refresh(sqlexecute, callbacks)

    assert actual[0].status == "Auto-completion refresh started in the background."
    assert refresher._completer_thread is not None
    assert refresher._completer_thread.name == "completion_refresh"
    assert refresher._completer_thread.daemon is True
    assert refresher._completer_thread.started is True
    assert refresher.is_refreshing() is True
    assert calls == []

    refresher._completer_thread.run_target()
    assert calls == [(sqlexecute, callbacks, {})]
    assert refresher.is_refreshing() is False


def test_refresh_passes_explicit_completer_options(monkeypatch, refresher) -> None:
    calls: list[tuple[object, object, dict]] = []

    def fake_bg_refresh(executor, callbacks, options) -> None:
        calls.append((executor, callbacks, options))

    monkeypatch.setattr(completion_refresher.threading, 'Thread', FakeThread)
    monkeypatch.setattr(refresher, '_bg_refresh', fake_bg_refresh)

    sqlexecute = Mock()
    callbacks = Mock()
    options = {'smart_completion': True}

    refresher.refresh(sqlexecute, callbacks, options)
    refresher._completer_thread.run_target()

    assert calls == [(sqlexecute, callbacks, options)]


def test_refresh_while_refreshing_restarts(monkeypatch, refresher) -> None:
    thread_calls: list[tuple[object, object, str]] = []

    def fail_thread(*, target, args, name):
        thread_calls.append((target, args, name))
        return FakeThread(target, args, name)

    monkeypatch.setattr(completion_refresher.threading, 'Thread', fail_thread)
    existing_thread = SimpleNamespace(is_alive=lambda: True)
    refresher._completer_thread = existing_thread

    actual = refresher.refresh(Mock(), Mock())

    assert actual[0].status == "Auto-completion refresh restarted."
    assert refresher._restart_refresh.is_set() is True
    assert refresher._completer_thread is existing_thread
    assert thread_calls == []


def test_bg_refresh_restarts_wraps_callbacks_and_closes(monkeypatch, refresher) -> None:
    completers: list[SimpleNamespace] = []
    executor_inits: list[tuple[object, ...]] = []
    executors: list[object] = []
    refresher_calls: list[str] = []
    callback_calls: list[tuple[str, SimpleNamespace]] = []
    event_order: list[str] = []

    class FakeCompleter:
        tidb_functions = ['tidb-func']
        tidb_keywords = ['tidb-keyword']

        def __init__(self, **options) -> None:
            self.options = options
            completers.append(self)

    class FakeExecutor:
        def __init__(self, *args) -> None:
            executor_inits.append(args)
            self.closed = False
            executors.append(self)

        def close(self) -> None:
            self.closed = True
            event_order.append('close')

    def first_refresher(completer, executor) -> None:
        refresher_calls.append('first')
        event_order.append('refresher:first')
        if refresher_calls == ['first']:
            refresher._restart_refresh.set()

    def second_refresher(completer, executor) -> None:
        refresher_calls.append('second')
        event_order.append('refresher:second')

    def first_callback(completer) -> None:
        callback_calls.append(('first', completer))
        event_order.append('callback:first')

    def second_callback(completer) -> None:
        callback_calls.append(('second', completer))
        event_order.append('callback:second')

    monkeypatch.setattr(completion_refresher, 'SQLCompleter', FakeCompleter)
    monkeypatch.setattr(completion_refresher, 'SQLExecute', FakeExecutor)
    refresher.refreshers = {
        'first': first_refresher,
        'second': second_refresher,
    }

    sqlexecute = make_sqlexecute()
    refresher._bg_refresh(sqlexecute, [first_callback, second_callback], {'smart_completion': True})

    assert len(completers) == 1
    assert completers[0].options == {'smart_completion': True}
    assert executor_inits == [
        (
            'db',
            'user',
            'pw',
            'host',
            3306,
            '/tmp/mysql.sock',
            'utf8mb4',
            False,
            {'ca': 'ca.pem'},
            'ssh-user',
            'ssh-host',
            22,
            'ssh-pw',
            'id_rsa',
        )
    ]
    assert len(executors) == 1
    assert executors[0].closed is True
    assert refresher_calls == ['first', 'first', 'second']
    assert refresher._restart_refresh.is_set() is False
    assert callback_calls == [('first', completers[0]), ('second', completers[0])]
    assert event_order == [
        'refresher:first',
        'refresher:first',
        'refresher:second',
        'callback:first',
        'callback:second',
        'close',
    ]


def test_bg_refresh_wraps_single_callback_callable(monkeypatch, refresher) -> None:
    completers: list[SimpleNamespace] = []

    class FakeCompleter:
        tidb_functions = []
        tidb_keywords = []

        def __init__(self, **options) -> None:
            completers.append(self)

    class FakeExecutor:
        def __init__(self, *args) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    callback = Mock()

    monkeypatch.setattr(completion_refresher, 'SQLCompleter', FakeCompleter)
    monkeypatch.setattr(completion_refresher, 'SQLExecute', FakeExecutor)
    refresher.refreshers = {}

    refresher._bg_refresh(make_sqlexecute(), callback, {})

    callback.assert_called_once_with(completers[0])


def test_refresher_decorator_registers_function() -> None:
    refreshers: dict[str, object] = {}

    @completion_refresher.refresher('demo', refreshers=refreshers)
    def demo(completer, executor) -> None:
        return None

    assert refreshers == {'demo': demo}


def test_refresh_helpers_delegate_to_completer_and_executor(monkeypatch) -> None:
    completer = Mock()
    executor = Mock()
    executor.dbname = 'current_db'
    executor.databases.return_value = ['db1', 'db2']
    executor.table_columns.return_value = iter([('tbl', 'col')])
    executor.foreign_keys.return_value = iter([('tbl', 'col', 'other', 'id')])
    executor.enum_values.return_value = iter([('tbl', 'status', ['open'])])
    executor.users.return_value = iter([('app',)])
    executor.procedures.return_value = iter([('proc',)])
    executor.character_sets.return_value = iter([('utf8mb4',)])
    executor.collations.return_value = iter([('utf8mb4_unicode_ci',)])
    executor.show_candidates.return_value = iter([('FULL TABLES',)])

    monkeypatch.setattr(completion_refresher, 'COMMANDS', {'\\x': object(), 'help': object()})

    completion_refresher.refresh_databases(completer, executor)
    completion_refresher.refresh_schemata(completer, executor)
    completion_refresher.refresh_tables(completer, executor)
    completion_refresher.refresh_foreign_keys(completer, executor)
    completion_refresher.refresh_enum_values(completer, executor)
    completion_refresher.refresh_users(completer, executor)
    completion_refresher.refresh_procedures(completer, executor)
    completion_refresher.refresh_character_sets(completer, executor)
    completion_refresher.refresh_collations(completer, executor)
    completion_refresher.refresh_special(completer, executor)
    completion_refresher.refresh_show_commands(completer, executor)

    completer.extend_database_names.assert_called_once_with(['db1', 'db2'])
    completer.extend_schemata.assert_called_once_with('current_db')
    completer.set_dbname.assert_called_once_with('current_db')
    completer.extend_relations.assert_called_once_with([('tbl', 'col')], kind='tables')
    completer.extend_columns.assert_called_once_with([('tbl', 'col')], kind='tables')
    completer.extend_foreign_keys.assert_called_once_with(executor.foreign_keys.return_value)
    completer.extend_enum_values.assert_called_once_with(executor.enum_values.return_value)
    completer.extend_users.assert_called_once_with(executor.users.return_value)
    completer.extend_procedures.assert_called_once_with(executor.procedures.return_value)
    completer.extend_character_sets.assert_called_once_with(executor.character_sets.return_value)
    completer.extend_collations.assert_called_once_with(executor.collations.return_value)
    completer.extend_special_commands.assert_called_once_with(['\\x', 'help'])
    completer.extend_show_items.assert_called_once_with(executor.show_candidates.return_value)


def test_refresh_functions_extends_tidb_builtins_only_for_tidb() -> None:
    completer = Mock()
    completer.tidb_functions = ['tidb_func']

    executor = Mock()
    executor.functions.return_value = iter([('func',)])
    executor.server_info = SimpleNamespace(species=completion_refresher.ServerSpecies.TiDB)

    completion_refresher.refresh_functions(completer, executor)

    assert completer.extend_functions.call_args_list == [
        ((executor.functions.return_value,), {}),
        ((['tidb_func'],), {'builtin': True}),
    ]

    completer.reset_mock()
    executor.server_info = SimpleNamespace(species=completion_refresher.ServerSpecies.MySQL)

    completion_refresher.refresh_functions(completer, executor)

    assert completer.extend_functions.call_args_list == [
        ((executor.functions.return_value,), {}),
    ]

    completer.reset_mock()
    executor.server_info = None

    completion_refresher.refresh_functions(completer, executor)

    assert completer.extend_functions.call_args_list == [
        ((executor.functions.return_value,), {}),
    ]


def test_refresh_keywords_extends_tidb_keywords_only_for_tidb() -> None:
    completer = Mock()
    completer.tidb_keywords = ['FLASHBACK']

    executor = Mock()
    executor.server_info = SimpleNamespace(species=completion_refresher.ServerSpecies.TiDB)

    completion_refresher.refresh_keywords(completer, executor)

    completer.extend_keywords.assert_called_once_with(['FLASHBACK'], replace=True)

    completer.reset_mock()
    executor.server_info = SimpleNamespace(species=completion_refresher.ServerSpecies.MySQL)

    completion_refresher.refresh_keywords(completer, executor)

    completer.extend_keywords.assert_not_called()

    completer.reset_mock()
    executor.server_info = None

    completion_refresher.refresh_keywords(completer, executor)

    completer.extend_keywords.assert_not_called()

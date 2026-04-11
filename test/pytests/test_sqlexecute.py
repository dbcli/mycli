# type: ignore

import builtins
from datetime import time
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from prompt_toolkit.formatted_text import FormattedText
import pymysql
import pytest

from mycli.constants import TEST_DATABASE
from mycli.packages.special import iocommands
from mycli.packages.sqlresult import SQLResult
import mycli.sqlexecute as sqlexecute
from mycli.sqlexecute import ServerInfo, ServerSpecies, SQLExecute
from test.utils import dbtest, is_expanded_output, run, set_expanded_output


def assert_result_equal(
    result,
    preamble=None,
    header=None,
    rows=None,
    status=None,
    status_plain=None,
    postamble=None,
    auto_status=True,
    assert_contains=False,
):
    """Assert that an sqlexecute.run() result matches the expected values."""
    if status_plain is None and auto_status and rows:
        status_plain = f"{len(rows)} row{'s' if len(rows) > 1 else ''} in set"
        status = FormattedText([('', status_plain)])
    fields = {
        "preamble": preamble,
        "header": header,
        "rows": rows,
        "postamble": postamble,
        "status": status,
        "status_plain": status_plain,
    }

    if assert_contains:
        # Do a loose match on the results using the *in* operator.
        for key, field in fields.items():
            if field:
                assert field in result[0][key]
    else:
        # Do an exact match on the fields.
        assert result == [fields]


@dbtest
def test_timediff_negative_value(executor):
    sql = "select timediff('2020-11-11 01:01:01', '2020-11-11 01:02:01')"
    result = run(executor, sql)
    # negative value comes back as str
    assert result[0]["rows"][0][0] == "-00:01:00"


@dbtest
def test_timediff_positive_value(executor):
    sql = "select timediff('2020-11-11 01:02:01', '2020-11-11 01:01:01')"
    result = run(executor, sql)
    # positive value comes back as datetime.time
    assert result[0]["rows"][0][0] == time(0, 1)


@dbtest
def test_get_result_status_without_warning(executor):
    sql = "select 1"
    result = run(executor, sql)
    assert result[0]["status_plain"] == "1 row in set"


@dbtest
def test_get_result_status_with_warning(executor):
    sql = "SELECT 1 + '0 foo'"
    result = run(executor, sql)
    assert result[0]["status"] == FormattedText([
        ('', '1 row in set'),
        ('', ', '),
        ('class:output.status.warning-count', '1 warning'),
    ])
    assert result[0]["status_plain"] == "1 row in set, 1 warning"


@dbtest
def test_conn(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc')""")
    results = run(executor, """select * from test""")

    assert_result_equal(results, header=["a"], rows=[("abc",)])


@dbtest
def test_bools(executor):
    run(executor, """create table test(a boolean)""")
    run(executor, """insert into test values(True)""")
    results = run(executor, """select * from test""")

    assert_result_equal(results, header=["a"], rows=[(1,)])


@dbtest
def test_binary(executor):
    run(executor, """create table bt(geom linestring NOT NULL)""")
    run(executor, "INSERT INTO bt VALUES (ST_GeomFromText('LINESTRING(116.37604 39.73979,116.375 39.73965)'));")
    results = run(executor, """select * from bt""")

    geom = (
        b"\x00\x00\x00\x00\x01\x02\x00\x00\x00\x02\x00\x00\x009\x7f\x13\n"
        b"\x11\x18]@4\xf4Op\xb1\xdeC@\x00\x00\x00\x00\x00\x18]@B>\xe8\xd9"
        b"\xac\xdeC@"
    )

    assert_result_equal(results, header=["geom"], rows=[(geom,)])


@dbtest
def test_table_and_columns_query(executor):
    run(executor, "create table a(x text, y text)")
    run(executor, "create table b(z text)")

    assert set(executor.tables()) == {("a",), ("b",)}
    assert set(executor.table_columns()) == {("a", "x"), ("a", "y"), ("b", "z")}


@dbtest
def test_database_list(executor):
    databases = executor.databases()
    assert TEST_DATABASE in databases


@dbtest
def test_invalid_syntax(executor):
    with pytest.raises(pymysql.ProgrammingError) as excinfo:
        run(executor, "invalid syntax!")
    assert "You have an error in your SQL syntax;" in str(excinfo.value)


@dbtest
def test_invalid_column_name(executor):
    with pytest.raises(pymysql.err.OperationalError) as excinfo:
        run(executor, "select invalid command")
    assert "Unknown column 'invalid' in 'field list'" in str(excinfo.value)


@dbtest
def test_unicode_support_in_output(executor):
    run(executor, "create table unicodechars(t text)")
    run(executor, "insert into unicodechars (t) values ('é')")

    # See issue #24, this raises an exception without proper handling
    results = run(executor, "select * from unicodechars")
    assert_result_equal(results, header=["t"], rows=[("é",)])


@dbtest
def test_multiple_queries_same_line(executor):
    results = run(executor, "select 'foo'; select 'bar'")

    expected = [
        {
            "preamble": None,
            "header": ["foo"],
            "rows": [("foo",)],
            "postamble": None,
            "status_plain": "1 row in set",
            'status': FormattedText([('', '1 row in set')]),
        },
        {
            "preamble": None,
            "header": ["bar"],
            "rows": [("bar",)],
            "postamble": None,
            "status_plain": "1 row in set",
            'status': FormattedText([('', '1 row in set')]),
        },
    ]
    assert expected == results


@dbtest
def test_multiple_queries_same_line_syntaxerror(executor):
    with pytest.raises(pymysql.ProgrammingError) as excinfo:
        run(executor, "select 'foo'; invalid syntax")
    assert "You have an error in your SQL syntax;" in str(excinfo.value)


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query(executor, monkeypatch):
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', iocommands.favoritequeries, raising=False)
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor, "\\fs test-a select * from test where a like 'a%'")
    assert_result_equal(results, status="Saved.", status_plain="Saved.")

    results = run(executor, "\\f test-a")
    assert_result_equal(results, preamble="> select * from test where a like 'a%'", header=["a"], rows=[("abc",)], auto_status=False)

    results = run(executor, "\\fd test-a")
    assert_result_equal(results, status="test-a: Deleted.", status_plain="test-a: Deleted.")


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query_multiple_statement(executor, monkeypatch):
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', iocommands.favoritequeries, raising=False)
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor, "\\fs test-ad select * from test where a like 'a%'; select * from test where a like 'd%'")
    assert_result_equal(results, status="Saved.", status_plain="Saved.")

    results = run(executor, "\\f test-ad")
    expected = [
        {
            "preamble": "> select * from test where a like 'a%'",
            "header": ["a"],
            "rows": [("abc",)],
            "postamble": None,
            "status": None,
            "status_plain": None,
        },
        {
            "preamble": "> select * from test where a like 'd%'",
            "header": ["a"],
            "rows": [("def",)],
            "postamble": None,
            "status": None,
            "status_plain": None,
        },
    ]
    assert expected == results

    results = run(executor, "\\fd test-ad")
    assert_result_equal(results, status="test-ad: Deleted.", status_plain="test-ad: Deleted.")


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query_expanded_output(executor, monkeypatch):
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', iocommands.favoritequeries, raising=False)
    set_expanded_output(False)
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc')""")

    results = run(executor, "\\fs test-ae select * from test")
    assert_result_equal(results, status="Saved.", status_plain="Saved.")

    results = run(executor, "\\f test-ae \\G")
    assert is_expanded_output() is True
    assert_result_equal(results, preamble="> select * from test", header=["a"], rows=[("abc",)], auto_status=False)

    set_expanded_output(False)

    results = run(executor, "\\fd test-ae")
    assert_result_equal(results, status="test-ae: Deleted.", status_plain="test-ae: Deleted.")


@dbtest
def test_collapsed_output_special_command(executor):
    set_expanded_output(True)
    run(executor, "select 1\\g")
    assert is_expanded_output() is False


@dbtest
def test_special_command(executor):
    results = run(executor, "\\?")
    assert_result_equal(results, rows=("quit", "\\q", "quit", "Quit."), header="Command", assert_contains=True, auto_status=False)


@dbtest
def test_cd_command_without_a_folder_name(executor):
    results = run(executor, "system cd")
    assert_result_equal(
        results, status="Exactly one directory name must be provided.", status_plain="Exactly one directory name must be provided."
    )


@dbtest
def test_cd_command_with_one_nonexistent_folder_name(executor):
    results = run(executor, 'system cd nonexistent_folder_name')
    assert_result_equal(results, status='No such file or directory', status_plain='No such file or directory')


@dbtest
def test_cd_command_with_one_real_folder_name(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    doc_dir = tmp_path / 'doc'
    doc_dir.mkdir()
    results = run(executor, 'system cd doc')
    # todo would be better to capture stderr but there was a problem with capsys
    assert results[0]['status_plain'] is None


@dbtest
def test_cd_command_with_two_folder_names(executor):
    results = run(executor, "system cd one two")
    assert_result_equal(
        results, status='Exactly one directory name must be provided.', status_plain='Exactly one directory name must be provided.'
    )


@dbtest
def test_cd_command_unbalanced(executor):
    results = run(executor, "system cd 'one")
    assert_result_equal(
        results,
        status='Cannot parse system command: No closing quotation',
        status_plain='Cannot parse system command: No closing quotation',
    )


@dbtest
def test_system_command_not_found(executor):
    results = run(executor, "system xyz")
    if os.name == "nt":
        assert_result_equal(results, status_plain="OSError: The system cannot find the file specified", assert_contains=True)
    else:
        assert_result_equal(results, status_plain="OSError: No such file or directory", assert_contains=True)


@dbtest
def test_system_command_output(executor):
    eol = os.linesep
    results = run(executor, "system echo mycli rocks")
    assert_result_equal(results, preamble=f"mycli rocks{eol}")


@dbtest
def test_cd_command_current_dir(executor):
    test_path = os.path.abspath(os.path.dirname(__file__))
    run(executor, f"system cd {test_path}")
    assert os.getcwd() == test_path


@dbtest
def test_unicode_support(executor):
    results = run(executor, "SELECT '日本語' AS japanese;")
    assert_result_equal(results, header=["japanese"], rows=[("日本語",)])


@dbtest
def test_timestamp_null(executor):
    run(executor, """create table ts_null(a timestamp null)""")
    run(executor, """insert into ts_null values(null)""")
    results = run(executor, """select * from ts_null""")
    assert_result_equal(results, header=["a"], rows=[(None,)])


@dbtest
def test_datetime_null(executor):
    run(executor, """create table dt_null(a datetime null)""")
    run(executor, """insert into dt_null values(null)""")
    results = run(executor, """select * from dt_null""")
    assert_result_equal(results, header=["a"], rows=[(None,)])


@dbtest
def test_date_null(executor):
    run(executor, """create table date_null(a date null)""")
    run(executor, """insert into date_null values(null)""")
    results = run(executor, """select * from date_null""")
    assert_result_equal(results, header=["a"], rows=[(None,)])


@dbtest
def test_time_null(executor):
    run(executor, """create table time_null(a time null)""")
    run(executor, """insert into time_null values(null)""")
    results = run(executor, """select * from time_null""")
    assert_result_equal(results, header=["a"], rows=[(None,)])


@dbtest
def test_multiple_results(executor):
    query = """CREATE PROCEDURE dmtest()
        BEGIN
          SELECT 1;
          SELECT 2;
        END"""
    executor.conn.cursor().execute(query)

    results = run(executor, "call dmtest;")
    expected = [
        {
            "preamble": None,
            "header": ["1"],
            "rows": [(1,)],
            "postamble": None,
            "status_plain": "1 row in set",
            'status': FormattedText([('', '1 row in set')]),
        },
        {
            "preamble": None,
            "header": ["2"],
            "rows": [(2,)],
            "postamble": None,
            "status_plain": "1 row in set",
            'status': FormattedText([('', '1 row in set')]),
        },
    ]
    assert results == expected


@pytest.mark.parametrize(
    "version_string, species, parsed_version_string, version",
    (
        ("5.7.25-TiDB-v6.1.0", "TiDB", "6.1.0", 60100),
        ("8.0.11-TiDB-v7.2.0-alpha-69-g96e9e68daa", "TiDB", "7.2.0", 70200),
        ("5.7.32-35", "Percona", "5.7.32", 50732),
        ("5.7.32-0ubuntu0.18.04.1", "MySQL", "5.7.32", 50732),
        ("10.5.8-MariaDB-1:10.5.8+maria~focal", "MariaDB", "10.5.8", 100508),
        ("5.5.5-10.5.8-MariaDB-1:10.5.8+maria~focal", "MariaDB", "10.5.8", 100508),
        ("5.0.16-pro-nt-log", "MySQL", "5.0.16", 50016),
        ("5.1.5a-alpha", "MySQL", "5.1.5", 50105),
        ("unexpected version string", None, "", 0),
        ("", None, "", 0),
        (None, None, "", 0),
    ),
)
def test_version_parsing(version_string, species, parsed_version_string, version):
    server_info = ServerInfo.from_version_string(version_string)
    assert (server_info.species and server_info.species.name) == species or ServerSpecies.MySQL
    assert server_info.version_str == parsed_version_string
    assert server_info.version == version


@pytest.mark.parametrize(
    'version_string, expected',
    (
        ('5.7.32', 50732),
        ('8.0.11', 80011),
        ('10.5.8', 100508),
    ),
)
def test_calc_mysql_version_value(version_string: str, expected: int) -> None:
    assert ServerInfo.calc_mysql_version_value(version_string) == expected


@pytest.mark.parametrize(
    'version_string',
    (
        None,
        '',
        123,
        '8.0',
        '8.0.11.1',
        'unexpected version string',
    ),
)
def test_calc_mysql_version_value_returns_zero_for_invalid_input(version_string: object) -> None:
    assert ServerInfo.calc_mysql_version_value(version_string) == 0


@pytest.mark.parametrize('version_string', ('8.0.x', '8.x.11', 'x.0.11'))
def test_calc_mysql_version_value_raises_for_non_numeric_parts(version_string: str) -> None:
    with pytest.raises(ValueError):
        ServerInfo.calc_mysql_version_value(version_string)


def test_sqlexecute_import_swallows_optional_dependency_import_errors(monkeypatch) -> None:
    assert sqlexecute.__file__ is not None
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == 'paramiko':
            raise ImportError('missing optional dependency')
        return original_import(name, globals, locals, fromlist, level)

    module_name = 'sqlexecute_importerror_test'
    spec = importlib.util.spec_from_file_location(module_name, Path(sqlexecute.__file__))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(builtins, '__import__', fake_import)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)


@pytest.mark.parametrize(
    ('server_info', 'expected'),
    (
        (ServerInfo(ServerSpecies.MySQL, '8.0.36'), 'MySQL 8.0.36'),
        (ServerInfo(None, '8.0.36'), '8.0.36'),
    ),
)
def test_server_info_string_representation(server_info: ServerInfo, expected: str) -> None:
    assert str(server_info) == expected


@pytest.mark.parametrize(
    'column_type, expected',
    (
        ("enum('small','medium','large')", ["small", "medium", "large"]),
        ("ENUM('yes','no')", ["yes", "no"]),
        ("enum('a,b','c')", ["a,b", "c"]),
        ("enum('it''s','can\\\\t')", ["it's", "can\\t"]),
    ),
)
def test_parse_enum_values(column_type: str, expected: list[str]) -> None:
    assert SQLExecute._parse_enum_values(column_type) == expected


@pytest.mark.parametrize('column_type', ('', 'varchar(255)', "set('a','b')", None))
def test_parse_enum_values_returns_empty_list_for_non_enum_input(column_type: str | None) -> None:
    assert SQLExecute._parse_enum_values(column_type) == []


class DummyConnection:
    def __init__(self, server_version: str, close_error: Exception | None = None) -> None:
        self.server_version = server_version
        self.host = 'initial-host'
        self.port = 3306
        self.close_calls = 0
        self.connect_calls = 0
        self.close_error = close_error

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error

    def connect(self) -> None:
        self.connect_calls += 1


class FakeQueryCursor:
    def __init__(
        self,
        nextset_steps: list[tuple[bool, int, object | None]] | None = None,
    ) -> None:
        self.executed: list[str] = []
        self.rowcount = 1
        self.description: object | None = [('column',)]
        self.warning_count = 0
        self._nextset_steps = list(nextset_steps or [])

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def nextset(self) -> bool:
        if not self._nextset_steps:
            return False

        has_next, rowcount, description = self._nextset_steps.pop(0)
        self.rowcount = rowcount
        self.description = description
        return has_next


class FakeQueryConnection:
    def __init__(self, cursors: list[FakeQueryCursor]) -> None:
        self.cursors = list(cursors)
        self.cursor_calls = 0

    def cursor(self) -> FakeQueryCursor:
        cursor = self.cursors[self.cursor_calls]
        self.cursor_calls += 1
        return cursor


class FakeMetadataCursor:
    def __init__(
        self,
        rows: list[tuple[object, ...]],
        execute_error: Exception | None = None,
    ) -> None:
        self.rows = rows
        self.execute_error = execute_error
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.entered = False
        self.exited = False

    def __enter__(self) -> 'FakeMetadataCursor':
        self.entered = True
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.exited = True

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.executed.append((sql, params))
        if self.execute_error is not None:
            raise self.execute_error

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def fetchone(self) -> tuple[object, ...] | None:
        if self.rows:
            return self.rows[0]
        return None

    def __iter__(self):
        return iter(self.rows)


class FakeMetadataConnection:
    def __init__(self, cursor: FakeMetadataCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeMetadataCursor:
        return self._cursor


class FakeConnectionIdCursor:
    def __init__(self, row: tuple[int] | None) -> None:
        self.row = row

    def fetchone(self) -> tuple[int] | None:
        return self.row


class FakeSelectableConnection:
    def __init__(self) -> None:
        self.selected_databases: list[str] = []

    def select_db(self, db: str) -> None:
        self.selected_databases.append(db)


class FakeSSLContext:
    def __init__(self) -> None:
        self.check_hostname = True
        self.verify_mode = None
        self.minimum_version = None
        self.maximum_version = None
        self.loaded_cert_chain: tuple[str, str | None] | None = None
        self.cipher_string: str | None = None

    def load_cert_chain(self, certfile: str, keyfile: str | None = None) -> None:
        self.loaded_cert_chain = (certfile, keyfile)

    def set_ciphers(self, cipher_string: str) -> None:
        self.cipher_string = cipher_string


def make_executor_for_connect_tests() -> SQLExecute:
    executor = SQLExecute.__new__(SQLExecute)
    executor.dbname = 'stored_db'
    executor.user = 'stored_user'
    executor.password = 'stored_password'
    executor.host = 'stored_host'
    executor.port = 3306
    executor.socket = '/tmp/mysql.sock'
    executor.character_set = 'utf8mb4'
    executor.local_infile = True
    executor.ssl = {'ca': '/stored/ca.pem'}
    executor.server_info = None
    executor.connection_id = None
    executor.ssh_user = 'stored_ssh_user'
    executor.ssh_host = None
    executor.ssh_port = 22
    executor.ssh_password = 'stored_ssh_password'
    executor.ssh_key_filename = '/stored/key.pem'
    executor.init_command = 'select 1'
    executor.unbuffered = False
    executor.sandbox_mode = False
    executor.conn = None
    return executor


def make_executor_for_run_tests(conn: object | None = None) -> SQLExecute:
    executor = SQLExecute.__new__(SQLExecute)
    executor.conn = conn
    return executor


def test_connect_updates_connection_state_and_merges_overrides(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    previous_conn = DummyConnection(
        server_version='5.7.0',
        close_error=pymysql.err.Error(),
    )
    executor.conn = previous_conn

    new_conn = DummyConnection(server_version='8.0.36-0ubuntu0.22.04.1')
    connect_kwargs = {}
    reset_calls = []
    ssl_context = object()
    ssl_params = {'ca': '/override/ca.pem'}

    def fake_connect(**kwargs):
        connect_kwargs.update(kwargs)
        return new_conn

    def fake_create_ssl_ctx(self, sslp):
        assert self is executor
        assert sslp == ssl_params
        return ssl_context

    def fake_reset_connection_id(self) -> None:
        assert self is executor
        reset_calls.append(True)
        self.connection_id = 42

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', fake_connect)
    monkeypatch.setattr(SQLExecute, '_create_ssl_ctx', fake_create_ssl_ctx)
    monkeypatch.setattr(SQLExecute, 'reset_connection_id', fake_reset_connection_id)

    executor.connect(
        database='override_db',
        user='override_user',
        password='override_password',
        host='override_host',
        port=3307,
        character_set='latin1',
        local_infile=False,
        ssl=ssl_params,
        init_command='select 1; select 2',
        unbuffered=True,
    )

    assert connect_kwargs['database'] == 'override_db'
    assert connect_kwargs['user'] == 'override_user'
    assert connect_kwargs['password'] == 'override_password'
    assert connect_kwargs['host'] == 'override_host'
    assert connect_kwargs['port'] == 3307
    assert connect_kwargs['unix_socket'] == '/tmp/mysql.sock'
    assert connect_kwargs['charset'] == 'latin1'
    assert connect_kwargs['local_infile'] is False
    assert connect_kwargs['ssl'] is ssl_context
    assert connect_kwargs['defer_connect'] is False
    assert connect_kwargs['init_command'] == 'select 1; select 2'
    assert connect_kwargs['cursorclass'] is sqlexecute.pymysql.cursors.SSCursor
    assert connect_kwargs['client_flag'] & sqlexecute.pymysql.constants.CLIENT.INTERACTIVE
    assert connect_kwargs['client_flag'] & sqlexecute.pymysql.constants.CLIENT.MULTI_STATEMENTS
    assert connect_kwargs['program_name'] == 'mycli'
    assert previous_conn.close_calls == 1
    assert executor.conn is new_conn
    assert executor.dbname == 'override_db'
    assert executor.user == 'override_user'
    assert executor.password == 'override_password'
    assert executor.host == 'override_host'
    assert executor.port == 3307
    assert executor.socket == '/tmp/mysql.sock'
    assert executor.character_set == 'latin1'
    assert executor.ssl == ssl_params
    assert executor.init_command == 'select 1; select 2'
    assert executor.unbuffered is True
    assert executor.connection_id == 42
    assert reset_calls == [True]
    assert executor.server_info is not None
    assert executor.server_info.version_str == '8.0.36'
    assert executor.server_info.version == 80036


def test_connect_sets_expired_password_flag(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    executor.ssl = None

    new_conn = DummyConnection(server_version='8.0.36-0ubuntu0.22.04.1')
    connect_kwargs = {}

    def fake_connect(**kwargs):
        connect_kwargs.update(kwargs)
        return new_conn

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', fake_connect)
    monkeypatch.setattr(SQLExecute, 'reset_connection_id', lambda self: None)

    executor.connect()

    assert connect_kwargs['client_flag'] & sqlexecute.pymysql.constants.CLIENT.HANDLE_EXPIRED_PASSWORDS
    assert executor.sandbox_mode is False


def test_connect_falls_back_to_sandbox_on_1820(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    executor.ssl = None

    new_conn = DummyConnection(server_version='8.0.36-0ubuntu0.22.04.1')
    call_count = 0
    sandbox_calls = []

    def fake_connect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise pymysql.OperationalError(1820, 'must change password')
        return new_conn

    def fake_connect_sandbox(self, conn):
        sandbox_calls.append(conn)

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', fake_connect)
    monkeypatch.setattr(SQLExecute, '_connect_sandbox', fake_connect_sandbox)

    executor.connect()

    assert call_count == 2
    assert len(sandbox_calls) == 1
    assert executor.sandbox_mode is True
    assert executor.server_info is None
    assert executor.connection_id is None


def test_connect_reraises_non_sandbox_operational_error(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    executor.ssl = None

    def fake_connect(**_kwargs):
        raise pymysql.OperationalError(1045, 'access denied')

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', fake_connect)

    with pytest.raises(pymysql.OperationalError) as exc_info:
        executor.connect()

    assert exc_info.value.args == (1045, 'access denied')


def test_connect_uses_ssh_tunnel_when_ssh_host_is_set(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    executor.ssl = None
    new_conn = DummyConnection(server_version='8.0.36-0ubuntu0.22.04.1')
    connect_kwargs = {}
    tunnel_args = {}
    tunnel_started = []

    class FakeTunnel:
        def __init__(
            self,
            ssh_address_or_host,
            ssh_username=None,
            ssh_pkey=None,
            ssh_password=None,
            remote_bind_address=None,
        ) -> None:
            tunnel_args['ssh_address_or_host'] = ssh_address_or_host
            tunnel_args['ssh_username'] = ssh_username
            tunnel_args['ssh_pkey'] = ssh_pkey
            tunnel_args['ssh_password'] = ssh_password
            tunnel_args['remote_bind_address'] = remote_bind_address
            self.local_bind_host = '127.0.0.1'
            self.local_bind_port = 4406

        def start(self) -> None:
            tunnel_started.append(True)

    def fake_connect(**kwargs):
        connect_kwargs.update(kwargs)
        return new_conn

    def fake_reset_connection_id(self) -> None:
        self.connection_id = 7

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', fake_connect)
    monkeypatch.setattr(SQLExecute, 'reset_connection_id', fake_reset_connection_id)
    monkeypatch.setattr(
        sqlexecute,
        'sshtunnel',
        SimpleNamespace(SSHTunnelForwarder=FakeTunnel),
        raising=False,
    )

    executor.connect(
        host='db.internal',
        port=3308,
        ssh_host='bastion.internal',
        ssh_port=2222,
        ssh_user='alice',
        ssh_password='secret',
        ssh_key_filename='/tmp/id_rsa',
    )

    assert connect_kwargs['host'] == 'db.internal'
    assert connect_kwargs['port'] == 3308
    assert connect_kwargs['defer_connect'] is True
    assert connect_kwargs['init_command'] == 'select 1'
    assert tunnel_args['ssh_address_or_host'] == ('bastion.internal', 2222)
    assert tunnel_args['ssh_username'] == 'alice'
    assert tunnel_args['ssh_pkey'] == '/tmp/id_rsa'
    assert tunnel_args['ssh_password'] == 'secret'
    assert tunnel_args['remote_bind_address'] == ('db.internal', 3308)
    assert tunnel_started == [True]
    assert new_conn.host == '127.0.0.1'
    assert new_conn.port == 4406
    assert new_conn.connect_calls == 1
    assert executor.conn is new_conn
    assert executor.host == 'db.internal'
    assert executor.port == 3308
    assert executor.connection_id == 7


def test_connect_reraises_ssh_tunnel_errors(monkeypatch) -> None:
    executor = make_executor_for_connect_tests()
    executor.ssl = None
    new_conn = DummyConnection(server_version='8.0.36-0ubuntu0.22.04.1')

    class FakeTunnel:
        def __init__(self, *args, **kwargs) -> None:
            self.local_bind_host = '127.0.0.1'
            self.local_bind_port = 4406

        def start(self) -> None:
            raise RuntimeError('tunnel failed')

    monkeypatch.setattr(sqlexecute.pymysql, 'connect', lambda **_kwargs: new_conn)
    monkeypatch.setattr(
        sqlexecute,
        'sshtunnel',
        SimpleNamespace(SSHTunnelForwarder=FakeTunnel),
        raising=False,
    )

    with pytest.raises(RuntimeError, match='tunnel failed'):
        executor.connect(ssh_host='bastion.internal')


def test_connect_sandbox_temporarily_disables_set_character_set() -> None:
    original_calls = []
    connect_observed_stub = []

    class FakeSandboxConnection:
        def set_character_set(self, *args, **kwargs) -> None:
            original_calls.append((args, kwargs))

        def connect(self) -> None:
            self.set_character_set('utf8mb4')
            connect_observed_stub.append(original_calls == [])

    conn = FakeSandboxConnection()
    original_set_character_set = conn.set_character_set

    SQLExecute._connect_sandbox(conn)

    assert connect_observed_stub == [True]
    assert conn.set_character_set == original_set_character_set
    conn.set_character_set('latin1')
    assert original_calls == [(('latin1',), {})]


def test_run_returns_empty_result_for_blank_statement(monkeypatch) -> None:
    split_inputs: list[str] = []

    def fake_split_queries(statement: str):
        split_inputs.append(statement)
        return iter(())

    monkeypatch.setattr(sqlexecute.iocommands, 'split_queries', fake_split_queries)

    executor = make_executor_for_run_tests()

    assert list(executor.run('   \n\t  ')) == [SQLResult()]
    assert split_inputs == ['']


def test_run_does_not_split_favorite_query(monkeypatch) -> None:
    favorite_results = [SQLResult(status='Saved.')]
    favorite_sql = '\\fs test-name select 1; select 2'
    cursor = FakeQueryCursor()
    execute_calls: list[str] = []

    def fake_execute(cur: FakeQueryCursor, sql: str) -> list[SQLResult]:
        assert cur is cursor
        execute_calls.append(sql)
        return favorite_results

    def fail_split_queries(_statement: str):
        raise AssertionError('split_queries() should not be called for favorite queries')

    monkeypatch.setattr(sqlexecute, 'Connection', FakeQueryConnection)
    monkeypatch.setattr(sqlexecute, 'execute', fake_execute)
    monkeypatch.setattr(sqlexecute.iocommands, 'split_queries', fail_split_queries)

    executor = make_executor_for_run_tests(FakeQueryConnection([cursor]))

    assert list(executor.run(favorite_sql)) == favorite_results
    assert execute_calls == [favorite_sql]
    assert cursor.executed == []


def test_run_uses_special_command_results_without_regular_execution(monkeypatch) -> None:
    cursor = FakeQueryCursor()
    special_results = [SQLResult(status='special command')]

    def fake_execute(cur: FakeQueryCursor, sql: str) -> list[SQLResult]:
        assert cur is cursor
        assert sql == '\\dt'
        return special_results

    def fail_get_result(_self: SQLExecute, _cursor: object) -> SQLResult:
        raise AssertionError('get_result() should not be called for handled special commands')

    monkeypatch.setattr(sqlexecute, 'Connection', FakeQueryConnection)
    monkeypatch.setattr(sqlexecute, 'execute', fake_execute)
    monkeypatch.setattr(sqlexecute.iocommands, 'split_queries', lambda statement: iter([statement]))
    monkeypatch.setattr(SQLExecute, 'get_result', fail_get_result)

    executor = make_executor_for_run_tests(FakeQueryConnection([cursor]))

    assert list(executor.run('\\dt')) == special_results
    assert cursor.executed == []


def test_run_falls_back_to_regular_sql_and_handles_output_flags(monkeypatch) -> None:
    cursors = [FakeQueryCursor(), FakeQueryCursor()]
    expanded_values: list[bool] = []
    forced_horizontal_values: list[bool] = []
    get_result_calls: list[list[str]] = []

    def fake_execute(_cur: FakeQueryCursor, _sql: str) -> list[SQLResult]:
        raise sqlexecute.CommandNotFound('not a special command')

    def fake_get_result(_self: SQLExecute, cursor: FakeQueryCursor) -> SQLResult:
        get_result_calls.append(list(cursor.executed))
        return SQLResult(status=f'ran {cursor.executed[-1]}')

    monkeypatch.setattr(sqlexecute, 'Connection', FakeQueryConnection)
    monkeypatch.setattr(sqlexecute, 'execute', fake_execute)
    monkeypatch.setattr(
        sqlexecute.iocommands,
        'split_queries',
        lambda _statement: iter(['select 1\\G', 'select 2\\g']),
    )
    monkeypatch.setattr(
        sqlexecute.iocommands,
        'set_expanded_output',
        lambda value: expanded_values.append(value),
    )
    monkeypatch.setattr(
        sqlexecute.iocommands,
        'set_forced_horizontal_output',
        lambda value: forced_horizontal_values.append(value),
    )
    monkeypatch.setattr(SQLExecute, 'get_result', fake_get_result)

    executor = make_executor_for_run_tests(FakeQueryConnection(cursors))

    results = list(executor.run('select 1; select 2'))

    assert [result.status for result in results] == ['ran select 1', 'ran select 2']
    assert expanded_values == [True, False]
    assert forced_horizontal_values == [True]
    assert [cursor.executed for cursor in cursors] == [['select 1'], ['select 2']]
    assert get_result_calls == [['select 1'], ['select 2']]


def test_run_yields_each_non_empty_result_set_until_nextset_is_false(monkeypatch) -> None:
    cursor = FakeQueryCursor(
        nextset_steps=[
            (True, 1, [('column',)]),
            (False, 1, [('column',)]),
        ]
    )
    get_result_calls: list[int] = []

    def fake_execute(_cur: FakeQueryCursor, _sql: str) -> list[SQLResult]:
        raise sqlexecute.CommandNotFound('not a special command')

    def fake_get_result(_self: SQLExecute, _cursor: FakeQueryCursor) -> SQLResult:
        get_result_calls.append(len(get_result_calls) + 1)
        return SQLResult(status=f'result {len(get_result_calls)}')

    monkeypatch.setattr(sqlexecute, 'Connection', FakeQueryConnection)
    monkeypatch.setattr(sqlexecute, 'execute', fake_execute)
    monkeypatch.setattr(sqlexecute.iocommands, 'split_queries', lambda statement: iter([statement]))
    monkeypatch.setattr(SQLExecute, 'get_result', fake_get_result)

    executor = make_executor_for_run_tests(FakeQueryConnection([cursor]))

    results = list(executor.run('call demo()'))

    assert [result.status for result in results] == ['result 1', 'result 2']
    assert cursor.executed == ['call demo()']
    assert get_result_calls == [1, 2]


def test_run_skips_trailing_empty_result_set_from_nextset(monkeypatch) -> None:
    cursor = FakeQueryCursor(nextset_steps=[(True, 0, None)])
    get_result_calls: list[int] = []

    def fake_execute(_cur: FakeQueryCursor, _sql: str) -> list[SQLResult]:
        raise sqlexecute.CommandNotFound('not a special command')

    def fake_get_result(_self: SQLExecute, _cursor: FakeQueryCursor) -> SQLResult:
        get_result_calls.append(1)
        return SQLResult(status='result 1')

    monkeypatch.setattr(sqlexecute, 'Connection', FakeQueryConnection)
    monkeypatch.setattr(sqlexecute, 'execute', fake_execute)
    monkeypatch.setattr(sqlexecute.iocommands, 'split_queries', lambda statement: iter([statement]))
    monkeypatch.setattr(SQLExecute, 'get_result', fake_get_result)

    executor = make_executor_for_run_tests(FakeQueryConnection([cursor]))

    results = list(executor.run('call demo()'))

    assert [result.status for result in results] == ['result 1']
    assert cursor.executed == ['call demo()']
    assert get_result_calls == [1]


def test_get_result_returns_header_and_row_status_for_result_sets() -> None:
    cursor = FakeQueryCursor()
    cursor.rowcount = 2
    cursor.description = [('name',), ('age',)]
    cursor.warning_count = 0

    executor = make_executor_for_run_tests()

    result = executor.get_result(cursor)

    assert result.preamble is None
    assert result.header == ['name', 'age']
    assert result.rows is cursor
    assert result.postamble is None
    assert result.status_plain == '2 rows in set'


def test_get_result_returns_query_ok_status_when_no_result_set() -> None:
    cursor = FakeQueryCursor()
    cursor.rowcount = 1
    cursor.description = None
    cursor.warning_count = 0

    executor = make_executor_for_run_tests()

    result = executor.get_result(cursor)

    assert result.header is None
    assert result.rows is cursor
    assert result.status_plain == 'Query OK, 1 row affected'


def test_get_result_appends_warning_count_to_status() -> None:
    cursor = FakeQueryCursor()
    cursor.rowcount = 3
    cursor.description = [('name',)]
    cursor.warning_count = 2

    executor = make_executor_for_run_tests()

    result = executor.get_result(cursor)

    assert result.header == ['name']
    assert result.rows is cursor
    assert result.status_plain == '3 rows in set, 2 warnings'


def test_tables_executes_show_tables_query_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('users',), ('orders',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.tables())

    assert result == [('users',), ('orders',)]
    assert cursor.executed == [(SQLExecute.tables_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_tables_returns_empty_generator_when_no_tables_exist(monkeypatch) -> None:
    cursor = FakeMetadataCursor([])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.tables())

    assert result == []
    assert cursor.executed == [(SQLExecute.tables_query, None)]


def test_table_columns_executes_query_with_dbname_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('users', 'id'), ('users', 'email'), ('orders', 'id')])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.table_columns())

    assert result == [('users', 'id'), ('users', 'email'), ('orders', 'id')]
    assert cursor.executed == [(SQLExecute.table_columns_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True


def test_table_columns_returns_empty_generator_when_schema_has_no_tables(monkeypatch) -> None:
    cursor = FakeMetadataCursor([])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'empty_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.table_columns())

    assert result == []
    assert cursor.executed == [(SQLExecute.table_columns_query, ('empty_db',))]


def test_enum_values_executes_query_and_skips_non_enum_columns(monkeypatch) -> None:
    cursor = FakeMetadataCursor([
        ('orders', 'status', "enum('new','paid')"),
        ('orders', 'notes', 'varchar(255)'),
    ])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.enum_values())

    assert result == [('orders', 'status', ['new', 'paid'])]
    assert cursor.executed == [(SQLExecute.enum_values_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True


def test_enum_values_returns_empty_generator_when_no_enum_values_are_found(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('orders', 'notes', 'varchar(255)')])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'empty_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.enum_values())

    assert result == []
    assert cursor.executed == [(SQLExecute.enum_values_query, ('empty_db',))]


def test_foreign_keys_executes_query_with_dbname_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([
        ('orders', 'customer_id', 'customers', 'id'),
        ('order_items', 'order_id', 'orders', 'id'),
    ])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.foreign_keys())

    assert result == [
        ('orders', 'customer_id', 'customers', 'id'),
        ('order_items', 'order_id', 'orders', 'id'),
    ]
    assert cursor.executed == [(SQLExecute.foreign_keys_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True


def test_foreign_keys_returns_empty_generator_and_logs_execute_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=RuntimeError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.foreign_keys())

    assert result == []
    assert cursor.executed == [(SQLExecute.foreign_keys_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No foreign key completions due to RuntimeError('boom')" in caplog.text


def test_databases_executes_show_databases_and_flattens_names(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('mysql',), ('information_schema',), ('app_db',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = executor.databases()

    assert result == ['mysql', 'information_schema', 'app_db']
    assert cursor.executed == [(SQLExecute.databases_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_databases_returns_empty_list_when_no_databases_are_found(monkeypatch) -> None:
    cursor = FakeMetadataCursor([])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = executor.databases()

    assert result == []
    assert cursor.executed == [(SQLExecute.databases_query, None)]


def test_functions_executes_query_with_dbname_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('calculate_total',), ('format_order',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.functions())

    assert result == [('calculate_total',), ('format_order',)]
    assert cursor.executed == [(SQLExecute.functions_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True


def test_functions_returns_empty_generator_when_schema_has_no_functions(monkeypatch) -> None:
    cursor = FakeMetadataCursor([])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'empty_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.functions())

    assert result == []
    assert cursor.executed == [(SQLExecute.functions_query, ('empty_db',))]


def test_procedures_executes_query_with_dbname_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('refresh_orders',), ('archive_orders',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.procedures())

    assert result == [('refresh_orders',), ('archive_orders',)]
    assert cursor.executed == [(SQLExecute.procedures_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True


def test_procedures_yields_empty_tuple_and_logs_database_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=pymysql.DatabaseError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    executor.dbname = 'app_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.procedures())

    assert result == [()]
    assert cursor.executed == [(SQLExecute.procedures_query, ('app_db',))]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No procedure completions due to DatabaseError('boom')" in caplog.text


def test_character_sets_executes_query_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('utf8mb4',), ('latin1',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.character_sets())

    assert result == [('utf8mb4',), ('latin1',)]
    assert cursor.executed == [(SQLExecute.character_sets_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_character_sets_yields_empty_tuple_and_logs_database_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=pymysql.DatabaseError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.character_sets())

    assert result == [()]
    assert cursor.executed == [(SQLExecute.character_sets_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No character_set completions due to DatabaseError('boom')" in caplog.text


def test_collations_executes_query_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('utf8mb4_general_ci',), ('latin1_swedish_ci',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.collations())

    assert result == [('utf8mb4_general_ci',), ('latin1_swedish_ci',)]
    assert cursor.executed == [(SQLExecute.collations_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_collations_yields_empty_tuple_and_logs_database_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=pymysql.DatabaseError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.collations())

    assert result == [()]
    assert cursor.executed == [(SQLExecute.collations_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No collations completions due to DatabaseError('boom')" in caplog.text


def test_show_candidates_executes_query_and_strips_show_prefix(monkeypatch) -> None:
    cursor = FakeMetadataCursor([('SHOW DATABASES',), ('SHOW FULL TABLES',)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.show_candidates())

    assert result == [('DATABASES',), ('FULL TABLES',)]
    assert cursor.executed == [(SQLExecute.show_candidates_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_show_candidates_yields_empty_tuple_and_logs_database_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=pymysql.DatabaseError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.show_candidates())

    assert result == [()]
    assert cursor.executed == [(SQLExecute.show_candidates_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No show completions due to DatabaseError('boom')" in caplog.text


def test_users_executes_query_and_yields_rows(monkeypatch) -> None:
    cursor = FakeMetadataCursor([("'alice'@'localhost'",), ("'bob'@'%'",)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = list(executor.users())

    assert result == [("'alice'@'localhost'",), ("'bob'@'%'",)]
    assert cursor.executed == [(SQLExecute.users_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_users_yields_empty_tuple_and_logs_database_errors(monkeypatch, caplog) -> None:
    cursor = FakeMetadataCursor([], execute_error=pymysql.DatabaseError('boom'))
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = list(executor.users())

    assert result == [()]
    assert cursor.executed == [(SQLExecute.users_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True
    assert "No user completions due to DatabaseError('boom')" in caplog.text


def test_now_returns_database_timestamp_from_first_row(monkeypatch) -> None:
    timestamp = sqlexecute.datetime.datetime(2024, 1, 2, 3, 4, 5)
    cursor = FakeMetadataCursor([(timestamp,)])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))
    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)

    result = executor.now()

    assert result == timestamp
    assert cursor.executed == [(SQLExecute.now_query, None)]
    assert cursor.entered is True
    assert cursor.exited is True


def test_now_falls_back_to_local_datetime_when_query_returns_no_rows(monkeypatch) -> None:
    fallback = sqlexecute.datetime.datetime(2024, 6, 7, 8, 9, 10)
    cursor = FakeMetadataCursor([])
    executor = make_executor_for_run_tests(FakeMetadataConnection(cursor))

    class FakeDateTime:
        @classmethod
        def now(cls) -> sqlexecute.datetime.datetime:
            return fallback

    monkeypatch.setattr(sqlexecute, 'Connection', FakeMetadataConnection)
    monkeypatch.setattr(sqlexecute.datetime, 'datetime', FakeDateTime)

    result = executor.now()

    assert result == fallback
    assert cursor.executed == [(SQLExecute.now_query, None)]


def test_get_connection_id_returns_cached_value_without_reset(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = 123

    def fail_reset_connection_id(self) -> None:
        raise AssertionError('reset_connection_id() should not be called')

    monkeypatch.setattr(SQLExecute, 'reset_connection_id', fail_reset_connection_id)

    assert executor.get_connection_id() == 123


def test_get_connection_id_resets_when_connection_id_is_missing(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = None
    reset_calls: list[bool] = []

    def fake_reset_connection_id(self) -> None:
        reset_calls.append(True)
        self.connection_id = 456

    monkeypatch.setattr(SQLExecute, 'reset_connection_id', fake_reset_connection_id)

    assert executor.get_connection_id() == 456
    assert reset_calls == [True]


def test_reset_connection_id_sets_connection_id_from_query_result(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = None
    run_calls: list[str] = []

    def fake_run(sql: str):
        run_calls.append(sql)
        return [SimpleNamespace(rows=FakeConnectionIdCursor((789,)))]

    monkeypatch.setattr(sqlexecute, 'Cursor', FakeConnectionIdCursor)
    monkeypatch.setattr(executor, 'run', fake_run)

    executor.reset_connection_id()

    assert executor.connection_id == 789
    assert run_calls == ['select connection_id()']


def test_reset_connection_id_sets_minus_one_when_query_returns_no_row(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = None

    monkeypatch.setattr(sqlexecute, 'Cursor', FakeConnectionIdCursor)
    monkeypatch.setattr(
        executor,
        'run',
        lambda _sql: [SimpleNamespace(rows=FakeConnectionIdCursor(None))],
    )

    executor.reset_connection_id()

    assert executor.connection_id == -1


def test_reset_connection_id_leaves_connection_id_unset_when_query_returns_no_results(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = None

    monkeypatch.setattr(executor, 'run', lambda _sql: iter(()))

    executor.reset_connection_id()

    assert executor.connection_id is None


def test_reset_connection_id_sets_minus_one_and_logs_errors_for_invalid_results(monkeypatch, caplog) -> None:
    executor = make_executor_for_run_tests()
    executor.connection_id = None

    monkeypatch.setattr(sqlexecute, 'Cursor', FakeConnectionIdCursor)
    monkeypatch.setattr(executor, 'run', lambda _sql: [SimpleNamespace(rows=object())])

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        executor.reset_connection_id()

    assert executor.connection_id == -1
    assert 'Failed to get connection id:' in caplog.text


def test_change_db_selects_database_and_updates_dbname(monkeypatch) -> None:
    conn = FakeSelectableConnection()
    executor = make_executor_for_run_tests(conn)
    executor.dbname = 'old_db'
    monkeypatch.setattr(sqlexecute, 'Connection', FakeSelectableConnection)

    executor.change_db('new_db')

    assert conn.selected_databases == ['new_db']
    assert executor.dbname == 'new_db'


def test_create_ssl_ctx_without_ca_disables_hostname_check_and_verification(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    ctx = FakeSSLContext()
    create_default_context_calls: list[tuple[str | None, str | None]] = []

    def fake_create_default_context(cafile: str | None = None, capath: str | None = None) -> FakeSSLContext:
        create_default_context_calls.append((cafile, capath))
        return ctx

    monkeypatch.setattr(sqlexecute.ssl, 'create_default_context', fake_create_default_context)

    result = executor._create_ssl_ctx({})

    assert result is ctx
    assert create_default_context_calls == [(None, None)]
    assert ctx.check_hostname is False
    assert ctx.verify_mode == sqlexecute.ssl.CERT_NONE
    assert ctx.minimum_version == sqlexecute.ssl.TLSVersion.TLSv1_2
    assert ctx.maximum_version is None
    assert ctx.loaded_cert_chain is None
    assert ctx.cipher_string is None


def test_create_ssl_ctx_applies_cert_cipher_and_tls_version(monkeypatch) -> None:
    executor = make_executor_for_run_tests()
    ctx = FakeSSLContext()
    create_default_context_calls: list[tuple[str | None, str | None]] = []

    def fake_create_default_context(cafile: str | None = None, capath: str | None = None) -> FakeSSLContext:
        create_default_context_calls.append((cafile, capath))
        return ctx

    monkeypatch.setattr(
        sqlexecute.ssl,
        'create_default_context',
        fake_create_default_context,
    )

    result = executor._create_ssl_ctx({
        'ca': '/tmp/ca.pem',
        'check_hostname': False,
        'cert': '/tmp/client-cert.pem',
        'key': '/tmp/client-key.pem',
        'cipher': 'ECDHE-RSA-AES256-GCM-SHA384',
        'tls_version': 'TLSv1.3',
    })

    assert result is ctx
    assert create_default_context_calls == [('/tmp/ca.pem', None)]
    assert ctx.check_hostname is False
    assert ctx.verify_mode == sqlexecute.ssl.CERT_REQUIRED
    assert ctx.loaded_cert_chain == ('/tmp/client-cert.pem', '/tmp/client-key.pem')
    assert ctx.cipher_string == 'ECDHE-RSA-AES256-GCM-SHA384'
    assert ctx.minimum_version == sqlexecute.ssl.TLSVersion.TLSv1_3
    assert ctx.maximum_version == sqlexecute.ssl.TLSVersion.TLSv1_3


@pytest.mark.parametrize(
    ('tls_version', 'expected_version'),
    (
        ('TLSv1', sqlexecute.ssl.TLSVersion.TLSv1),
        ('TLSv1.1', sqlexecute.ssl.TLSVersion.TLSv1_1),
        ('TLSv1.2', sqlexecute.ssl.TLSVersion.TLSv1_2),
    ),
)
def test_create_ssl_ctx_supports_legacy_tls_version_overrides(monkeypatch, tls_version: str, expected_version) -> None:
    executor = make_executor_for_run_tests()
    ctx = FakeSSLContext()

    monkeypatch.setattr(sqlexecute.ssl, 'create_default_context', lambda **_kwargs: ctx)

    result = executor._create_ssl_ctx({'tls_version': tls_version})

    assert result is ctx
    assert ctx.minimum_version == expected_version
    assert ctx.maximum_version == expected_version


def test_create_ssl_ctx_logs_invalid_tls_version_and_keeps_default_minimum(monkeypatch, caplog) -> None:
    executor = make_executor_for_run_tests()
    ctx = FakeSSLContext()

    monkeypatch.setattr(sqlexecute.ssl, 'create_default_context', lambda **_kwargs: ctx)

    with caplog.at_level('ERROR', logger='mycli.sqlexecute'):
        result = executor._create_ssl_ctx({'tls_version': 'SSLv3'})

    assert result is ctx
    assert ctx.minimum_version == sqlexecute.ssl.TLSVersion.TLSv1_2
    assert ctx.maximum_version is None
    assert 'Invalid tls version: SSLv3' in caplog.text


def test_close_calls_connection_close_when_present() -> None:
    conn = DummyConnection(server_version='8.0.0')
    executor = make_executor_for_run_tests(conn)

    executor.close()

    assert conn.close_calls == 1


def test_close_swallows_pymysql_errors() -> None:
    conn = DummyConnection(server_version='8.0.0', close_error=pymysql.err.Error())
    executor = make_executor_for_run_tests(conn)

    executor.close()

    assert conn.close_calls == 1


def test_close_does_nothing_when_connection_is_none() -> None:
    executor = make_executor_for_run_tests()

    executor.close()

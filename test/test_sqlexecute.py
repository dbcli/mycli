import os

import pymysql
import pytest

from mycli.sqlexecute import ServerInfo, ServerSpecies
from test.utils import dbtest, is_expanded_output, run, set_expanded_output


def assert_result_equal(result, title=None, rows=None, headers=None, status=None, auto_status=True, assert_contains=False):
    """Assert that an sqlexecute.run() result matches the expected values."""
    if status is None and auto_status and rows:
        status = "{} row{} in set".format(len(rows), "s" if len(rows) > 1 else "")
    fields = {"title": title, "rows": rows, "headers": headers, "status": status}

    if assert_contains:
        # Do a loose match on the results using the *in* operator.
        for key, field in fields.items():
            if field:
                assert field in result[0][key]
    else:
        # Do an exact match on the fields.
        assert result == [fields]


@dbtest
def test_conn(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc')""")
    results = run(executor, """select * from test""")

    assert_result_equal(results, headers=["a"], rows=[("abc",)])


@dbtest
def test_bools(executor):
    run(executor, """create table test(a boolean)""")
    run(executor, """insert into test values(True)""")
    results = run(executor, """select * from test""")

    assert_result_equal(results, headers=["a"], rows=[(1,)])


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

    assert_result_equal(results, headers=["geom"], rows=[(geom,)])


@dbtest
def test_table_and_columns_query(executor):
    run(executor, "create table a(x text, y text)")
    run(executor, "create table b(z text)")

    assert set(executor.tables()) == {("a",), ("b",)}
    assert set(executor.table_columns()) == {("a", "x"), ("a", "y"), ("b", "z")}


@dbtest
def test_database_list(executor):
    databases = executor.databases()
    assert "mycli_test_db" in databases


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
    assert_result_equal(results, headers=["t"], rows=[("é",)])


@dbtest
def test_multiple_queries_same_line(executor):
    results = run(executor, "select 'foo'; select 'bar'")

    expected = [
        {"title": None, "headers": ["foo"], "rows": [("foo",)], "status": "1 row in set"},
        {"title": None, "headers": ["bar"], "rows": [("bar",)], "status": "1 row in set"},
    ]
    assert expected == results


@dbtest
def test_multiple_queries_same_line_syntaxerror(executor):
    with pytest.raises(pymysql.ProgrammingError) as excinfo:
        run(executor, "select 'foo'; invalid syntax")
    assert "You have an error in your SQL syntax;" in str(excinfo.value)


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query(executor):
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor, "\\fs test-a select * from test where a like 'a%'")
    assert_result_equal(results, status="Saved.")

    results = run(executor, "\\f test-a")
    assert_result_equal(results, title="> select * from test where a like 'a%'", headers=["a"], rows=[("abc",)], auto_status=False)

    results = run(executor, "\\fd test-a")
    assert_result_equal(results, status="test-a: Deleted")


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query_multiple_statement(executor):
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor, "\\fs test-ad select * from test where a like 'a%'; select * from test where a like 'd%'")
    assert_result_equal(results, status="Saved.")

    results = run(executor, "\\f test-ad")
    expected = [
        {"title": "> select * from test where a like 'a%'", "headers": ["a"], "rows": [("abc",)], "status": None},
        {"title": "> select * from test where a like 'd%'", "headers": ["a"], "rows": [("def",)], "status": None},
    ]
    assert expected == results

    results = run(executor, "\\fd test-ad")
    assert_result_equal(results, status="test-ad: Deleted")


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query_expanded_output(executor):
    set_expanded_output(False)
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc')""")

    results = run(executor, "\\fs test-ae select * from test")
    assert_result_equal(results, status="Saved.")

    results = run(executor, "\\f test-ae \\G")
    assert is_expanded_output() is True
    assert_result_equal(results, title="> select * from test", headers=["a"], rows=[("abc",)], auto_status=False)

    set_expanded_output(False)

    results = run(executor, "\\fd test-ae")
    assert_result_equal(results, status="test-ae: Deleted")


@dbtest
def test_collapsed_output_special_command(executor):
    set_expanded_output(True)
    run(executor, "select 1\\g")
    assert is_expanded_output() is False


@dbtest
def test_special_command(executor):
    results = run(executor, "\\?")
    assert_result_equal(results, rows=("quit", "\\q", "Quit."), headers="Command", assert_contains=True, auto_status=False)


@dbtest
def test_cd_command_without_a_folder_name(executor):
    results = run(executor, "system cd")
    assert_result_equal(results, status="No folder name was provided.")


@dbtest
def test_system_command_not_found(executor):
    results = run(executor, "system xyz")
    if os.name == "nt":
        assert_result_equal(results, status="OSError: The system cannot find the file specified", assert_contains=True)
    else:
        assert_result_equal(results, status="OSError: No such file or directory", assert_contains=True)


@dbtest
def test_system_command_output(executor):
    eol = os.linesep
    test_dir = os.path.abspath(os.path.dirname(__file__))
    test_file_path = os.path.join(test_dir, "test.txt")
    results = run(executor, "system cat {0}".format(test_file_path))
    assert_result_equal(results, status=f"mycli rocks!{eol}")


@dbtest
def test_cd_command_current_dir(executor):
    test_path = os.path.abspath(os.path.dirname(__file__))
    run(executor, "system cd {0}".format(test_path))
    assert os.getcwd() == test_path


@dbtest
def test_unicode_support(executor):
    results = run(executor, "SELECT '日本語' AS japanese;")
    assert_result_equal(results, headers=["japanese"], rows=[("日本語",)])


@dbtest
def test_timestamp_null(executor):
    run(executor, """create table ts_null(a timestamp null)""")
    run(executor, """insert into ts_null values(null)""")
    results = run(executor, """select * from ts_null""")
    assert_result_equal(results, headers=["a"], rows=[(None,)])


@dbtest
def test_datetime_null(executor):
    run(executor, """create table dt_null(a datetime null)""")
    run(executor, """insert into dt_null values(null)""")
    results = run(executor, """select * from dt_null""")
    assert_result_equal(results, headers=["a"], rows=[(None,)])


@dbtest
def test_date_null(executor):
    run(executor, """create table date_null(a date null)""")
    run(executor, """insert into date_null values(null)""")
    results = run(executor, """select * from date_null""")
    assert_result_equal(results, headers=["a"], rows=[(None,)])


@dbtest
def test_time_null(executor):
    run(executor, """create table time_null(a time null)""")
    run(executor, """insert into time_null values(null)""")
    results = run(executor, """select * from time_null""")
    assert_result_equal(results, headers=["a"], rows=[(None,)])


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
        {"title": None, "rows": [(1,)], "headers": ["1"], "status": "1 row in set"},
        {"title": None, "rows": [(2,)], "headers": ["2"], "status": "1 row in set"},
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

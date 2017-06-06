# coding=UTF-8

import os

import pytest
import pymysql

from utils import run, dbtest, set_expanded_output, is_expanded_output


@dbtest
def test_conn(executor):
    run(executor, '''create table test(a text)''')
    run(executor, '''insert into test values('abc')''')
    results = run(executor, '''select * from test''')

    expected = [{'title': None, 'headers': ['a'], 'rows': [('abc',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_bools(executor):
    run(executor, '''create table test(a boolean)''')
    run(executor, '''insert into test values(True)''')
    results = run(executor, '''select * from test''')

    expected = [{'title': None, 'headers': ['a'], 'rows': [(1,)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_binary(executor):
    run(executor, '''create table bt(geom linestring NOT NULL)''')
    run(executor, '''INSERT INTO bt VALUES (GeomFromText('LINESTRING(116.37604 39.73979,116.375 39.73965)'));''')
    results = run(executor, '''select * from bt''')

    expected = [{'title': None, 'headers': ['geom'],
                 'rows': [(b'\x00\x00\x00\x00\x01\x02\x00\x00\x00\x02\x00\x00\x009\x7f\x13\n\x11\x18]@4\xf4Op\xb1\xdeC@\x00\x00\x00\x00\x00\x18]@B>\xe8\xd9\xac\xdeC@',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_table_and_columns_query(executor):
    run(executor, "create table a(x text, y text)")
    run(executor, "create table b(z text)")

    assert set(executor.tables()) == set([('a',), ('b',)])
    assert set(executor.table_columns()) == set(
        [('a', 'x'), ('a', 'y'), ('b', 'z')])


@dbtest
def test_database_list(executor):
    databases = executor.databases()
    assert '_test_db' in databases


@dbtest
def test_invalid_syntax(executor):
    with pytest.raises(pymysql.ProgrammingError) as excinfo:
        run(executor, 'invalid syntax!')
    assert 'You have an error in your SQL syntax;' in str(excinfo.value)


@dbtest
def test_invalid_column_name(executor):
    with pytest.raises(pymysql.InternalError) as excinfo:
        run(executor, 'select invalid command')
    assert "Unknown column 'invalid' in 'field list'" in str(excinfo.value)


@dbtest
def test_unicode_support_in_output(executor):
    run(executor, "create table unicodechars(t text)")
    run(executor, u"insert into unicodechars (t) values ('é')")

    # See issue #24, this raises an exception without proper handling
    results = run(executor, u"select * from unicodechars")
    expected = [{'title': None, 'headers': ['t'], 'rows': [(u'é',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_multiple_queries_same_line(executor):
    results = run(executor, "select 'foo'; select 'bar'")

    expected = [{'title': None, 'headers': ['foo'], 'rows': [('foo',)],
                 'status': '1 row in set'},
                {'title': None, 'headers': ['bar'], 'rows': [('bar',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_multiple_queries_same_line_syntaxerror(executor):
    with pytest.raises(pymysql.ProgrammingError) as excinfo:
        run(executor, "select 'foo'; invalid syntax")
    assert 'You have an error in your SQL syntax;' in str(excinfo.value)


@dbtest
def test_favorite_query(executor):
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor, "\\fs test-a select * from test where a like 'a%'")
    expected = [{'title': None, 'headers': None,
                 'rows': None, 'status': 'Saved.'}]
    assert expected == results

    results = run(executor, "\\f test-a")
    expected = [{'title': "> select * from test where a like 'a%'",
                 'headers': ['a'], 'rows': [('abc',)], 'status': None}]
    assert expected == results

    results = run(executor, "\\fd test-a")
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'test-a: Deleted'}]
    assert expected == results


@dbtest
def test_favorite_query_multiple_statement(executor):
    set_expanded_output(False)
    run(executor, "create table test(a text)")
    run(executor, "insert into test values('abc')")
    run(executor, "insert into test values('def')")

    results = run(executor,
                  "\\fs test-ad select * from test where a like 'a%'; "
                  "select * from test where a like 'd%'")
    expected = [{'title': None, 'headers': None,
                 'rows': None, 'status': 'Saved.'}]
    assert expected == results

    results = run(executor, "\\f test-ad")
    expected = [{'title': "> select * from test where a like 'a%'",
                 'headers': ['a'], 'rows': [('abc',)], 'status': None},
                {'title': "> select * from test where a like 'd%'",
                 'headers': ['a'], 'rows': [('def',)], 'status': None}]
    assert expected == results

    results = run(executor, "\\fd test-ad")
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'test-ad: Deleted'}]
    assert expected == results


@dbtest
def test_favorite_query_expanded_output(executor):
    set_expanded_output(False)
    run(executor, '''create table test(a text)''')
    run(executor, '''insert into test values('abc')''')

    results = run(executor, "\\fs test-ae select * from test")
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'Saved.'}]
    assert expected == results

    results = run(executor, "\\f test-ae \G")
    assert is_expanded_output() is True
    expected = [{'title': '> select * from test', 'headers': ['a'],
                 'rows': [('abc',)], 'status': None}]
    assert expected == results

    set_expanded_output(False)

    results = run(executor, "\\fd test-ae")
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'test-ae: Deleted'}]
    assert expected == results


@dbtest
def test_special_command(executor):
    results = run(executor, '\\?')
    assert results[0]['headers'] == ['Command', 'Shortcut', 'Description']
    assert len(results) == 1


@dbtest
def test_cd_command_without_a_folder_name(executor):
    results = run(executor, 'system cd')
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'No folder name was provided.'}]
    assert expected == results


@dbtest
def test_system_command_not_found(executor):
    results = run(executor, 'system xyz')
    assert 'OSError: No such file or directory' in results[0]['status']
    assert results[0]['title'] is None
    assert results[0]['headers'] is None
    assert results[0]['rows'] is None
    assert len(results) == 1


@dbtest
def test_system_command_output(executor):
    test_file_path = os.path.join(os.path.abspath('.'), 'test', 'test.txt')
    results = run(executor, 'system cat {0}'.format(test_file_path))
    expected = [{'title': None, 'headers': None, 'rows': None,
                 'status': 'mycli rocks!\n'}]
    assert expected == results


@dbtest
def test_cd_command_current_dir(executor):
    test_path = os.path.join(os.path.abspath('.'), 'test')
    run(executor, 'system cd {0}'.format(test_path))
    assert os.getcwd() == test_path


@dbtest
def test_unicode_support(executor):
    results = run(executor, u"SELECT '日本語' AS japanese;")
    expected = [{'title': None, 'headers': ['japanese'], 'rows': [(u'日本語',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_timestamp_null(executor):
    run(executor, '''create table ts_null(a timestamp)''')
    run(executor, '''insert into ts_null values(0)''')
    results = run(executor, '''select * from ts_null''')
    expected = [{'title': None, 'headers': ['a'],
                 'rows': [('0000-00-00 00:00:00',)], 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_datetime_null(executor):
    run(executor, '''create table dt_null(a datetime)''')
    run(executor, '''insert into dt_null values(0)''')
    results = run(executor, '''select * from dt_null''')
    expected = [{'title': None, 'headers': ['a'],
                 'rows': [('0000-00-00 00:00:00',)], 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_date_null(executor):
    run(executor, '''create table date_null(a date)''')
    run(executor, '''insert into date_null values(0)''')
    results = run(executor, '''select * from date_null''')
    expected = [{'title': None, 'headers': ['a'], 'rows': [('0000-00-00',)],
                 'status': '1 row in set'}]
    assert expected == results


@dbtest
def test_time_null(executor):
    run(executor, '''create table time_null(a time)''')
    run(executor, '''insert into time_null values(0)''')
    results = run(executor, '''select * from time_null''')
    expected = [{'title': None, 'headers': ['a'], 'rows': [('00:00:00',)],
                 'status': '1 row in set'}]
    assert expected == results

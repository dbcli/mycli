import pytest
from mycli.packages.parseutils import (
    extract_tables, query_starts_with, queries_start_with, is_destructive, query_has_where_clause,
    is_dropping_database)


def test_empty_string():
    tables = extract_tables('')
    assert tables == []


def test_simple_select_single_table():
    tables = extract_tables('select * from abc')
    assert tables == [(None, 'abc', None)]


def test_simple_select_single_table_schema_qualified():
    tables = extract_tables('select * from abc.def')
    assert tables == [('abc', 'def', None)]


def test_simple_select_multiple_tables():
    tables = extract_tables('select * from abc, def')
    assert sorted(tables) == [(None, 'abc', None), (None, 'def', None)]


def test_simple_select_multiple_tables_schema_qualified():
    tables = extract_tables('select * from abc.def, ghi.jkl')
    assert sorted(tables) == [('abc', 'def', None), ('ghi', 'jkl', None)]


def test_simple_select_with_cols_single_table():
    tables = extract_tables('select a,b from abc')
    assert tables == [(None, 'abc', None)]


def test_simple_select_with_cols_single_table_schema_qualified():
    tables = extract_tables('select a,b from abc.def')
    assert tables == [('abc', 'def', None)]


def test_simple_select_with_cols_multiple_tables():
    tables = extract_tables('select a,b from abc, def')
    assert sorted(tables) == [(None, 'abc', None), (None, 'def', None)]


def test_simple_select_with_cols_multiple_tables_with_schema():
    tables = extract_tables('select a,b from abc.def, def.ghi')
    assert sorted(tables) == [('abc', 'def', None), ('def', 'ghi', None)]


def test_select_with_hanging_comma_single_table():
    tables = extract_tables('select a, from abc')
    assert tables == [(None, 'abc', None)]


def test_select_with_hanging_comma_multiple_tables():
    tables = extract_tables('select a, from abc, def')
    assert sorted(tables) == [(None, 'abc', None), (None, 'def', None)]


def test_select_with_hanging_period_multiple_tables():
    tables = extract_tables('SELECT t1. FROM tabl1 t1, tabl2 t2')
    assert sorted(tables) == [(None, 'tabl1', 't1'), (None, 'tabl2', 't2')]


def test_simple_insert_single_table():
    tables = extract_tables('insert into abc (id, name) values (1, "def")')

    # sqlparse mistakenly assigns an alias to the table
    # assert tables == [(None, 'abc', None)]
    assert tables == [(None, 'abc', 'abc')]


@pytest.mark.xfail
def test_simple_insert_single_table_schema_qualified():
    tables = extract_tables('insert into abc.def (id, name) values (1, "def")')
    assert tables == [('abc', 'def', None)]


def test_simple_update_table():
    tables = extract_tables('update abc set id = 1')
    assert tables == [(None, 'abc', None)]


def test_simple_update_table_with_schema():
    tables = extract_tables('update abc.def set id = 1')
    assert tables == [('abc', 'def', None)]


def test_join_table():
    tables = extract_tables('SELECT * FROM abc a JOIN def d ON a.id = d.num')
    assert sorted(tables) == [(None, 'abc', 'a'), (None, 'def', 'd')]


def test_join_table_schema_qualified():
    tables = extract_tables(
        'SELECT * FROM abc.def x JOIN ghi.jkl y ON x.id = y.num')
    assert tables == [('abc', 'def', 'x'), ('ghi', 'jkl', 'y')]


def test_join_as_table():
    tables = extract_tables('SELECT * FROM my_table AS m WHERE m.a > 5')
    assert tables == [(None, 'my_table', 'm')]


def test_query_starts_with():
    query = 'USE test;'
    assert query_starts_with(query, ('use', )) is True

    query = 'DROP DATABASE test;'
    assert query_starts_with(query, ('use', )) is False


def test_query_starts_with_comment():
    query = '# comment\nUSE test;'
    assert query_starts_with(query, ('use', )) is True


def test_queries_start_with():
    sql = (
        '# comment\n'
        'show databases;'
        'use foo;'
    )
    assert queries_start_with(sql, ('show', 'select')) is True
    assert queries_start_with(sql, ('use', 'drop')) is True
    assert queries_start_with(sql, ('delete', 'update')) is False


def test_is_destructive():
    sql = (
        'use test;\n'
        'show databases;\n'
        'drop database foo;'
    )
    assert is_destructive(sql) is True


def test_is_destructive_update_with_where_clause():
    sql = (
        'use test;\n'
        'show databases;\n'
        'UPDATE test SET x = 1 WHERE id = 1;'
    )
    assert is_destructive(sql) is False


def test_is_destructive_update_without_where_clause():
    sql = (
        'use test;\n'
        'show databases;\n'
        'UPDATE test SET x = 1;'
    )
    assert is_destructive(sql) is True


@pytest.mark.parametrize(
    ('sql', 'has_where_clause'),
    [
        ('update test set dummy = 1;', False),
        ('update test set dummy = 1 where id = 1);', True),
    ],
)
def test_query_has_where_clause(sql, has_where_clause):
    assert query_has_where_clause(sql) is has_where_clause


@pytest.mark.parametrize(
    ('sql', 'dbname', 'is_dropping'),
    [
        ('select bar from foo', 'foo', False),
        ('drop database "foo";', '`foo`', True),
        ('drop schema foo', 'foo', True),
        ('drop schema foo', 'bar', False),
        ('drop database bar', 'foo', False),
        ('drop database foo', None, False),
        ('drop database foo; create database foo', 'foo', False),
        ('drop database foo; create database bar', 'foo', True),
        ('select bar from foo; drop database bazz', 'foo', False),
        ('select bar from foo; drop database bazz', 'bazz', True),
        ('-- dropping database \n '
         'drop -- really dropping \n '
         'schema abc -- now it is dropped',
         'abc',
         True)
    ]
)
def test_is_dropping_database(sql, dbname, is_dropping):
    assert is_dropping_database(sql, dbname) == is_dropping

import pytest
from mycli.packages.parseutils import extract_tables


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

from mycli.packages.completion_engine import suggest_type
import os
import pytest


def sorted_dicts(dicts):
    """input is a list of dicts."""
    return sorted(tuple(x.items()) for x in dicts)


def test_select_suggests_cols_with_visible_table_scope():
    suggestions = suggest_type('SELECT  FROM tabl', 'SELECT ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_select_suggests_cols_with_qualified_table_scope():
    suggestions = suggest_type('SELECT  FROM sch.tabl', 'SELECT ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [('sch', 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


@pytest.mark.parametrize('expression', [
    'SELECT * FROM tabl WHERE ',
    'SELECT * FROM tabl WHERE (',
    'SELECT * FROM tabl WHERE foo = ',
    'SELECT * FROM tabl WHERE bar OR ',
    'SELECT * FROM tabl WHERE foo = 1 AND ',
    'SELECT * FROM tabl WHERE (bar > 10 AND ',
    'SELECT * FROM tabl WHERE (bar AND (baz OR (qux AND (',
    'SELECT * FROM tabl WHERE 10 < ',
    'SELECT * FROM tabl WHERE foo BETWEEN ',
    'SELECT * FROM tabl WHERE foo BETWEEN foo AND ',
])
def test_where_suggests_columns_functions(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


@pytest.mark.parametrize('expression', [
    'SELECT * FROM tabl WHERE foo IN (',
    'SELECT * FROM tabl WHERE foo IN (bar, ',
])
def test_where_in_suggests_columns(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_where_equals_any_suggests_columns_or_keywords():
    text = 'SELECT * FROM tabl WHERE foo = ANY('
    suggestions = suggest_type(text, text)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'}])


def test_lparen_suggests_cols():
    suggestion = suggest_type('SELECT MAX( FROM tbl', 'SELECT MAX(')
    assert suggestion == [
        {'type': 'column', 'tables': [(None, 'tbl', None)]}]


def test_operand_inside_function_suggests_cols1():
    suggestion = suggest_type(
        'SELECT MAX(col1 +  FROM tbl', 'SELECT MAX(col1 + ')
    assert suggestion == [
        {'type': 'column', 'tables': [(None, 'tbl', None)]}]


def test_operand_inside_function_suggests_cols2():
    suggestion = suggest_type(
        'SELECT MAX(col1 + col2 +  FROM tbl', 'SELECT MAX(col1 + col2 + ')
    assert suggestion == [
        {'type': 'column', 'tables': [(None, 'tbl', None)]}]


def test_select_suggests_cols_and_funcs():
    suggestions = suggest_type('SELECT ', 'SELECT ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': []},
        {'type': 'column', 'tables': []},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


@pytest.mark.parametrize('expression', [
    'SELECT * FROM ',
    'INSERT INTO ',
    'COPY ',
    'UPDATE ',
    'DESCRIBE ',
    'DESC ',
    'EXPLAIN ',
    'SELECT * FROM foo JOIN ',
])
def test_expression_suggests_tables_views_and_schemas(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


@pytest.mark.parametrize('expression', [
    'SELECT * FROM sch.',
    'INSERT INTO sch.',
    'COPY sch.',
    'UPDATE sch.',
    'DESCRIBE sch.',
    'DESC sch.',
    'EXPLAIN sch.',
    'SELECT * FROM foo JOIN sch.',
])
def test_expression_suggests_qualified_tables_views_and_schemas(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': 'sch'},
        {'type': 'view', 'schema': 'sch'}])


def test_truncate_suggests_tables_and_schemas():
    suggestions = suggest_type('TRUNCATE ', 'TRUNCATE ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'schema'}])


def test_truncate_suggests_qualified_tables():
    suggestions = suggest_type('TRUNCATE sch.', 'TRUNCATE sch.')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': 'sch'}])


def test_distinct_suggests_cols():
    suggestions = suggest_type('SELECT DISTINCT ', 'SELECT DISTINCT ')
    assert suggestions == [{'type': 'column', 'tables': []}]


def test_col_comma_suggests_cols():
    suggestions = suggest_type('SELECT a, b, FROM tbl', 'SELECT a, b,')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tbl']},
        {'type': 'column', 'tables': [(None, 'tbl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_table_comma_suggests_tables_and_schemas():
    suggestions = suggest_type('SELECT a, b FROM tbl1, ',
                               'SELECT a, b FROM tbl1, ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


def test_into_suggests_tables_and_schemas():
    suggestion = suggest_type('INSERT INTO ', 'INSERT INTO ')
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


def test_insert_into_lparen_suggests_cols():
    suggestions = suggest_type('INSERT INTO abc (', 'INSERT INTO abc (')
    assert suggestions == [{'type': 'column', 'tables': [(None, 'abc', None)]}]


def test_insert_into_lparen_partial_text_suggests_cols():
    suggestions = suggest_type('INSERT INTO abc (i', 'INSERT INTO abc (i')
    assert suggestions == [{'type': 'column', 'tables': [(None, 'abc', None)]}]


def test_insert_into_lparen_comma_suggests_cols():
    suggestions = suggest_type('INSERT INTO abc (id,', 'INSERT INTO abc (id,')
    assert suggestions == [{'type': 'column', 'tables': [(None, 'abc', None)]}]


def test_partially_typed_col_name_suggests_col_names():
    suggestions = suggest_type('SELECT * FROM tabl WHERE col_n',
                               'SELECT * FROM tabl WHERE col_n')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_dot_suggests_cols_of_a_table_or_schema_qualified_table():
    suggestions = suggest_type('SELECT tabl. FROM tabl', 'SELECT tabl.')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'table', 'schema': 'tabl'},
        {'type': 'view', 'schema': 'tabl'},
        {'type': 'function', 'schema': 'tabl'}])


def test_dot_suggests_cols_of_an_alias():
    suggestions = suggest_type('SELECT t1. FROM tabl1 t1, tabl2 t2',
                               'SELECT t1.')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': 't1'},
        {'type': 'view', 'schema': 't1'},
        {'type': 'column', 'tables': [(None, 'tabl1', 't1')]},
        {'type': 'function', 'schema': 't1'}])


def test_dot_col_comma_suggests_cols_or_schema_qualified_table():
    suggestions = suggest_type('SELECT t1.a, t2. FROM tabl1 t1, tabl2 t2',
                               'SELECT t1.a, t2.')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl2', 't2')]},
        {'type': 'table', 'schema': 't2'},
        {'type': 'view', 'schema': 't2'},
        {'type': 'function', 'schema': 't2'}])


@pytest.mark.parametrize('expression', [
    'SELECT * FROM (',
    'SELECT * FROM foo WHERE EXISTS (',
    'SELECT * FROM foo WHERE bar AND NOT EXISTS (',
    'SELECT 1 AS',
])
def test_sub_select_suggests_keyword(expression):
    suggestion = suggest_type(expression, expression)
    assert suggestion == [{'type': 'keyword'}]


@pytest.mark.parametrize('expression', [
    'SELECT * FROM (S',
    'SELECT * FROM foo WHERE EXISTS (S',
    'SELECT * FROM foo WHERE bar AND NOT EXISTS (S',
])
def test_sub_select_partial_text_suggests_keyword(expression):
    suggestion = suggest_type(expression, expression)
    assert suggestion == [{'type': 'keyword'}]


def test_outer_table_reference_in_exists_subquery_suggests_columns():
    q = 'SELECT * FROM foo f WHERE EXISTS (SELECT 1 FROM bar WHERE f.'
    suggestions = suggest_type(q, q)
    assert suggestions == [
        {'type': 'column', 'tables': [(None, 'foo', 'f')]},
        {'type': 'table', 'schema': 'f'},
        {'type': 'view', 'schema': 'f'},
        {'type': 'function', 'schema': 'f'}]


@pytest.mark.parametrize('expression', [
    'SELECT * FROM (SELECT * FROM ',
    'SELECT * FROM foo WHERE EXISTS (SELECT * FROM ',
    'SELECT * FROM foo WHERE bar AND NOT EXISTS (SELECT * FROM ',
])
def test_sub_select_table_name_completion(expression):
    suggestion = suggest_type(expression, expression)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


def test_sub_select_col_name_completion():
    suggestions = suggest_type('SELECT * FROM (SELECT  FROM abc',
                               'SELECT * FROM (SELECT ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['abc']},
        {'type': 'column', 'tables': [(None, 'abc', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


@pytest.mark.xfail
def test_sub_select_multiple_col_name_completion():
    suggestions = suggest_type('SELECT * FROM (SELECT a, FROM abc',
                               'SELECT * FROM (SELECT a, ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'abc', None)]},
        {'type': 'function', 'schema': []}])


def test_sub_select_dot_col_name_completion():
    suggestions = suggest_type('SELECT * FROM (SELECT t. FROM tabl t',
                               'SELECT * FROM (SELECT t.')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl', 't')]},
        {'type': 'table', 'schema': 't'},
        {'type': 'view', 'schema': 't'},
        {'type': 'function', 'schema': 't'}])


@pytest.mark.parametrize('join_type', ['', 'INNER', 'LEFT', 'RIGHT OUTER'])
@pytest.mark.parametrize('tbl_alias', ['', 'foo'])
def test_join_suggests_tables_and_schemas(tbl_alias, join_type):
    text = 'SELECT * FROM abc {0} {1} JOIN '.format(tbl_alias, join_type)
    suggestion = suggest_type(text, text)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


@pytest.mark.parametrize('sql', [
    'SELECT * FROM abc a JOIN def d ON a.',
    'SELECT * FROM abc a JOIN def d ON a.id = d.id AND a.',
])
def test_join_alias_dot_suggests_cols1(sql):
    suggestions = suggest_type(sql, sql)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'abc', 'a')]},
        {'type': 'table', 'schema': 'a'},
        {'type': 'view', 'schema': 'a'},
        {'type': 'function', 'schema': 'a'}])


@pytest.mark.parametrize('sql', [
    'SELECT * FROM abc a JOIN def d ON a.id = d.',
    'SELECT * FROM abc a JOIN def d ON a.id = d.id AND a.id2 = d.',
])
def test_join_alias_dot_suggests_cols2(sql):
    suggestions = suggest_type(sql, sql)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'def', 'd')]},
        {'type': 'table', 'schema': 'd'},
        {'type': 'view', 'schema': 'd'},
        {'type': 'function', 'schema': 'd'}])


@pytest.mark.parametrize('sql', [
    'select a.x, b.y from abc a join bcd b on ',
    'select a.x, b.y from abc a join bcd b on a.id = b.id OR ',
])
def test_on_suggests_aliases(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [{'type': 'alias', 'aliases': ['a', 'b']}]


@pytest.mark.parametrize('sql', [
    'select abc.x, bcd.y from abc join bcd on ',
    'select abc.x, bcd.y from abc join bcd on abc.id = bcd.id AND ',
])
def test_on_suggests_tables(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [{'type': 'alias', 'aliases': ['abc', 'bcd']}]


@pytest.mark.parametrize('sql', [
    'select a.x, b.y from abc a join bcd b on a.id = ',
    'select a.x, b.y from abc a join bcd b on a.id = b.id AND a.id2 = ',
])
def test_on_suggests_aliases_right_side(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [{'type': 'alias', 'aliases': ['a', 'b']}]


@pytest.mark.parametrize('sql', [
    'select abc.x, bcd.y from abc join bcd on ',
    'select abc.x, bcd.y from abc join bcd on abc.id = bcd.id and ',
])
def test_on_suggests_tables_right_side(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [{'type': 'alias', 'aliases': ['abc', 'bcd']}]


@pytest.mark.parametrize('col_list', ['', 'col1, '])
def test_join_using_suggests_common_columns(col_list):
    text = 'select * from abc inner join def using (' + col_list
    assert suggest_type(text, text) == [
        {'type': 'column',
         'tables': [(None, 'abc', None), (None, 'def', None)],
         'drop_unique': True}]


def test_2_statements_2nd_current():
    suggestions = suggest_type('select * from a; select * from ',
                               'select * from a; select * from ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])

    suggestions = suggest_type('select * from a; select  from b',
                               'select * from a; select ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['b']},
        {'type': 'column', 'tables': [(None, 'b', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])

    # Should work even if first statement is invalid
    suggestions = suggest_type('select * from; select * from ',
                               'select * from; select * from ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


def test_2_statements_1st_current():
    suggestions = suggest_type('select * from ; select * from b',
                               'select * from ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])

    suggestions = suggest_type('select  from a; select * from b',
                               'select ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['a']},
        {'type': 'column', 'tables': [(None, 'a', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_3_statements_2nd_current():
    suggestions = suggest_type('select * from a; select * from ; select * from c',
                               'select * from a; select * from ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])

    suggestions = suggest_type('select * from a; select  from b; select * from c',
                               'select * from a; select ')
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'alias', 'aliases': ['b']},
        {'type': 'column', 'tables': [(None, 'b', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'keyword'},
    ])


def test_create_db_with_template():
    suggestions = suggest_type('create database foo with template ',
                               'create database foo with template ')

    assert sorted_dicts(suggestions) == sorted_dicts([{'type': 'database'}])


@pytest.mark.parametrize('initial_text', ['', '    ', '\t \t'])
def test_specials_included_for_initial_completion(initial_text):
    suggestions = suggest_type(initial_text, initial_text)

    assert sorted_dicts(suggestions) == \
        sorted_dicts([{'type': 'keyword'}, {'type': 'special'}])


def test_specials_not_included_after_initial_token():
    suggestions = suggest_type('create table foo (dt d',
                               'create table foo (dt d')

    assert sorted_dicts(suggestions) == sorted_dicts([{'type': 'keyword'}])


def test_drop_schema_qualified_table_suggests_only_tables():
    text = 'DROP TABLE schema_name.table_name'
    suggestions = suggest_type(text, text)
    assert suggestions == [{'type': 'table', 'schema': 'schema_name'}]


@pytest.mark.parametrize('text', [',', '  ,', 'sel ,'])
def test_handle_pre_completion_comma_gracefully(text):
    suggestions = suggest_type(text, text)

    assert iter(suggestions)


def test_cross_join():
    text = 'select * from v1 cross join v2 JOIN v1.id, '
    suggestions = suggest_type(text, text)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
        {'type': 'schema'}])


@pytest.mark.parametrize('expression', [
    'SELECT 1 AS ',
    'SELECT 1 FROM tabl AS ',
])
def test_after_as(expression):
    suggestions = suggest_type(expression, expression)
    assert set(suggestions) == set()


@pytest.mark.parametrize('expression', [
    '\\. ',
    'select 1; \\. ',
    'select 1;\\. ',
    'select 1 ; \\. ',
    'source ',
    'truncate table test; source ',
    'truncate table test ; source ',
    'truncate table test;source ',
])
def test_source_is_file(expression):
    suggestions = suggest_type(expression, expression)
    assert suggestions == [{'type': 'file_name'}]

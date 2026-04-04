# type: ignore

import pytest
import sqlparse
from sqlparse.sql import Identifier, IdentifierList, Token, TokenList
from sqlparse.tokens import DML, Keyword, Punctuation

from mycli.packages import sql_utils
from mycli.packages.sql_utils import (
    extract_columns_from_select,
    extract_from_part,
    extract_table_identifiers,
    extract_tables,
    extract_tables_from_complete_statements,
    find_prev_keyword,
    get_last_select,
    is_destructive,
    is_dropping_database,
    is_mutating,
    is_select,
    is_subselect,
    last_word,
    need_completion_refresh,
    need_completion_reset,
    queries_start_with,
    query_has_where_clause,
    query_is_single_table_update,
    query_starts_with,
)


def test_extract_columns_from_select():
    columns = extract_columns_from_select('SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS')
    assert columns == ['COLUMN_NAME', 'DATA_TYPE', 'IS_NULLABLE', 'COLUMN_DEFAULT']


def test_extract_columns_from_select_empty():
    columns = extract_columns_from_select('')
    assert columns == []


def test_extract_columns_from_select_update():
    columns = extract_columns_from_select('UPDATE table SET value = 1 WHERE id = 1')
    assert columns == []


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
    tables = extract_tables('SELECT * FROM abc.def x JOIN ghi.jkl y ON x.id = y.num')
    assert tables == [('abc', 'def', 'x'), ('ghi', 'jkl', 'y')]


def test_join_as_table():
    tables = extract_tables('SELECT * FROM my_table AS m WHERE m.a > 5')
    assert tables == [(None, 'my_table', 'm')]


def test_extract_tables_from_complete_statements():
    tables = extract_tables_from_complete_statements('SELECT * FROM my_table AS m WHERE m.a > 5')
    assert tables == [(None, 'my_table', 'm')]


def test_extract_tables_from_complete_statements_cte():
    tables = extract_tables_from_complete_statements('WITH my_cte (id, num) AS ( SELECT id, COUNT(1) FROM my_table GROUP BY id ) SELECT *')
    assert tables == [(None, 'my_table', None)]


# this would confuse plain extract_tables() per #1122
def test_extract_tables_from_multiple_complete_statements():
    tables = extract_tables_from_complete_statements(r'\T sql-insert; SELECT * FROM my_table AS m WHERE m.a > 5')
    assert tables == [(None, 'my_table', 'm')]


def test_query_starts_with():
    query = 'USE test;'
    assert query_starts_with(query, ('use',)) is True

    query = 'DROP DATABASE test;'
    assert query_starts_with(query, ('use',)) is False


def test_query_starts_with_comment():
    query = '# comment\nUSE test;'
    assert query_starts_with(query, ('use',)) is True


def test_queries_start_with():
    sql = '# comment\nshow databases;use foo;'
    assert queries_start_with(sql, ['show', 'select']) is True
    assert queries_start_with(sql, ['use', 'drop']) is True
    assert queries_start_with(sql, ['delete', 'update']) is False


@pytest.mark.parametrize(
    ('text', 'include', 'expected'),
    [
        ('abc', 'alphanum_underscore', 'abc'),
        (' abc', 'alphanum_underscore', 'abc'),
        ('', 'alphanum_underscore', ''),
        (' ', 'alphanum_underscore', ''),
        ('abc ', 'alphanum_underscore', ''),
        ('abc def', 'alphanum_underscore', 'def'),
        ('abc def ', 'alphanum_underscore', ''),
        ('abc def;', 'alphanum_underscore', ''),
        ('bac $def', 'alphanum_underscore', 'def'),
        ('bac $def', 'most_punctuations', '$def'),
        (r'bac \def', 'most_punctuations', r'\def'),
        (r'bac \def;', 'most_punctuations', r'\def;'),
        ('bac::def', 'most_punctuations', 'def'),
        ('abc:def', 'many_punctuations', 'def'),
        ('abc.def', 'all_punctuations', 'abc.def'),
    ],
)
def test_last_word(text, include, expected):
    assert last_word(text, include=include) == expected


def test_is_subselect_returns_false_for_non_group_token():
    token = sqlparse.parse('foo')[0].tokens[0]
    assert is_subselect(token) is False


def test_is_subselect_returns_false_for_group_without_dml():
    token = sqlparse.parse('(foo)')[0].tokens[0]
    assert is_subselect(token) is False


def test_is_subselect_returns_true_for_group_with_select():
    token = sqlparse.parse('(select 1)')[0].tokens[0]
    assert is_subselect(token) is True


def test_get_last_select_returns_empty_token_list_without_select():
    parsed = sqlparse.parse('update t set x = 1')[0]
    assert list(get_last_select(parsed).flatten()) == []


def test_get_last_select_returns_single_select_statement():
    parsed = sqlparse.parse('select c1')[0]
    tokens = get_last_select(parsed)
    assert ''.join(token.value for token in tokens.flatten()) == 'select c1'


def test_get_last_select_returns_single_select_statement_with_from():
    parsed = sqlparse.parse('select c1 from')[0]
    tokens = get_last_select(parsed)
    assert ''.join(token.value for token in tokens.flatten()) == 'select c1 from'


def test_get_last_select_returns_last_top_level_select():
    parsed = sqlparse.parse('select c1 union select c2')[0]
    tokens = get_last_select(parsed)
    assert ''.join(token.value for token in tokens.flatten()) == 'select c2'


def test_get_last_select_keeps_outer_select_for_nested_subselect():
    parsed = sqlparse.parse('select c1 from (select c2')[0]
    tokens = get_last_select(parsed)
    assert ''.join(token.value for token in tokens.flatten()) == 'select c2'


def token_values(tokens):
    return [token.value for token in tokens if not getattr(token, 'is_whitespace', False)]


# todo: coverage of stop_at_punctuation parameter
def test_extract_from_part_returns_identifier_after_from():
    parsed = sqlparse.parse('select * from abc')[0]
    tokens = extract_from_part(parsed)
    assert token_values(tokens) == ['abc']


def test_extract_from_part_returns_identifier_list():
    parsed = sqlparse.parse('select * from abc, def')[0]
    tokens = extract_from_part(parsed)
    assert token_values(tokens) == ['abc, def']


def test_extract_from_part_handles_multiple_joins_and_skips_on_clause():
    parsed = sqlparse.parse('select * from abc join def on abc.id = def.id join ghi')[0]
    tokens = extract_from_part(parsed)
    assert token_values(tokens) == ['abc', 'join', 'def', 'ghi']


def test_extract_from_part_recurses_into_subselect_and_stops_at_punctuation():
    parsed = sqlparse.parse('select * from (select * from inner_table), outer_table')[0]
    tokens = extract_from_part(parsed)
    assert token_values(tokens) == ['inner_table']


def test_extract_from_part_stops_at_punctuation_when_requested():
    parsed = TokenList([Token(Keyword, 'FROM'), Token(Punctuation, ','), Token(Keyword, 'SELECT')])
    tokens = extract_from_part(parsed, stop_at_punctuation=True)
    assert token_values(tokens) == []


def test_extract_table_identifiers_handles_identifier_list():
    parsed = sqlparse.parse('select * from abc a, def d')[0]
    token_stream = extract_from_part(parsed)
    assert list(extract_table_identifiers(token_stream)) == [
        (None, 'abc', 'a'),
        (None, 'def', 'd'),
    ]


def test_extract_table_identifiers_handles_schema_qualified_identifier():
    parsed = sqlparse.parse('select * from abc.def x')[0]
    token_stream = extract_from_part(parsed)
    assert list(extract_table_identifiers(token_stream)) == [('abc', 'def', 'x')]


def test_extract_table_identifiers_handles_function_tokens():
    parsed = sqlparse.parse('select * from my_func()')[0]
    token_stream = extract_from_part(parsed)
    assert list(extract_table_identifiers(token_stream)) == [(None, 'my_func', 'my_func')]


def test_extract_table_identifiers_skips_identifier_list_entries_without_identifier_methods():
    class BrokenIdentifierList(IdentifierList):
        def get_identifiers(self):
            return [object()]

    assert list(extract_table_identifiers(iter([BrokenIdentifierList([])]))) == []


def test_extract_table_identifiers_uses_name_when_identifier_has_no_real_name():
    class NamelessIdentifier(Identifier):
        def get_real_name(self):
            return None

        def get_parent_name(self):
            return None

        def get_name(self):
            return 'fallback_name'

        def get_alias(self):
            return None

    assert list(extract_table_identifiers(iter([NamelessIdentifier([])]))) == [
        (None, 'fallback_name', 'fallback_name'),
    ]


@pytest.mark.parametrize(
    ('sql', 'expected_keyword', 'expected_text'),
    [
        ('', None, ''),
        ('foo', None, ''),
        ('select * from foo where bar = 1', 'where', 'select * from foo where'),
        ('select * from foo where a = 1 and b = 2', 'where', 'select * from foo where'),
        ('select * from foo where a between 1 and 2', 'where', 'select * from foo where'),
        ('select count(', '(', 'select count('),
    ],
)
def test_find_prev_keyword(sql, expected_keyword, expected_text):
    token, text = find_prev_keyword(sql)
    assert (token.value if token else None) == expected_keyword
    assert text == expected_text


@pytest.mark.parametrize(
    ('sql', 'is_single_table'),
    [
        ('update test set x = 1', True),
        ('update test t set x = 1', True),
        ('update /* inline comment */ test set x = 1', True),
        ('select 1', False),
        ('', False),
        ('update', False),
        ('update test, foo set x = 1', False),
        ('update test join foo on test.id = foo.id set test.x = 1', False),
    ],
)
def test_query_is_single_table_update(sql, is_single_table):
    assert query_is_single_table_update(sql) is is_single_table


def test_extract_columns_from_select_handles_falsey_last_select(monkeypatch):
    monkeypatch.setattr(sql_utils, 'get_last_select', lambda _parsed: [])
    assert extract_columns_from_select('select 1') == []


def test_extract_columns_from_select_handles_single_identifier(monkeypatch):
    class SingleIdentifier(Identifier):
        def get_real_name(self):
            return 'column_name'

    monkeypatch.setattr(
        sql_utils,
        'get_last_select',
        lambda _parsed: TokenList([Token(DML, 'SELECT'), SingleIdentifier([])]),
    )

    assert extract_columns_from_select('select column_name') == ['column_name']


def test_extract_columns_from_select_ignores_unhandled_identifier_list_entries(monkeypatch):
    class WeirdIdentifierList(IdentifierList):
        def get_identifiers(self):
            return [object()]

    monkeypatch.setattr(
        sql_utils,
        'get_last_select',
        lambda _parsed: TokenList([Token(DML, 'SELECT'), WeirdIdentifierList([])]),
    )

    assert extract_columns_from_select('select 1') == []


def test_extract_columns_from_select_stops_at_keyword_before_collecting_columns(monkeypatch):
    monkeypatch.setattr(
        sql_utils,
        'get_last_select',
        lambda _parsed: TokenList([Token(DML, 'SELECT'), Token(Keyword, 'FROM')]),
    )

    assert extract_columns_from_select('select 1') == []


def test_extract_tables_from_complete_statements_returns_empty_for_falsey_rough_parse(monkeypatch):
    monkeypatch.setattr(sql_utils.sqlparse, 'parse', lambda _sql: [])

    assert extract_tables_from_complete_statements('select * from t') == []


def test_extract_tables_from_complete_statements_skips_cte_table_identifiers(monkeypatch):
    class FakeParentSelect:
        def sql(self):
            return 'WITH cte AS (SELECT 1) SELECT * FROM cte'

    class FakeIdentifier:
        parent_select = FakeParentSelect()
        db = ''
        name = 'cte'
        alias = ''

    class FakeStatement:
        def find_all(self, _table_type):
            return [FakeIdentifier()]

    monkeypatch.setattr(sql_utils.sqlparse, 'parse', lambda _sql: ['stmt'])
    monkeypatch.setattr(sql_utils.sqlglot, 'parse_one', lambda *_args, **_kwargs: FakeStatement())

    assert extract_tables_from_complete_statements('with cte as (select 1) select * from cte') == []


def test_query_is_single_table_update_returns_false_when_parse_result_is_empty(monkeypatch):
    monkeypatch.setattr(sql_utils.sqlparse, 'parse', lambda _sql: [])

    assert query_is_single_table_update('update test set x = 1') is False


def test_is_destructive():
    sql = "use test;\nshow databases;\ndrop database foo;"
    assert is_destructive(["drop"], sql) is True


def test_is_destructive_update_with_where_clause():
    sql = "use test;\nshow databases;\nUPDATE test SET x = 1 WHERE id = 1;"
    assert is_destructive(["update"], sql) is False


def test_is_destructive_update_with_where_clause_and_comment():
    sql = "use test;\nshow databases;\nUPDATE /* inline comment */ test SET x = 1 WHERE id = 1;"
    assert is_destructive(["update"], sql) is False


def test_is_destructive_update_multiple_tables_with_where_clause():
    sql = "use test;\nshow databases;\nUPDATE test, foo SET x = 1 WHERE id = 1;"
    assert is_destructive(["update"], sql) is True


def test_is_destructive_update_without_where_clause():
    sql = "use test;\nshow databases;\nUPDATE test SET x = 1;"
    assert is_destructive(["update"], sql) is True


def test_is_destructive_skips_empty_split_queries(monkeypatch):
    monkeypatch.setattr(sql_utils.sqlparse, 'split', lambda _queries: ['', ''])

    assert is_destructive(['drop'], 'ignored') is False


def test_is_destructive_returns_false_when_no_query_matches_keywords() -> None:
    assert is_destructive(['drop'], 'select 1; show databases;') is False


@pytest.mark.parametrize(
    ("sql", "has_where_clause"),
    [
        ("update test set dummy = 1;", False),
        ("update test set dummy = 1 where id = 1);", True),
    ],
)
def test_query_has_where_clause(sql, has_where_clause):
    assert query_has_where_clause(sql) is has_where_clause


@pytest.mark.parametrize(
    ("sql", "dbname", "is_dropping"),
    [
        ("select bar from foo", "foo", False),
        ('drop database "foo";', "`foo`", True),
        ("drop schema foo", "foo", True),
        ("drop schema foo", "bar", False),
        ("drop database bar", "foo", False),
        ("drop database foo", None, False),
        ("drop database foo; create database foo", "foo", False),
        ("drop database foo; create database bar", "foo", True),
        ("select bar from foo; drop database bazz", "foo", False),
        ("select bar from foo; drop database bazz", "bazz", True),
        ("-- dropping database \n drop -- really dropping \n schema abc -- now it is dropped", "abc", True),
    ],
)
def test_is_dropping_database(sql, dbname, is_dropping):
    assert is_dropping_database(sql, dbname) == is_dropping


def test_is_dropping_database_skips_statements_without_enough_keywords():
    assert is_dropping_database('drop foo', 'foo') is False


@pytest.mark.parametrize(
    ('queries', 'expected'),
    [
        ('select 1;', False),
        ('alter table foo add column bar int;', True),
        ('create table foo (id int);', True),
        ('use foo;', True),
        ('\\r foo localhost root', True),
        ('\\u foo', True),
        ('connect foo localhost root', True),
        ('drop table foo;', True),
        ('rename table foo to bar;', True),
    ],
)
def test_need_completion_refresh(queries, expected):
    assert need_completion_refresh(queries) is expected


def test_need_completion_refresh_ignores_queries_that_fail_to_split(monkeypatch):
    class BrokenQuery:
        def split(self):
            raise RuntimeError('broken')

    monkeypatch.setattr(sql_utils.sqlparse, 'split', lambda _queries: [BrokenQuery(), 'select 1;'])

    assert need_completion_refresh('ignored') is False


@pytest.mark.parametrize(
    ('queries', 'expected'),
    [
        ('select 1;', False),
        ('use foo;', True),
        ('\\u foo', True),
        ('\\r', False),
        ('\\r foo localhost root', True),
        ('connect', False),
        ('connect foo localhost root', True),
    ],
)
def test_need_completion_reset(queries, expected):
    assert need_completion_reset(queries) is expected


def test_need_completion_reset_ignores_queries_that_fail_to_split(monkeypatch):
    class BrokenQuery:
        def split(self):
            raise RuntimeError('broken')

    monkeypatch.setattr(sql_utils.sqlparse, 'split', lambda _queries: [BrokenQuery(), 'select 1;'])

    assert need_completion_reset('ignored') is False


@pytest.mark.parametrize(
    ('status_plain', 'expected'),
    [
        (None, False),
        ('', False),
        ('SELECT 1', False),
        ('INSERT 1', True),
        ('update 3', True),
        ('rename table', True),
    ],
)
def test_is_mutating(status_plain, expected):
    assert is_mutating(status_plain) is expected


@pytest.mark.parametrize(
    ('status_plain', 'expected'),
    [
        (None, False),
        ('', False),
        ('SELECT 1', True),
        ('select rows', True),
        ('UPDATE 1', False),
    ],
)
def test_is_select(status_plain, expected):
    assert is_select(status_plain) is expected

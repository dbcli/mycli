# type: ignore

from types import SimpleNamespace

import pytest
import sqlparse

from mycli.packages import completion_engine, special
from mycli.packages.completion_engine import (
    _aliases,
    _build_suggest_context,
    _charset_suggestion,
    _emit_binary_or_comma,
    _emit_blank_token,
    _emit_character_set,
    _emit_collation,
    _emit_column_for_tables,
    _emit_database,
    _emit_lparen,
    _emit_none_token,
    _emit_nothing,
    _emit_on,
    _emit_procedure,
    _emit_relation_like,
    _emit_relation_name,
    _emit_select_like,
    _emit_show,
    _emit_star,
    _emit_to,
    _emit_user,
    _emit_where_token,
    _enum_value_suggestion,
    _find_doubled_backticks,
    _is_single_or_double_quoted,
    _is_where_or_having,
    _keyword_and_special_suggestions,
    _keyword_suggestions,
    _normalize_token_value,
    _parent_name,
    _parse_suggestion_statement,
    _tables,
    _token_is_binary_or_comma,
    _token_is_blank,
    _token_is_lparen,
    _token_is_none,
    _token_is_relation_keyword,
    _token_value_is,
    _word_starts_with_digit_or_dot,
    _word_starts_with_quote,
    identifies,
    is_inside_quotes,
    suggest_based_on_last_token,
    suggest_special,
    suggest_type,
)


def sorted_dicts(dicts):
    """input is a list of dicts."""
    return sorted(tuple(x.items()) for x in dicts)


def flattened_tokens(text):
    return list(sqlparse.parse(text)[0].flatten())


def value_tokens(*values):
    return [SimpleNamespace(value=value) for value in values]


def empty_identifier():
    return SimpleNamespace(get_parent_name=lambda: None)


def last_non_whitespace_token(text):
    parsed = sqlparse.parse(text)[0]
    return parsed.token_prev(len(parsed.tokens) - 1)[1]


def test_select_suggests_cols_with_visible_table_scope():
    suggestions = suggest_type("SELECT  FROM tabl", "SELECT ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_select_suggests_cols_with_qualified_table_scope():
    suggestions = suggest_type("SELECT  FROM sch.tabl", "SELECT ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [("sch", "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM tabl WHERE ",
        "SELECT * FROM tabl WHERE (",
        "SELECT * FROM tabl WHERE bar OR ",
        "SELECT * FROM tabl WHERE foo = 1 AND ",
        "SELECT * FROM tabl WHERE (bar > 10 AND ",
        "SELECT * FROM tabl WHERE (bar AND (baz OR (qux AND (",
        "SELECT * FROM tabl WHERE 10 < ",
        "SELECT * FROM tabl WHERE foo BETWEEN ",
        "SELECT * FROM tabl WHERE foo BETWEEN foo AND ",
    ],
)
def test_where_suggests_columns_functions(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_where_equals_suggests_enum_values_first():
    expression = "SELECT * FROM tabl WHERE foo = "
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "enum_value", "tables": [(None, "tabl", None)], "column": "foo", "parent": None},
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_enum_value_suggestion_returns_none_without_equals_context():
    expression = 'SELECT * FROM tabl WHERE foo'
    suggestion = _enum_value_suggestion(expression, expression)
    assert suggestion is None


def test_enum_value_suggestion_returns_column_and_tables():
    expression = 'SELECT * FROM tabl WHERE foo = '
    suggestion = _enum_value_suggestion(expression, expression)
    assert suggestion == {
        'type': 'enum_value',
        'tables': [(None, 'tabl', None)],
        'column': 'foo',
        'parent': None,
    }


def test_enum_value_suggestion_handles_qualified_backticked_identifier():
    expression = 'SELECT * FROM sch.tabl WHERE `tabl`.`foo` = '
    suggestion = _enum_value_suggestion(expression, expression)
    assert suggestion == {
        'type': 'enum_value',
        'tables': [('sch', 'tabl', None)],
        'column': '`foo`',
        'parent': '`tabl`',
    }


def test_enum_value_suggestion_returns_none_inside_quotes():
    full_text = 'SELECT * FROM tabl WHERE "foo = '
    text_before_cursor = 'SELECT * FROM tabl WHERE "foo = '
    suggestion = _enum_value_suggestion(text_before_cursor, full_text)
    assert suggestion is None


@pytest.mark.parametrize(
    ('tokens', 'expected'),
    [
        (value_tokens('character', 'set'), [{'type': 'character_set'}]),
        (value_tokens('x', 'character', 'set', ' '), [{'type': 'character_set'}]),
        (value_tokens('collate'), [{'type': 'collation'}]),
        (value_tokens('select', 'foo'), None),
    ],
)
def test_charset_suggestion(tokens, expected):
    assert _charset_suggestion(tokens) == expected


def test_keyword_suggestions():
    assert _keyword_suggestions() == [{'type': 'keyword'}]


def test_keyword_and_special_suggestions():
    assert _keyword_and_special_suggestions() == [{'type': 'keyword'}, {'type': 'special'}]


def test_parse_suggestion_statement_returns_statement_and_nonspace_tokens():
    statement, tokens_wo_space = _parse_suggestion_statement('select  1')
    assert str(statement) == 'select  1'
    assert [token.value for token in tokens_wo_space] == ['select', '1']


def test_parse_suggestion_statement_raises_type_error_for_invalid_input_type():
    with pytest.raises(TypeError):
        _parse_suggestion_statement(None)  # type: ignore[arg-type]


def test_normalize_token_value_handles_string():
    assert _normalize_token_value('SELECT') == 'select'


def test_normalize_token_value_handles_none():
    assert _normalize_token_value(None) is None


def test_normalize_token_value_handles_plain_token():
    token = SimpleNamespace(value='SHOW')
    assert _normalize_token_value(token) == 'show'


def test_normalize_token_value_handles_comparison_token():
    comparison = sqlparse.parse('a.id = d.')[0].tokens[0]
    assert _normalize_token_value(comparison) == 'd.'


def test_build_suggest_context_populates_fields():
    identifier = empty_identifier()
    context = _build_suggest_context(
        'SHOW',
        'show ',
        None,
        'show ',
        identifier,
    )

    assert context.token == 'SHOW'
    assert context.token_value == 'show'
    assert context.text_before_cursor == 'show '
    assert context.word_before_cursor is None
    assert context.full_text == 'show '
    assert context.identifier is identifier
    assert str(context.parsed) == 'show '
    assert [token.value for token in context.tokens_wo_space] == ['show']


def test_build_suggest_context_handles_none_token():
    context = _build_suggest_context(
        None,
        '',
        None,
        '',
        empty_identifier(),
    )

    assert context.token is None
    assert context.token_value is None
    assert str(context.parsed) == ''
    assert context.tokens_wo_space == []


@pytest.mark.parametrize(
    ('text_before_cursor', 'expected'),
    [
        ("select 'foo", True),
        ('select "foo', True),
        ('select `foo', False),
        ('select foo', False),
    ],
)
def test_is_single_or_double_quoted(text_before_cursor, expected):
    context = _build_suggest_context(
        None,
        text_before_cursor,
        None,
        text_before_cursor,
        empty_identifier(),
    )
    assert _is_single_or_double_quoted(context) is expected


def test_parent_name_returns_identifier_parent():
    identifier = SimpleNamespace(get_parent_name=lambda: 'sch')
    context = _build_suggest_context(None, '', None, '', identifier)
    assert _parent_name(context) == 'sch'


def test_parent_name_returns_empty_list_without_parent():
    context = _build_suggest_context(None, '', None, '', empty_identifier())
    assert _parent_name(context) == []


def test_tables_returns_extracted_tables_from_full_text():
    full_text = 'SELECT * FROM abc a, sch.def d'
    context = _build_suggest_context(None, '', None, full_text, empty_identifier())
    assert _tables(context) == [
        (None, 'abc', 'a'),
        ('sch', 'def', 'd'),
    ]


def test_aliases_prefers_alias_and_falls_back_to_table_name():
    tables = [
        (None, 'abc', 'a'),
        ('sch', 'def', ''),
    ]
    assert _aliases(tables) == ['a', 'def']


@pytest.mark.parametrize(
    ('word_before_cursor', 'expected'),
    [
        ('9foo', True),
        ('.foo', True),
        ('foo', False),
        (None, False),
    ],
)
def test_word_starts_with_digit_or_dot(word_before_cursor, expected):
    context = _build_suggest_context(
        None,
        '',
        word_before_cursor,
        '',
        empty_identifier(),
    )
    assert _word_starts_with_digit_or_dot(context) is expected


@pytest.mark.parametrize(
    ('word_before_cursor', 'expected'),
    [
        ("'foo", True),
        ('"foo', True),
        ('foo', False),
        (None, False),
    ],
)
def test_word_starts_with_quote(word_before_cursor, expected):
    context = _build_suggest_context(
        None,
        '',
        word_before_cursor,
        '',
        empty_identifier(),
    )
    assert _word_starts_with_quote(context) is expected


def test_token_is_none_true_for_none_token():
    context = _build_suggest_context(None, '', None, '', empty_identifier())
    assert _token_is_none(context) is True


def test_token_is_none_false_for_non_none_token():
    context = _build_suggest_context('select', '', None, '', empty_identifier())
    assert _token_is_none(context) is False


@pytest.mark.parametrize(
    ('token', 'expected'),
    [
        ('', True),
        ('select', False),
        (None, True),
    ],
)
def test_token_is_blank(token, expected):
    context = _build_suggest_context(token, '', None, '', empty_identifier())
    assert _token_is_blank(context) is expected


@pytest.mark.parametrize(
    ('token', 'values', 'expected'),
    [
        ('select', ('select', 'where'), True),
        ('show', ('select', 'where'), False),
        (None, ('select',), False),
    ],
)
def test_token_value_is(token, values, expected):
    context = _build_suggest_context(token, '', None, '', empty_identifier())
    assert _token_value_is(context, *values) is expected


@pytest.mark.parametrize(
    ('token', 'expected'),
    [
        ('(', True),
        ('any(', True),
        ('select', False),
        (None, False),
    ],
)
def test_token_is_lparen(token, expected):
    context = _build_suggest_context(token, '', None, '', empty_identifier())
    assert _token_is_lparen(context) is expected


@pytest.mark.parametrize(
    ('token', 'text_before_cursor', 'full_text', 'expected'),
    [
        (last_non_whitespace_token('SELECT * FROM foo JOIN '), 'SELECT * FROM foo JOIN ', 'SELECT * FROM foo JOIN ', True),
        ('from', 'from ', 'from ', True),
        ('truncate', 'truncate ', 'truncate ', True),
        ('like', 'like ', 'create table new like ', True),
        ('like', 'like ', 'select * from foo like ', False),
        ('select', 'select ', 'select ', False),
    ],
)
def test_token_is_relation_keyword(token, text_before_cursor, full_text, expected):
    context = _build_suggest_context(token, text_before_cursor, None, full_text, empty_identifier())
    assert _token_is_relation_keyword(context) is expected


@pytest.mark.parametrize(
    ('token', 'expected'),
    [
        (',', True),
        ('=', True),
        ('and', True),
        ('select', False),
        (None, False),
    ],
)
def test_token_is_binary_or_comma(token, expected):
    context = _build_suggest_context(token, '', None, '', empty_identifier())
    assert _token_is_binary_or_comma(context) is expected


def test_emit_none_token():
    context = _build_suggest_context(None, '', None, '', empty_identifier())
    assert _emit_none_token(context) == [{'type': 'keyword'}]


def test_emit_blank_token():
    context = _build_suggest_context('', '', None, '', empty_identifier())
    assert _emit_blank_token(context) == [{'type': 'keyword'}, {'type': 'special'}]


def test_emit_star():
    context = _build_suggest_context('*', '', None, '', empty_identifier())
    assert _emit_star(context) == [{'type': 'keyword'}]


def test_emit_lparen_exists_where():
    text = 'SELECT * FROM foo WHERE EXISTS ('
    context = _build_suggest_context('(', text, None, text, empty_identifier())
    assert _emit_lparen(context) == [{'type': 'keyword'}]


def test_emit_lparen_join_using():
    text = 'select * from abc inner join def using ('
    context = _build_suggest_context('(', text, None, text, empty_identifier())
    assert _emit_lparen(context) == [{'type': 'column', 'tables': [(None, 'abc', None), (None, 'def', None)], 'drop_unique': True}]


def test_emit_lparen_show():
    text = 'SHOW ('
    context = _build_suggest_context('(', text, None, text, empty_identifier())
    assert _emit_lparen(context) == [{'type': 'show'}]


def test_emit_lparen_function_argument_list():
    text = 'SELECT MAX('
    full_text = 'SELECT MAX( FROM tbl'
    context = _build_suggest_context('(', text, None, full_text, empty_identifier())
    assert _emit_lparen(context) == [{'type': 'column', 'tables': [(None, 'tbl', None)]}]


def test_emit_procedure():
    context = _build_suggest_context('call', '', None, '', empty_identifier())
    assert _emit_procedure(context) == [{'type': 'procedure', 'schema': []}]


def test_emit_character_set():
    context = _build_suggest_context('set', '', None, '', empty_identifier())
    assert _emit_character_set(context) == [{'type': 'character_set'}]


def test_emit_column_for_tables():
    full_text = 'SELECT * FROM abc a, sch.def d'
    context = _build_suggest_context('select', '', None, full_text, empty_identifier())
    assert _emit_column_for_tables(context) == [
        {
            'type': 'column',
            'tables': [
                (None, 'abc', 'a'),
                ('sch', 'def', 'd'),
            ],
        }
    ]


def test_emit_nothing():
    context = _build_suggest_context('as', '', None, '', empty_identifier())
    assert _emit_nothing(context) == []


def test_emit_show():
    context = _build_suggest_context('show', '', None, '', empty_identifier())
    assert _emit_show(context) == [{'type': 'show'}]


def test_emit_to_for_change_statement():
    text = 'change master to '
    context = _build_suggest_context('to', text, None, text, empty_identifier())
    assert _emit_to(context) == [{'type': 'change'}]


def test_emit_to_for_non_change_statement():
    text = 'grant all on db.* to '
    context = _build_suggest_context('to', text, None, text, empty_identifier())
    assert _emit_to(context) == [{'type': 'user'}]


def test_emit_user():
    context = _build_suggest_context('user', '', None, '', empty_identifier())
    assert _emit_user(context) == [{'type': 'user'}]


def test_emit_collation():
    context = _build_suggest_context('collate', '', None, '', empty_identifier())
    assert _emit_collation(context) == [{'type': 'collation'}]


@pytest.mark.xfail
def test_emit_select_like_with_parent_filters_tables():
    identifier = SimpleNamespace(get_parent_name=lambda: 't1')
    text = 'SELECT t1.'
    full_text = 'SELECT t1. FROM tabl1 t1, tabl2 t2'
    context = _build_suggest_context('select', text, None, full_text, identifier)
    assert sorted_dicts(_emit_select_like(context)) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl1', 't1')]},
        # xfail because these are also currently returned
        # {'type': 'table', 'schema': 't1'},
        # {'type': 'view', 'schema': 't1'},
        # {'type': 'function', 'schema': 't1'},
    ])


def test_emit_select_like_inside_backticks_adds_keyword():
    text = 'SELECT `a'
    full_text = 'SELECT `a FROM tabl'
    context = _build_suggest_context('select', text, None, full_text, empty_identifier())
    assert sorted_dicts(_emit_select_like(context)) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'keyword'},
    ])


def test_emit_select_like_default():
    text = 'SELECT '
    full_text = 'SELECT  FROM tabl'
    context = _build_suggest_context('select', text, None, full_text, empty_identifier())
    assert sorted_dicts(_emit_select_like(context)) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'introducer'},
        {'type': 'alias', 'aliases': ['tabl']},
    ])


def test_emit_relation_like_with_schema_parent():
    identifier = SimpleNamespace(get_parent_name=lambda: 'sch')
    text = 'INSERT INTO sch.'
    context = _build_suggest_context('into', text, None, text, identifier)
    assert sorted_dicts(_emit_relation_like(context)) == sorted_dicts([
        {'type': 'table', 'schema': 'sch'},
        {'type': 'view', 'schema': 'sch'},
    ])


def test_emit_relation_like_join_adds_database_and_join_flag():
    text = 'SELECT * FROM foo JOIN '
    token = last_non_whitespace_token(text)
    context = _build_suggest_context(token, text, None, text, empty_identifier())
    assert sorted_dicts(_emit_relation_like(context)) == sorted_dicts([
        {'type': 'database'},
        {'type': 'table', 'schema': [], 'join': True},
        {'type': 'view', 'schema': []},
    ])


def test_emit_relation_like_truncate_omits_view():
    text = 'TRUNCATE '
    context = _build_suggest_context('truncate', text, None, text, empty_identifier())
    assert sorted_dicts(_emit_relation_like(context)) == sorted_dicts([
        {'type': 'database'},
        {'type': 'table', 'schema': []},
    ])


def test_emit_relation_name_with_schema_parent():
    identifier = SimpleNamespace(get_parent_name=lambda: 'sch')
    context = _build_suggest_context('table', '', None, '', identifier)
    assert _emit_relation_name(context) == [{'type': 'table', 'schema': 'sch'}]


def test_emit_relation_name_without_schema_parent():
    context = _build_suggest_context('view', '', None, '', empty_identifier())
    assert _emit_relation_name(context) == [{'type': 'schema'}, {'type': 'view', 'schema': []}]


@pytest.mark.xfail
def test_emit_on_with_parent_filters_tables():
    identifier = SimpleNamespace(get_parent_name=lambda: 'a')
    text = 'SELECT * FROM abc a JOIN def d ON a.'
    context = _build_suggest_context('on', text, None, text, identifier)
    assert sorted_dicts(_emit_on(context)) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'abc', 'a')]},
        # xfail because these currently also are returned
        # {'type': 'table', 'schema': 'a'},
        # {'type': 'view', 'schema': 'a'},
        # {'type': 'function', 'schema': 'a'},
    ])


def test_emit_on_without_parent_uses_fk_join_and_aliases():
    text = 'select a.x, b.y from abc a join bcd b on '
    context = _build_suggest_context('on', text, None, text, empty_identifier())
    assert _emit_on(context) == [
        {'type': 'fk_join', 'tables': [(None, 'abc', 'a'), (None, 'bcd', 'b')]},
        {'type': 'alias', 'aliases': ['a', 'b']},
    ]


def test_emit_on_without_visible_tables_adds_database_and_table():
    text = 'grant select on '
    context = _build_suggest_context('on', text, None, text, empty_identifier())
    assert _emit_on(context) == [
        {'type': 'fk_join', 'tables': []},
        {'type': 'alias', 'aliases': []},
        {'type': 'database'},
        {'type': 'table', 'schema': []},
    ]


def test_emit_database():
    context = _build_suggest_context('database', '', None, '', empty_identifier())
    assert _emit_database(context) == [{'type': 'database'}]


def test_emit_where_token_returns_charset_suggestion_when_available(monkeypatch):
    text = 'select * from tabl where foo = '
    where_token = next(token for token in sqlparse.parse(text)[0].tokens if isinstance(token, sqlparse.sql.Where))
    context = _build_suggest_context(where_token, text, None, text, empty_identifier())
    suggestion = [{'type': 'character_set'}]

    monkeypatch.setattr(completion_engine, '_charset_suggestion', lambda _tokens: suggestion)
    monkeypatch.setattr(
        completion_engine,
        'suggest_based_on_last_token',
        lambda *_args: pytest.fail('suggest_based_on_last_token should not be called'),
    )

    assert _emit_where_token(context) == suggestion


def test_emit_where_token_prepends_enum_value_for_where_fallback(monkeypatch):
    text = 'select * from tabl where foo = '
    where_token = next(token for token in sqlparse.parse(text)[0].tokens if isinstance(token, sqlparse.sql.Where))
    context = _build_suggest_context(where_token, text, None, text, empty_identifier())
    prev_keyword = SimpleNamespace(value='where')
    enum_suggestion = {'type': 'enum_value'}
    fallback = [{'type': 'keyword'}]

    monkeypatch.setattr(completion_engine, '_charset_suggestion', lambda _tokens: None)
    monkeypatch.setattr(completion_engine, 'find_prev_keyword', lambda _text: (prev_keyword, 'select * from tabl where '))
    monkeypatch.setattr(completion_engine, '_enum_value_suggestion', lambda _original, _full: enum_suggestion)
    monkeypatch.setattr(completion_engine, 'suggest_based_on_last_token', lambda *_args: fallback)

    assert _emit_where_token(context) == [enum_suggestion] + fallback


def test_emit_where_token_returns_fallback_for_non_where_keyword(monkeypatch):
    text = 'select * from tabl where foo = '
    where_token = next(token for token in sqlparse.parse(text)[0].tokens if isinstance(token, sqlparse.sql.Where))
    context = _build_suggest_context(where_token, text, None, text, empty_identifier())
    fallback = [{'type': 'keyword'}]

    monkeypatch.setattr(completion_engine, '_charset_suggestion', lambda _tokens: None)
    monkeypatch.setattr(
        completion_engine,
        'find_prev_keyword',
        lambda _text: (SimpleNamespace(value='from'), 'select * from tabl '),
    )
    monkeypatch.setattr(completion_engine, '_enum_value_suggestion', lambda _original, _full: {'type': 'enum_value'})
    monkeypatch.setattr(completion_engine, 'suggest_based_on_last_token', lambda *_args: fallback)

    assert _emit_where_token(context) == fallback


def test_emit_binary_or_comma_prepends_enum_value_for_where_fallback(monkeypatch):
    text = 'select * from tabl where foo = '
    context = _build_suggest_context('=', text, None, text, empty_identifier())
    prev_keyword = SimpleNamespace(value='where')
    enum_suggestion = {'type': 'enum_value'}
    fallback = [{'type': 'column', 'tables': [(None, 'tabl', None)]}]

    monkeypatch.setattr(completion_engine, 'find_prev_keyword', lambda _text: (prev_keyword, 'select * from tabl where '))
    monkeypatch.setattr(completion_engine, '_enum_value_suggestion', lambda _original, _full: enum_suggestion)
    monkeypatch.setattr(completion_engine, 'suggest_based_on_last_token', lambda *_args: fallback)

    assert _emit_binary_or_comma(context) == [enum_suggestion] + fallback


def test_emit_binary_or_comma_uses_keyword_fallback_for_nonprogressing_rewind(monkeypatch):
    text = 'select * from tabl where foo = '
    context = _build_suggest_context(',', text, None, text, empty_identifier())
    prev_keyword = SimpleNamespace(value='where')
    fallback = [{'type': 'keyword'}]

    monkeypatch.setattr(completion_engine, 'find_prev_keyword', lambda _text: (prev_keyword, text.rstrip()))
    monkeypatch.setattr(completion_engine, '_enum_value_suggestion', lambda _original, _full: None)
    monkeypatch.setattr(
        completion_engine,
        'suggest_based_on_last_token',
        lambda *_args: pytest.fail('suggest_based_on_last_token should not be called'),
    )
    monkeypatch.setattr(completion_engine, '_keyword_suggestions', lambda: fallback)

    assert _emit_binary_or_comma(context) == fallback


def test_emit_binary_or_comma_returns_rewound_fallback_without_where_enum(monkeypatch):
    text = 'select * from tabl and '
    context = _build_suggest_context('and', text, None, text, empty_identifier())
    fallback = [{'type': 'keyword'}]

    monkeypatch.setattr(
        completion_engine,
        'find_prev_keyword',
        lambda _text: (SimpleNamespace(value='from'), 'select * from '),
    )
    monkeypatch.setattr(completion_engine, '_enum_value_suggestion', lambda _original, _full: {'type': 'enum_value'})
    monkeypatch.setattr(completion_engine, 'suggest_based_on_last_token', lambda *_args: fallback)

    assert _emit_binary_or_comma(context) == fallback


@pytest.mark.parametrize(
    ('token', 'expected'),
    [
        (None, False),
        (SimpleNamespace(value='where'), True),
        (SimpleNamespace(value='HAVING'), True),
        (SimpleNamespace(value='from'), False),
        (SimpleNamespace(value=''), False),
    ],
)
def test_is_where_or_having(token, expected):
    assert _is_where_or_having(token) is expected


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('\\', [{'type': 'special'}]),
        ('use ', [{'type': 'database'}]),
        ('connect ', [{'type': 'database'}]),
        ('\\u ', [{'type': 'database'}]),
        ('\\r ', [{'type': 'database'}]),
        ('tableformat ', [{'type': 'table_format'}]),
        ('redirectformat ', [{'type': 'table_format'}]),
        ('\\T ', [{'type': 'table_format'}]),
        ('\\Tr ', [{'type': 'table_format'}]),
        ('\\f ', [{'type': 'favoritequery'}]),
        ('\\fs ', [{'type': 'favoritequery'}]),
        ('\\fd ', [{'type': 'favoritequery'}]),
        ('\\dt ', [{'type': 'table', 'schema': []}, {'type': 'view', 'schema': []}, {'type': 'schema'}]),
        ('\\dt+ ', [{'type': 'table', 'schema': []}, {'type': 'view', 'schema': []}, {'type': 'schema'}]),
        ('\\. ', [{'type': 'file_name'}]),
        ('source ', [{'type': 'file_name'}]),
        ('\\o ', [{'type': 'file_name'}]),
        ('\\once ', [{'type': 'file_name'}]),
        ('tee ', [{'type': 'file_name'}]),
        ('\\e ', [{'type': 'file_name'}]),
        ('\\edit ', [{'type': 'file_name'}]),
        ('\\llm ', [{'type': 'llm'}]),
        ('\\ai ', [{'type': 'llm'}]),
        ('pager ', [{'type': 'keyword'}, {'type': 'special'}]),
    ],
)
def test_suggest_special(text, expected):
    assert suggest_special(text) == expected


@pytest.mark.parametrize(
    ('token', 'text_before_cursor', 'word_before_cursor', 'full_text', 'expected'),
    [
        (None, '', None, '', [{'type': 'keyword'}]),
        ('', '', None, '', [{'type': 'keyword'}, {'type': 'special'}]),
        ('*', 'select *', None, 'select *', [{'type': 'keyword'}]),
        ('as', 'select 1 as ', None, 'select 1 as ', []),
        ('show', 'show ', None, 'show ', [{'type': 'show'}]),
        ('to', 'grant all on db.* to ', None, 'grant all on db.* to ', [{'type': 'user'}]),
        ('to', 'change master to ', None, 'change master to ', [{'type': 'change'}]),
        ('where', 'select * from tabl where ', '9', 'select * from tabl where ', []),
        ('where', 'select * from tabl where "fo', '"fo', 'select * from tabl where "fo', []),
        ('where', "select * from tabl where 'fo", 'fo', "select * from tabl where 'fo", []),
    ],
)
def test_suggest_based_on_last_token(token, text_before_cursor, word_before_cursor, full_text, expected):
    suggestion = suggest_based_on_last_token(
        token,
        text_before_cursor,
        word_before_cursor,
        full_text,
        empty_identifier(),
    )
    assert suggestion == expected


def test_suggest_based_on_last_token_lparen_in_exists_where_suggests_keyword():
    text = 'SELECT * FROM foo WHERE EXISTS ('
    suggestion = suggest_based_on_last_token('(', text, None, text, empty_identifier())
    assert suggestion == [{'type': 'keyword'}]


def test_suggest_based_on_last_token_lparen_in_where_any_suggests_columns_functions():
    text = 'SELECT * FROM tabl WHERE foo = ANY('
    suggestion = suggest_based_on_last_token('(', text, None, text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'introducer'},
    ])


def test_suggest_based_on_last_token_lparen_after_join_using_suggests_common_columns():
    text = 'select * from abc inner join def using ('
    suggestion = suggest_based_on_last_token('(', text, None, text, empty_identifier())
    assert suggestion == [{'type': 'column', 'tables': [(None, 'abc', None), (None, 'def', None)], 'drop_unique': True}]


def test_suggest_based_on_last_token_lparen_after_select_subquery_suggests_keyword():
    text = 'SELECT * FROM ('
    suggestion = suggest_based_on_last_token('(', text, None, text, empty_identifier())
    assert suggestion == [{'type': 'keyword'}]


def test_suggest_based_on_last_token_lparen_after_show_suggests_show_items():
    text = 'SHOW ('
    suggestion = suggest_based_on_last_token('(', text, None, text, empty_identifier())
    assert suggestion == [{'type': 'show'}]


def test_suggest_based_on_last_token_lparen_in_function_call_suggests_columns():
    text = 'SELECT MAX('
    full_text = 'SELECT MAX( FROM tbl'
    suggestion = suggest_based_on_last_token('(', text, None, full_text, empty_identifier())
    assert suggestion == [{'type': 'column', 'tables': [(None, 'tbl', None)]}]


@pytest.mark.parametrize(
    ('token', 'text_before_cursor', 'full_text', 'expected'),
    [
        ('call', 'call ', 'call ', [{'type': 'procedure', 'schema': []}]),
        ('set', 'character set', 'character set', [{'type': 'character_set'}]),
        ('distinct', 'select distinct ', 'select distinct ', [{'type': 'column', 'tables': []}]),
        ('database', 'drop database ', 'drop database ', [{'type': 'database'}]),
        ('template', 'create database foo with template ', 'create database foo with template ', [{'type': 'database'}]),
        ('collate', 'collate ', 'collate ', [{'type': 'collation'}]),
        ('table', 'drop table ', 'drop table ', [{'type': 'schema'}, {'type': 'table', 'schema': []}]),
        ('view', 'drop view ', 'drop view ', [{'type': 'schema'}, {'type': 'view', 'schema': []}]),
        ('function', 'drop function ', 'drop function ', [{'type': 'schema'}, {'type': 'function', 'schema': []}]),
    ],
)
def test_suggest_based_on_last_token_direct_keyword_branches(token, text_before_cursor, full_text, expected):
    suggestion = suggest_based_on_last_token(token, text_before_cursor, None, full_text, empty_identifier())
    assert suggestion == expected


def test_suggest_based_on_last_token_relation_keyword_with_schema_parent():
    identifier = SimpleNamespace(get_parent_name=lambda: 'sch')
    text = 'INSERT INTO sch.'
    suggestion = suggest_based_on_last_token('into', text, None, text, identifier)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'table', 'schema': 'sch'},
        {'type': 'view', 'schema': 'sch'},
    ])


def test_suggest_based_on_last_token_join_keyword_marks_join_suggestions():
    text = 'SELECT * FROM foo JOIN '
    suggestion = suggest_based_on_last_token(last_non_whitespace_token(text), text, None, text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'database'},
        {'type': 'table', 'schema': [], 'join': True},
        {'type': 'view', 'schema': []},
    ])


def test_suggest_based_on_last_token_like_in_create_table_suggests_relations():
    text = 'CREATE TABLE new LIKE '
    suggestion = suggest_based_on_last_token('like', text, None, text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'database'},
        {'type': 'table', 'schema': []},
        {'type': 'view', 'schema': []},
    ])


@pytest.mark.xfail
def test_suggest_based_on_last_token_select_with_parent_identifier_filters_tables():
    identifier = SimpleNamespace(get_parent_name=lambda: 't1')
    text = 'SELECT t1.'
    full_text = 'SELECT t1. FROM tabl1 t1, tabl2 t2'
    suggestion = suggest_based_on_last_token('select', text, None, full_text, identifier)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl1', 't1')]},
        # xfail because these are currently also returned
        # {'type': 'table', 'schema': 't1'},
        # {'type': 'view', 'schema': 't1'},
        # {'type': 'function', 'schema': 't1'},
    ])


def test_suggest_based_on_last_token_select_inside_backticks_adds_keywords():
    text = 'SELECT `a'
    full_text = 'SELECT `a FROM tabl'
    suggestion = suggest_based_on_last_token('select', text, None, full_text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'keyword'},
    ])


def test_suggest_based_on_last_token_on_without_parent_suggests_fk_join_and_aliases():
    text = 'select a.x, b.y from abc a join bcd b on '
    suggestion = suggest_based_on_last_token('on', text, None, text, empty_identifier())
    assert suggestion == [
        {'type': 'fk_join', 'tables': [(None, 'abc', 'a'), (None, 'bcd', 'b')]},
        {'type': 'alias', 'aliases': ['a', 'b']},
    ]


def test_suggest_based_on_last_token_on_without_tables_adds_database_and_table():
    text = 'grant select on '
    suggestion = suggest_based_on_last_token('on', text, None, text, empty_identifier())
    assert suggestion == [
        {'type': 'fk_join', 'tables': []},
        {'type': 'alias', 'aliases': []},
        {'type': 'database'},
        {'type': 'table', 'schema': []},
    ]


@pytest.mark.xfail
def test_suggest_based_on_last_token_on_with_parent_identifier_filters_tables():
    identifier = SimpleNamespace(get_parent_name=lambda: 'a')
    text = 'SELECT * FROM abc a JOIN def d ON a.'
    suggestion = suggest_based_on_last_token('on', text, None, text, identifier)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'column', 'tables': [(None, 'abc', 'a')]},
        # xfail because these are currently also returned
        # {'type': 'table', 'schema': 'a'},
        # {'type': 'view', 'schema': 'a'},
        # {'type': 'function', 'schema': 'a'},
    ])


def test_suggest_based_on_last_token_binary_operand_in_where_prepends_enum_value():
    text = 'SELECT * FROM tabl WHERE foo = '
    suggestion = suggest_based_on_last_token('=', text, None, text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'enum_value', 'tables': [(None, 'tabl', None)], 'column': 'foo', 'parent': None},
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'introducer'},
    ])


def test_suggest_based_on_last_token_comma_recurses_to_select_suggestions():
    text = 'SELECT a, '
    full_text = 'SELECT a, FROM tabl'
    suggestion = suggest_based_on_last_token(',', text, None, full_text, empty_identifier())
    assert sorted_dicts(suggestion) == sorted_dicts([
        {'type': 'alias', 'aliases': ['tabl']},
        {'type': 'column', 'tables': [(None, 'tabl', None)]},
        {'type': 'function', 'schema': []},
        {'type': 'introducer'},
    ])


def test_suggest_based_on_last_token_nonprogressing_comma_falls_back_to_keyword():
    text = ','
    suggestion = suggest_based_on_last_token(',', text, None, text, empty_identifier())
    assert suggestion == [{'type': 'keyword'}]


@pytest.mark.parametrize(
    ('identifier', 'schema', 'table', 'alias', 'expected'),
    [
        ('t', None, 'tbl', 't', True),
        ('tbl', None, 'tbl', 't', True),
        ('sch.tbl', 'sch', 'tbl', 't', True),
        ('other', 'sch', 'tbl', 't', False),
        ('sch.other', 'sch', 'tbl', 't', False),
        ('tbl', 'sch', 'other', 't', False),
    ],
)
def test_identifies(identifier, schema, table, alias, expected):
    assert identifies(identifier, schema, table, alias) is expected


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM tabl WHERE foo IN (",
        "SELECT * FROM tabl WHERE foo IN (bar, ",
    ],
)
def test_where_in_suggests_columns(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_where_equals_any_suggests_columns_or_keywords():
    text = "SELECT * FROM tabl WHERE foo = ANY("
    suggestions = suggest_type(text, text)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_where_convert_using_suggests_character_set():
    text = 'SELECT * FROM tabl WHERE CONVERT(foo USING '
    suggestions = suggest_type(text, text)
    assert suggestions == [{"type": "character_set"}]


def test_where_cast_character_set_suggests_character_set():
    text = 'SELECT * FROM tabl WHERE CAST(foo AS CHAR CHARACTER SET '
    suggestions = suggest_type(text, text)
    assert suggestions == [{"type": "character_set"}]


def test_lparen_suggests_cols():
    suggestion = suggest_type("SELECT MAX( FROM tbl", "SELECT MAX(")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


def test_operand_inside_function_suggests_cols1():
    suggestion = suggest_type("SELECT MAX(col1 +  FROM tbl", "SELECT MAX(col1 + ")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


def test_operand_inside_function_suggests_cols2():
    suggestion = suggest_type("SELECT MAX(col1 + col2 +  FROM tbl", "SELECT MAX(col1 + col2 + ")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


def test_operand_inside_function_suggests_cols3():
    suggestion = suggest_type("SELECT MAX(col1 ||  FROM tbl", "SELECT MAX(col1 || ")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


def test_operand_inside_function_suggests_cols4():
    suggestion = suggest_type("SELECT MAX(col1 LIKE  FROM tbl", "SELECT MAX(col1 LIKE ")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


def test_operand_inside_function_suggests_cols5():
    suggestion = suggest_type("SELECT MAX(col1 DIV  FROM tbl", "SELECT MAX(col1 DIV ")
    assert suggestion == [{"type": "column", "tables": [(None, "tbl", None)]}]


@pytest.mark.xfail
def test_arrow_op_inside_function_suggests_nothing():
    suggestion = suggest_type("SELECT MAX(col1->  FROM tbl", "SELECT MAX(col1->")
    assert suggestion == []


def test_select_suggests_cols_and_funcs():
    suggestions = suggest_type("SELECT ", "SELECT ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": []},
        {"type": "column", "tables": []},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM ",
        "INSERT INTO ",
        "COPY ",
        "UPDATE ",
        "DESCRIBE ",
        "DESC ",
        "EXPLAIN ",
    ],
)
def test_expression_suggests_tables_views_and_schemas(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
        {"type": "database"},
    ])


def test_join_expression_suggests_tables_views_and_schemas():
    expression = "SELECT * FROM foo JOIN "
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": [], "join": True},
        {"type": "view", "schema": []},
        {"type": "database"},
    ])


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM sch.",
        "INSERT INTO sch.",
        "COPY sch.",
        "UPDATE sch.",
        "DESCRIBE sch.",
        "DESC sch.",
        "EXPLAIN sch.",
    ],
)
def test_expression_suggests_qualified_tables_views_and_schemas(expression):
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": "sch"},
        {"type": "view", "schema": "sch"},
    ])


def test_join_expression_suggests_qualified_tables_views_and_schemas():
    expression = "SELECT * FROM foo JOIN sch."
    suggestions = suggest_type(expression, expression)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": "sch", "join": True},
        {"type": "view", "schema": "sch"},
    ])


def test_truncate_suggests_tables_and_schemas():
    suggestions = suggest_type("TRUNCATE ", "TRUNCATE ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": []},
        {"type": "database"},
    ])


def test_truncate_suggests_qualified_tables():
    suggestions = suggest_type("TRUNCATE sch.", "TRUNCATE sch.")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": "sch"},
    ])


def test_distinct_suggests_cols():
    suggestions = suggest_type("SELECT DISTINCT ", "SELECT DISTINCT ")
    assert suggestions == [{"type": "column", "tables": []}]


def test_col_comma_suggests_cols():
    suggestions = suggest_type("SELECT a, b, FROM tbl", "SELECT a, b,")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tbl"]},
        {"type": "column", "tables": [(None, "tbl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_table_comma_suggests_tables_and_schemas():
    suggestions = suggest_type("SELECT a, b FROM tbl1, ", "SELECT a, b FROM tbl1, ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
    ])


def test_into_suggests_tables_and_schemas():
    suggestion = suggest_type("INSERT INTO ", "INSERT INTO ")
    assert sorted_dicts(suggestion) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
    ])


def test_insert_into_lparen_suggests_cols():
    suggestions = suggest_type("INSERT INTO abc (", "INSERT INTO abc (")
    assert suggestions == [{"type": "column", "tables": [(None, "abc", None)]}]


def test_insert_into_lparen_partial_text_suggests_cols():
    suggestions = suggest_type("INSERT INTO abc (i", "INSERT INTO abc (i")
    assert suggestions == [{"type": "column", "tables": [(None, "abc", None)]}]


def test_insert_into_lparen_comma_suggests_cols():
    suggestions = suggest_type("INSERT INTO abc (id,", "INSERT INTO abc (id,")
    assert suggestions == [{"type": "column", "tables": [(None, "abc", None)]}]


def test_partially_typed_col_name_suggests_col_names():
    suggestions = suggest_type("SELECT * FROM tabl WHERE col_n", "SELECT * FROM tabl WHERE col_n")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["tabl"]},
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_dot_suggests_cols_of_a_table_or_schema_qualified_table():
    suggestions = suggest_type("SELECT tabl. FROM tabl", "SELECT tabl.")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "tabl", None)]},
        {"type": "table", "schema": "tabl"},
        {"type": "view", "schema": "tabl"},
        {"type": "function", "schema": "tabl"},
    ])


def test_dot_suggests_cols_of_an_alias():
    suggestions = suggest_type("SELECT t1. FROM tabl1 t1, tabl2 t2", "SELECT t1.")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": "t1"},
        {"type": "view", "schema": "t1"},
        {"type": "column", "tables": [(None, "tabl1", "t1")]},
        {"type": "function", "schema": "t1"},
    ])


def test_dot_col_comma_suggests_cols_or_schema_qualified_table():
    suggestions = suggest_type("SELECT t1.a, t2. FROM tabl1 t1, tabl2 t2", "SELECT t1.a, t2.")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "tabl2", "t2")]},
        {"type": "table", "schema": "t2"},
        {"type": "view", "schema": "t2"},
        {"type": "function", "schema": "t2"},
    ])


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM (",
        "SELECT * FROM foo WHERE EXISTS (",
        "SELECT * FROM foo WHERE bar AND NOT EXISTS (",
        "SELECT 1 AS",
    ],
)
def test_sub_select_suggests_keyword(expression):
    suggestion = suggest_type(expression, expression)
    assert suggestion == [{"type": "keyword"}]


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM (S",
        "SELECT * FROM foo WHERE EXISTS (S",
        "SELECT * FROM foo WHERE bar AND NOT EXISTS (S",
    ],
)
def test_sub_select_partial_text_suggests_keyword(expression):
    suggestion = suggest_type(expression, expression)
    assert suggestion == [{"type": "keyword"}]


def test_outer_table_reference_in_exists_subquery_suggests_columns():
    q = "SELECT * FROM foo f WHERE EXISTS (SELECT 1 FROM bar WHERE f."
    suggestions = suggest_type(q, q)
    assert suggestions == [
        {"type": "column", "tables": [(None, "foo", "f")]},
        {"type": "table", "schema": "f"},
        {"type": "view", "schema": "f"},
        {"type": "function", "schema": "f"},
    ]


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT * FROM (SELECT * FROM ",
        "SELECT * FROM foo WHERE EXISTS (SELECT * FROM ",
        "SELECT * FROM foo WHERE bar AND NOT EXISTS (SELECT * FROM ",
    ],
)
def test_sub_select_table_name_completion(expression):
    suggestion = suggest_type(expression, expression)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
    ])


def test_sub_select_col_name_completion():
    suggestions = suggest_type("SELECT * FROM (SELECT  FROM abc", "SELECT * FROM (SELECT ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["abc"]},
        {"type": "column", "tables": [(None, "abc", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


@pytest.mark.xfail
def test_sub_select_multiple_col_name_completion():
    suggestions = suggest_type("SELECT * FROM (SELECT a, FROM abc", "SELECT * FROM (SELECT a, ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "abc", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_sub_select_dot_col_name_completion():
    suggestions = suggest_type("SELECT * FROM (SELECT t. FROM tabl t", "SELECT * FROM (SELECT t.")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "tabl", "t")]},
        {"type": "table", "schema": "t"},
        {"type": "view", "schema": "t"},
        {"type": "function", "schema": "t"},
    ])


@pytest.mark.parametrize("join_type", ["", "INNER", "LEFT", "RIGHT OUTER"])
@pytest.mark.parametrize("tbl_alias", ["", "foo"])
def test_join_suggests_tables_and_schemas(tbl_alias, join_type):
    text = f"SELECT * FROM abc {tbl_alias} {join_type} JOIN "
    suggestion = suggest_type(text, text)
    assert sorted_dicts(suggestion) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": [], "join": True},
        {"type": "view", "schema": []},
    ])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM abc a JOIN def d ON a.",
        "SELECT * FROM abc a JOIN def d ON a.id = d.id AND a.",
    ],
)
def test_join_alias_dot_suggests_cols1(sql):
    suggestions = suggest_type(sql, sql)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "abc", "a")]},
        {"type": "table", "schema": "a"},
        {"type": "view", "schema": "a"},
        {"type": "function", "schema": "a"},
    ])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM abc a JOIN def d ON a.id = d.",
        "SELECT * FROM abc a JOIN def d ON a.id = d.id AND a.id2 = d.",
    ],
)
def test_join_alias_dot_suggests_cols2(sql):
    suggestions = suggest_type(sql, sql)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "def", "d")]},
        {"type": "table", "schema": "d"},
        {"type": "view", "schema": "d"},
        {"type": "function", "schema": "d"},
    ])


@pytest.mark.parametrize(
    "sql",
    [
        "select a.x, b.y from abc a join bcd b on ",
        "select a.x, b.y from abc a join bcd b on a.id = b.id OR ",
        "select a.x, b.y from abc a join bcd b on a.id = b.id + ",
        "select a.x, b.y from abc a join bcd b on a.id = b.id < ",
    ],
)
def test_on_suggests_aliases(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [
        {"type": "fk_join", "tables": [(None, "abc", "a"), (None, "bcd", "b")]},
        {"type": "alias", "aliases": ["a", "b"]},
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "select abc.x, bcd.y from abc join bcd on ",
        "select abc.x, bcd.y from abc join bcd on abc.id = bcd.id AND ",
    ],
)
def test_on_suggests_tables(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [
        {"type": "fk_join", "tables": [(None, "abc", None), (None, "bcd", None)]},
        {"type": "alias", "aliases": ["abc", "bcd"]},
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "select a.x, b.y from abc a join bcd b on a.id = ",
        "select a.x, b.y from abc a join bcd b on a.id = b.id AND a.id2 = ",
    ],
)
def test_on_suggests_aliases_right_side(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [
        {"type": "fk_join", "tables": [(None, "abc", "a"), (None, "bcd", "b")]},
        {"type": "alias", "aliases": ["a", "b"]},
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "select abc.x, bcd.y from abc join bcd on ",
        "select abc.x, bcd.y from abc join bcd on abc.id = bcd.id and ",
    ],
)
def test_on_suggests_tables_right_side(sql):
    suggestions = suggest_type(sql, sql)
    assert suggestions == [
        {"type": "fk_join", "tables": [(None, "abc", None), (None, "bcd", None)]},
        {"type": "alias", "aliases": ["abc", "bcd"]},
    ]


@pytest.mark.parametrize("col_list", ["", "col1, "])
def test_join_using_suggests_common_columns(col_list):
    text = "select * from abc inner join def using (" + col_list
    assert suggest_type(text, text) == [{"type": "column", "tables": [(None, "abc", None), (None, "def", None)], "drop_unique": True}]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM abc a JOIN def d ON a.id = d.id JOIN ghi g ON g.",
        "SELECT * FROM abc a JOIN def d ON a.id = d.id AND a.id2 = d.id2 JOIN ghi g ON d.id = g.id AND g.",
    ],
)
def test_two_join_alias_dot_suggests_cols1(sql):
    suggestions = suggest_type(sql, sql)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "column", "tables": [(None, "ghi", "g")]},
        {"type": "table", "schema": "g"},
        {"type": "view", "schema": "g"},
        {"type": "function", "schema": "g"},
    ])


def test_2_statements_2nd_current():
    suggestions = suggest_type("select * from a; select * from ", "select * from a; select * from ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
        {"type": "database"},
    ])

    suggestions = suggest_type("select * from a; select  from b", "select * from a; select ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["b"]},
        {"type": "column", "tables": [(None, "b", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])

    # Should work even if first statement is invalid
    suggestions = suggest_type("select * from; select * from ", "select * from; select * from ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
        {"type": "database"},
    ])


def test_2_statements_1st_current():
    suggestions = suggest_type("select * from ; select * from b", "select * from ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
    ])

    suggestions = suggest_type("select  from a; select * from b", "select ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["a"]},
        {"type": "column", "tables": [(None, "a", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_3_statements_2nd_current():
    suggestions = suggest_type("select * from a; select * from ; select * from c", "select * from a; select * from ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": []},
        {"type": "view", "schema": []},
    ])

    suggestions = suggest_type("select * from a; select  from b; select * from c", "select * from a; select ")
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "alias", "aliases": ["b"]},
        {"type": "column", "tables": [(None, "b", None)]},
        {"type": "function", "schema": []},
        {"type": "introducer"},
    ])


def test_create_db_with_template():
    suggestions = suggest_type("create database foo with template ", "create database foo with template ")

    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "database"}])


@pytest.mark.parametrize("initial_text", ["", "    ", "\t \t"])
def test_specials_included_for_initial_completion(initial_text):
    suggestions = suggest_type(initial_text, initial_text)

    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "keyword"}, {"type": "special"}])


@pytest.mark.parametrize('initial_text', ['REDIRECT'])
def test_specials_included_with_caps(initial_text):
    suggestions = suggest_type(initial_text, initial_text)

    assert sorted_dicts(suggestions) == sorted_dicts([{'type': 'keyword'}, {'type': 'special'}])


def test_specials_not_included_after_initial_token():
    suggestions = suggest_type("create table foo (dt d", "create table foo (dt d")

    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "keyword"}])


def test_drop_schema_qualified_table_suggests_only_tables():
    text = "DROP TABLE schema_name.table_name"
    suggestions = suggest_type(text, text)
    assert suggestions == [{"type": "table", "schema": "schema_name"}]


@pytest.mark.parametrize("text", [",", "  ,", "sel ,"])
def test_handle_pre_completion_comma_gracefully(text):
    suggestions = suggest_type(text, text)

    assert iter(suggestions)


def test_cross_join():
    text = "select * from v1 cross join v2 JOIN v1.id, "
    suggestions = suggest_type(text, text)
    assert sorted_dicts(suggestions) == sorted_dicts([
        {"type": "database"},
        {"type": "table", "schema": [], "join": True},
        {"type": "view", "schema": []},
    ])


@pytest.mark.parametrize(
    "expression",
    [
        "SELECT 1 AS ",
        "SELECT 1 FROM tabl AS ",
    ],
)
def test_after_as(expression):
    suggestions = suggest_type(expression, expression)
    assert set(suggestions) == set()


@pytest.mark.parametrize(
    "expression",
    [
        "\\. ",
        "select 1; \\. ",
        "select 1;\\. ",
        "select 1 ; \\. ",
        "source ",
        "truncate table test; source ",
        "truncate table test ; source ",
        "truncate table test;source ",
    ],
)
def test_source_is_file(expression):
    # "source" has to be registered by hand because that usually happens inside MyCLI in mycli/main.py
    special.register_special_command(..., 'source', '\\. <filename>', 'Execute commands from file.', aliases=['\\.'])
    suggestions = suggest_type(expression, expression)
    assert suggestions == [{"type": "file_name"}]


@pytest.mark.parametrize(
    "expression",
    [
        "\\f ",
    ],
)
def test_favorite_name_suggestion(expression):
    suggestions = suggest_type(expression, expression)
    assert suggestions == [{"type": "favoritequery"}]


def test_order_by():
    text = "select * from foo order by "
    suggestions = suggest_type(text, text)
    assert suggestions == [{"tables": [(None, "foo", None)], "type": "column"}]


def test_quoted_where():
    text = "'where i=';"
    suggestions = suggest_type(text, text)
    assert suggestions == [{"type": "keyword"}]


def test_find_doubled_backticks_none():
    text = 'select `ab`'
    assert _find_doubled_backticks(text) == []


def test_find_doubled_backticks_some():
    text = 'select `a``b`'
    assert _find_doubled_backticks(text) == [9, 10]


def test_inside_quotes_01():
    text = "select '"
    assert is_inside_quotes(text, len(text)) == 'single'


def test_inside_quotes_02():
    text = "select '\\'"
    assert is_inside_quotes(text, len(text)) == 'single'


def test_inside_quotes_03():
    text = "select '`"
    assert is_inside_quotes(text, len(text)) == 'single'


def test_inside_quotes_04():
    text = 'select "'
    assert is_inside_quotes(text, len(text)) == 'double'


def test_inside_quotes_05():
    text = 'select "\\"\''
    assert is_inside_quotes(text, len(text)) == 'double'


def test_inside_quotes_06():
    text = 'select ""'
    assert is_inside_quotes(text, len(text)) is False


@pytest.mark.parametrize(
    ["text", "position", "expected"],
    [
        ("select `'",      len("select `'"),  'backtick'),
        ("select `' ",     len("select `' "), 'backtick'),
        ("select `'",      -1,  'backtick'),
        ("select `'",      -2,  False),
        ('select `ab` ',   -1,  False),
        ('select `ab` ',   -2,  'backtick'),
        ('select `a``b` ', -1,  False),
        ('select `a``b` ', -2,  'backtick'),
        ('select `a``b` ', -3,  'backtick'),
        ('select `a``b` ', -4,  'backtick'),
        ('select `a``b` ', -5,  'backtick'),
        ('select `a``b` ', -6,  'backtick'),
        ('select `a``b` ', -7,  False),
    ]
)  # fmt: skip
def test_inside_quotes_backtick_01(text, position, expected):
    assert is_inside_quotes(text, position) == expected


def test_inside_quotes_backtick_02():
    """Empty backtick pairs are treated as a doubled (escaped) backtick.
    This is okay because it is invalid SQL, and we don't have to complete on it.
    """
    text = 'select ``'
    assert is_inside_quotes(text, -1) is False


def test_inside_quotes_backtick_03():
    """Empty backtick pairs are treated as a doubled (escaped) backtick.
    This is okay because it is invalid SQL, and we don't have to complete on it.
    """
    text = 'select ``'
    assert is_inside_quotes(text, -2) is False

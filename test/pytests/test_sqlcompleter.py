# type: ignore

import re
from types import SimpleNamespace

from prompt_toolkit.document import Document
import pytest

import mycli.sqlcompleter
from mycli.sqlcompleter import Fuzziness, SQLCompleter


def collect_matches(
    orig_text: str,
    collection: list[str],
    *,
    start_only: bool = False,
    fuzzy: bool = True,
    casing: str | None = None,
    text_before_cursor: str = '',
) -> list[tuple[str, int]]:
    completer = SQLCompleter()
    return list(
        completer.find_matches(
            orig_text,
            collection,
            start_only=start_only,
            fuzzy=fuzzy,
            casing=casing,
            text_before_cursor=text_before_cursor,
        )
    )


def make_completer(**kwargs) -> SQLCompleter:
    comp = SQLCompleter(**kwargs)
    comp.keywords = list(comp.keywords)
    comp.functions = list(comp.functions)
    return comp


@pytest.mark.parametrize(
    ('item', 'expected'),
    [
        ('users', '`users`'),
        ('`already`', '`already`'),
        ('*', '*'),
    ],
)
def test_maybe_quote_identifier(item: str, expected: str) -> None:
    completer = SQLCompleter()
    assert completer.maybe_quote_identifier(item) == expected


def test_quote_collection_if_needed_quotes_when_text_starts_with_backtick() -> None:
    completer = SQLCompleter()
    quoted = completer.quote_collection_if_needed('`us', ['users', '*'], '')

    assert quoted == ['`users`', '*']


def test_quote_collection_if_needed_quotes_when_cursor_is_inside_backticks() -> None:
    completer = SQLCompleter()
    quoted = completer.quote_collection_if_needed('us', ['users', '`uuid`'], 'select `us')

    assert quoted == ['`users`', '`uuid`']


def test_quote_collection_if_needed_leaves_collection_unchanged_when_not_quoted() -> None:
    collection = ['users', '*']
    completer = SQLCompleter()
    quoted = completer.quote_collection_if_needed('us', collection, 'select us')

    assert quoted is collection


@pytest.mark.parametrize(
    ('text_parts', 'item_parts', 'expected'),
    [
        (['us', 'de', 'fu'], ['user', 'defined', 'function'], True),
        (['us', 'fu'], ['user', 'defined', 'function'], True),
        (['us', 'zz'], ['user', 'defined', 'function'], False),
        ([], ['user', 'defined', 'function'], True),
        (['us'], [], False),
    ],
)
def test_word_parts_match(
    text_parts: list[str],
    item_parts: list[str],
    expected: bool,
) -> None:
    completer = SQLCompleter()
    assert completer.word_parts_match(text_parts, item_parts) is expected


@pytest.mark.parametrize(
    ('item', 'pattern', 'under_words_text', 'case_words_text', 'expected'),
    [
        ('foo_select_bar', re.compile('(s.{0,3}?e.{0,3}?l)'), ['sel'], ['sel'], Fuzziness.REGEX),
        ('user_defined_function', re.compile('(z.{0,3}?z)'), ['us', 'de', 'fu'], ['us_de_fu'], Fuzziness.UNDER_WORDS),
        ('TimeZoneTransitionType', re.compile('(Ti.{0,3}?Zx)'), ['TiZoTrTy'], ['Ti', 'Zo', 'Tr', 'Ty'], Fuzziness.CAMEL_CASE),
        ('orders', re.compile('(z.{0,3}?z)'), ['zz'], ['zz'], None),
    ],
)
def test_find_fuzzy_match(
    item: str,
    pattern: re.Pattern[str],
    under_words_text: list[str],
    case_words_text: list[str],
    expected: int | None,
) -> None:
    completer = SQLCompleter()
    assert completer.find_fuzzy_match(item, pattern, under_words_text, case_words_text) == expected


def test_find_fuzzy_matches_collects_item_level_matches(monkeypatch) -> None:
    monkeypatch.setattr(
        SQLCompleter,
        'find_fuzzy_match',
        lambda self, item, pattern, under_words_text, case_words_text: {
            'orders': Fuzziness.REGEX,
            'order_items': Fuzziness.UNDER_WORDS,
            'other': None,
        }[item],
    )
    monkeypatch.setattr(mycli.sqlcompleter.rapidfuzz.process, 'extract', lambda *args, **kwargs: [])
    completer = SQLCompleter()
    matches = completer.find_fuzzy_matches('OrIt', 'orit', ['orders', 'order_items', 'other'])

    assert matches == [
        ('orders', Fuzziness.REGEX),
        ('order_items', Fuzziness.UNDER_WORDS),
    ]


def test_find_fuzzy_matches_skips_rapidfuzz_for_short_text(monkeypatch) -> None:
    monkeypatch.setattr(SQLCompleter, 'find_fuzzy_match', lambda *args, **kwargs: None)

    def fail_extract(*args, **kwargs):
        raise AssertionError('rapidfuzz should not be called')

    monkeypatch.setattr(mycli.sqlcompleter.rapidfuzz.process, 'extract', fail_extract)
    completer = SQLCompleter()
    matches = completer.find_fuzzy_matches('sel', 'sel', ['SELECT'])

    assert matches == []


def test_find_fuzzy_matches_appends_rapidfuzz_results_and_skips_duplicates(monkeypatch) -> None:
    monkeypatch.setattr(
        SQLCompleter,
        'find_fuzzy_match',
        lambda self, item, pattern, under_words_text, case_words_text: Fuzziness.REGEX if item == 'alphabet' else None,
    )
    monkeypatch.setattr(
        mycli.sqlcompleter.rapidfuzz.process,
        'extract',
        lambda *args, **kwargs: [('abc', 99, 0), ('alphabet', 95, 1), ('alphanumeric', 90, 2)],
    )
    completer = SQLCompleter()
    matches = completer.find_fuzzy_matches('alpahet', 'alpahet', ['abc', 'alphabet', 'alphanumeric'])

    assert matches == [
        ('alphabet', Fuzziness.REGEX),
        ('alphanumeric', Fuzziness.RAPIDFUZZ),
    ]


@pytest.mark.parametrize('existing_fuzziness', [Fuzziness.PERFECT, Fuzziness.CAMEL_CASE, Fuzziness.RAPIDFUZZ])
def test_find_fuzzy_matches_skips_rapidfuzz_duplicates_for_remaining_fuzziness_types(
    monkeypatch,
    existing_fuzziness: Fuzziness,
) -> None:
    monkeypatch.setattr(
        SQLCompleter,
        'find_fuzzy_match',
        lambda self, item, pattern, under_words_text, case_words_text: existing_fuzziness if item == 'alphabet' else None,
    )
    monkeypatch.setattr(
        mycli.sqlcompleter.rapidfuzz.process,
        'extract',
        lambda *args, **kwargs: [('alphabet', 95, 0)],
    )
    completer = SQLCompleter()

    matches = completer.find_fuzzy_matches('alpahet', 'alpahet', ['alphabet'])

    assert matches == [('alphabet', existing_fuzziness)]


@pytest.mark.parametrize(
    ('text', 'collection', 'start_only', 'expected'),
    [
        ('ord', ['orders', 'user_orders'], True, [('orders', Fuzziness.PERFECT)]),
        ('name', ['table_name', 'name_table'], False, [('table_name', Fuzziness.PERFECT), ('name_table', Fuzziness.PERFECT)]),
        ('', ['orders', 'users'], True, [('orders', Fuzziness.PERFECT), ('users', Fuzziness.PERFECT)]),
    ],
)
def test_find_perfect_matches(
    text: str,
    collection: list[str],
    start_only: bool,
    expected: list[tuple[str, int]],
) -> None:
    completer = SQLCompleter()
    assert completer.find_perfect_matches(text, collection, start_only) == expected


@pytest.mark.parametrize(
    ('casing', 'last', 'expected'),
    [
        (None, 'Sel', None),
        ('upper', 'sel', 'upper'),
        ('lower', 'SEL', 'lower'),
        ('auto', 'sel', 'lower'),
        ('auto', 'SEl', 'lower'),
        ('auto', 'SEL', 'upper'),
        ('auto', '', 'upper'),
    ],
)
def test_resolve_casing(casing: str | None, last: str, expected: str | None) -> None:
    completer = SQLCompleter()
    assert completer.resolve_casing(casing, last) == expected


@pytest.mark.parametrize(
    ('completions', 'casing', 'expected'),
    [
        ([('Select', Fuzziness.REGEX)], None, [('Select', Fuzziness.REGEX)]),
        ([('Select', Fuzziness.REGEX)], 'upper', [('SELECT', Fuzziness.REGEX)]),
        ([('Select', Fuzziness.REGEX)], 'lower', [('select', Fuzziness.REGEX)]),
        (
            [('Select', Fuzziness.REGEX), ('From', Fuzziness.PERFECT)],
            'upper',
            [('SELECT', Fuzziness.REGEX), ('FROM', Fuzziness.PERFECT)],
        ),
    ],
)
def test_apply_casing(
    completions: list[tuple[str, int]],
    casing: str | None,
    expected: list[tuple[str, int]],
) -> None:
    completer = SQLCompleter()
    assert list(completer.apply_casing(completions, casing)) == expected


def test_find_matches_uses_last_word_for_prefix_matching() -> None:
    matches = collect_matches(
        'select ord',
        ['orders', 'user_orders'],
        start_only=True,
        fuzzy=False,
    )

    assert matches == [('orders', Fuzziness.PERFECT)]


def test_find_matches_supports_substring_matching() -> None:
    matches = collect_matches(
        'name',
        ['table_name', 'name_table'],
        start_only=False,
        fuzzy=False,
    )

    assert matches == [
        ('table_name', Fuzziness.PERFECT),
        ('name_table', Fuzziness.PERFECT),
    ]


def test_find_matches_quotes_identifiers_when_text_starts_with_backtick() -> None:
    matches = collect_matches('`us', ['users'])

    assert matches == [('`users`', Fuzziness.REGEX)]


def test_find_matches_quotes_identifiers_when_cursor_is_inside_backticks() -> None:
    matches = collect_matches(
        'uu',
        ['users', '`uuid`'],
        text_before_cursor='select `uu',
    )

    assert matches == [('`uuid`', Fuzziness.REGEX)]


def test_find_matches_preserves_asterisk_inside_backticks() -> None:
    matches = collect_matches(
        '*',
        ['*'],
        text_before_cursor='select `*',
    )

    assert matches == [('*', Fuzziness.REGEX)]


def test_find_matches_finds_regex_matches() -> None:
    matches = collect_matches('sel', ['SELECT', 'foo_select_bar'])

    assert matches == [
        ('SELECT', Fuzziness.REGEX),
        ('foo_select_bar', Fuzziness.REGEX),
    ]


def test_find_matches_finds_under_word_matches() -> None:
    matches = collect_matches('us_de_fu', ['user_defined_function'])

    assert matches == [('user_defined_function', Fuzziness.UNDER_WORDS)]


def test_find_matches_finds_camel_case_matches(monkeypatch) -> None:
    monkeypatch.setattr(mycli.sqlcompleter.rapidfuzz.process, 'extract', lambda *args, **kwargs: [])

    matches = collect_matches('TiZoTrTy', ['TimeZoneTransitionType'])

    assert matches == [('TimeZoneTransitionType', Fuzziness.CAMEL_CASE)]


def test_find_matches_finds_rapidfuzz_matches() -> None:
    matches = collect_matches('sleect', ['SELECT'])

    assert matches == [('SELECT', Fuzziness.RAPIDFUZZ)]


def test_find_matches_skips_rapidfuzz_for_short_text(monkeypatch) -> None:
    def fail_extract(*args, **kwargs):
        raise AssertionError('rapidfuzz should not be called')

    monkeypatch.setattr(mycli.sqlcompleter.rapidfuzz.process, 'extract', fail_extract)

    matches = collect_matches('sel', ['SELECT'])

    assert matches == [('SELECT', Fuzziness.REGEX)]


def test_find_matches_filters_short_rapidfuzz_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        mycli.sqlcompleter.rapidfuzz.process,
        'extract',
        lambda *args, **kwargs: [('abc', 99, 0), ('alphabet', 95, 1)],
    )

    matches = collect_matches('alpahet', ['abc', 'alphabet'])

    assert matches == [('alphabet', Fuzziness.RAPIDFUZZ)]


@pytest.mark.parametrize(
    ('orig_text', 'collection', 'casing', 'expected'),
    [
        ('sel', ['SELECT'], 'auto', [('select', Fuzziness.REGEX)]),
        ('SEL', ['select'], 'auto', [('SELECT', Fuzziness.REGEX)]),
        ('sel', ['select'], 'upper', [('SELECT', Fuzziness.REGEX)]),
        ('SEL', ['SELECT'], 'lower', [('select', Fuzziness.REGEX)]),
    ],
)
def test_find_matches_applies_casing(
    orig_text: str,
    collection: list[str],
    casing: str,
    expected: list[tuple[str, int]],
) -> None:
    matches = collect_matches(orig_text, collection, casing=casing)

    assert matches == expected


def test_init_invalid_keyword_casing_defaults_to_auto() -> None:
    completer = SQLCompleter(keyword_casing='invalid')

    assert completer.keyword_casing == 'auto'


def test_extend_metadata_helpers_and_logging(caplog) -> None:
    completer = make_completer()
    completer.set_dbname('missing')

    completer.extend_keywords(['ZZZ'])
    assert 'ZZZ' in completer.keywords
    assert 'ZZZ' in completer.all_completions

    completer.extend_keywords(['ONLY_THIS'], replace=True)
    assert completer.keywords == ['ONLY_THIS']
    assert 'ONLY_THIS' in completer.all_completions

    completer.extend_show_items([('FULL TABLES',), ('STATUS',)])
    completer.extend_change_items([('MASTER TO',)])
    completer.extend_users([('app_user',)])
    assert completer.show_items == ['FULL TABLES', 'STATUS']
    assert 'MASTER TO' in completer.change_items
    assert 'app_user' in completer.users

    completer.extend_schemata(None)
    assert '' not in completer.dbmetadata['tables']

    with caplog.at_level('ERROR', logger='mycli.sqlcompleter'):
        completer.extend_relations([('orders',)], kind='tables')
    assert "listed in unrecognized schema 'missing'" in caplog.text

    completer.extend_schemata('test')
    completer.set_dbname('test')
    completer.extend_relations([('select',)], kind='tables')

    caplog.clear()
    with caplog.at_level('ERROR', logger='mycli.sqlcompleter'):
        completer.extend_columns([('missing', 'id'), ('select', 'from')], kind='tables')
    assert "relname 'missing' was not found in db 'test'" in caplog.text
    assert completer.dbmetadata['tables']['test']['`select`'] == ['*', '`from`']

    completer.set_dbname('enumdb')
    completer.extend_enum_values([('order status', 'select', ['pending'])])
    assert completer.dbmetadata['enum_values']['enumdb']['`order status`']['`select`'] == ['pending']


def test_extend_functions_procedures_character_sets_and_collations() -> None:
    completer = make_completer()
    completer.extend_schemata('test')
    completer.set_dbname('test')

    completer.extend_functions(['BUILTIN_X'], builtin=True)
    assert 'BUILTIN_X' in completer.functions

    def broken_functions():
        raise RuntimeError('boom')
        yield ('ignored', 'ignored')

    completer.extend_functions(broken_functions())
    completer.extend_functions(iter([('quoted func', 'meta')]))
    assert '`quoted func`' in completer.dbmetadata['functions']['test']

    completer.extend_procedures(iter([(), (None,), ('proc_demo',)]))
    assert 'proc_demo' in completer.dbmetadata['procedures']['test']

    completer.extend_character_sets(iter([(), (None,), ('utf8mb4',)]))
    completer.extend_collations(iter([(), (None,), ('utf8mb4_unicode_ci',)]))
    assert completer.character_sets == ['utf8mb4']
    assert completer.collations == ['utf8mb4_unicode_ci']


def test_extend_procedures_initializes_schema_metadata_when_missing() -> None:
    completer = make_completer()
    completer.set_dbname('procdb')

    completer.extend_procedures(iter([('proc_demo',)]))

    assert completer.dbmetadata['procedures']['procdb']['proc_demo'] is None


def test_get_completions_drop_unique_columns(monkeypatch) -> None:
    completer = make_completer()
    completer.extend_schemata('test')
    completer.set_dbname('test')
    completer.dbmetadata['tables']['test'] = {
        't1': ['*', 'id', 'name'],
        't2': ['*', 'id', 'email'],
    }

    monkeypatch.setattr(
        mycli.sqlcompleter,
        'suggest_type',
        lambda text, before: [{'type': 'column', 'tables': [(None, 't1', None), (None, 't2', None)], 'drop_unique': True}],
    )

    result = [c.text for c in completer.get_completions(Document(text='SELECT ', cursor_position=7), None)]

    assert result == ['id']


@pytest.mark.parametrize(
    ('suggestion', 'setup', 'text', 'expected'),
    [
        ({'type': 'procedure', 'schema': 'test'}, lambda c, m: c.extend_procedures(iter([('proc_demo',)])), 'CALL pro', 'proc_demo'),
        ({'type': 'show'}, lambda c, m: c.extend_show_items([('TABLE STATUS',)]), 'SHOW tab', 'table status'),
        ({'type': 'change'}, lambda c, m: c.extend_change_items([('MASTER TO',)]), 'CHANGE ma', 'MASTER TO'),
        ({'type': 'user'}, lambda c, m: c.extend_users([('app_user',)]), 'GRANT app', 'app_user'),
        (
            {'type': 'favoritequery'},
            lambda c, m: m.setattr(
                mycli.sqlcompleter.FavoriteQueries, 'instance', SimpleNamespace(list=lambda: ['daily_report']), raising=False
            ),
            '\\f dai',
            'daily_report',
        ),
        ({'type': 'table_format'}, lambda c, m: None, 'fmt c', 'csv'),
    ],
)
def test_get_completions_branch_specific_suggestions(monkeypatch, suggestion, setup, text, expected) -> None:
    completer = make_completer(supported_formats=('csv', 'tsv'))
    completer.extend_schemata('test')
    completer.set_dbname('test')
    setup(completer, monkeypatch)
    monkeypatch.setattr(mycli.sqlcompleter, 'suggest_type', lambda full_text, before: [suggestion])

    result = [c.text for c in completer.get_completions(Document(text=text, cursor_position=len(text)), None)]

    assert expected in result


def test_get_completions_llm_branch_with_and_without_current_word(monkeypatch) -> None:
    tokens_seen: list[list[str]] = []

    def fake_get_completions(tokens: list[str]) -> list[str]:
        tokens_seen.append(tokens)
        return ['chat', 'explain']

    monkeypatch.setattr(mycli.sqlcompleter, 'suggest_type', lambda full_text, before: [{'type': 'llm'}])
    monkeypatch.setattr(mycli.sqlcompleter.llm, 'get_completions', fake_get_completions)

    completer = make_completer()

    blank_word = [c.text for c in completer.get_completions(Document(text='\\llm ', cursor_position=5), None)]
    partial_text = '\\llm ask ch'
    partial_word = [c.text for c in completer.get_completions(Document(text=partial_text, cursor_position=len(partial_text)), None)]

    assert tokens_seen == [[], ['ask']]
    assert 'chat' in blank_word
    assert 'chat' in partial_word
    assert 'explain' in blank_word
    assert 'explain' not in partial_word


def test_find_files_populate_scoped_cols_and_enum_helpers(monkeypatch) -> None:
    completer = make_completer()
    completer.extend_schemata('test')
    completer.set_dbname('test')
    completer.dbmetadata['tables']['test']['`select`'] = ['id']
    completer.dbmetadata['views']['test']['orders_view'] = ['view_id']
    completer.extend_enum_values([('orders', 'status', ['pending', 'shipped'])])

    monkeypatch.setattr(mycli.sqlcompleter, 'parse_path', lambda word: ('/tmp', 'fi', 0))
    monkeypatch.setattr(mycli.sqlcompleter, 'suggest_path', lambda word: ['file.sql', 'folder/'])
    monkeypatch.setattr(mycli.sqlcompleter, 'complete_path', lambda name, last_path: name if name == 'file.sql' else None)

    assert list(completer.find_files('./fi')) == [('file.sql', Fuzziness.PERFECT)]
    assert completer.populate_scoped_cols([(None, 'select', None), (None, 'orders_view', None), (None, 'missing', None)]) == [
        'id',
        'view_id',
    ]
    assert completer.populate_enum_values([(None, 'orders', 'o')], 'status', parent='other') == []
    assert completer.populate_enum_values([(None, 'orders', 'o')], 'status', parent='o') == ['pending', 'shipped']
    assert completer._quote_sql_string("O'Reilly") == "'O''Reilly'"


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('`quoted`', 'quoted'),
        ('plain', 'plain'),
        (None, ''),
    ],
)
def test_strip_backticks(name: str | None, expected: str) -> None:
    assert SQLCompleter._strip_backticks(name) == expected


@pytest.mark.parametrize(
    ('parent', 'schema', 'relname', 'alias', 'expected'),
    [
        ('o', None, 'orders', 'o', True),
        ('orders', None, 'orders', None, True),
        ('test.orders', 'test', 'orders', None, True),
        ('other', 'test', 'orders', 'o', False),
    ],
)
def test_matches_parent(parent: str, schema: str | None, relname: str, alias: str | None, expected: bool) -> None:
    assert SQLCompleter._matches_parent(parent, schema, relname, alias) is expected


def test_copy_other_schemas_from_preserves_non_current_metadata() -> None:
    source = SQLCompleter()
    source.load_schema_metadata(
        schema='other',
        table_columns={'users': ['*', 'id', 'email']},
        foreign_keys={'tables': {}, 'relations': []},
        enum_values={},
        functions={'fn_foo': None},
        procedures={},
    )
    # Also populate the source's "current" schema; it should NOT be copied.
    source.load_schema_metadata(
        schema='current',
        table_columns={'stale_current': ['*']},
        foreign_keys={'tables': {}, 'relations': []},
        enum_values={},
        functions={},
        procedures={},
    )

    dest = SQLCompleter()
    dest.set_dbname('current')
    dest.extend_schemata('current')

    dest.copy_other_schemas_from(source, exclude='current')

    assert 'other' in dest.dbmetadata['tables']
    assert dest.dbmetadata['tables']['other'] == {'users': ['*', 'id', 'email']}
    assert dest.dbmetadata['functions']['other'] == {'fn_foo': None}
    # The excluded schema is not overwritten with stale source data.
    assert dest.dbmetadata['tables']['current'] == {}
    # Completion lookups pick up the copied names.
    assert 'users' in dest.all_completions
    assert 'email' in dest.all_completions
    assert 'fn_foo' in dest.all_completions


def test_copy_other_schemas_from_does_not_overwrite_existing_dest() -> None:
    source = SQLCompleter()
    source.load_schema_metadata(
        schema='shared',
        table_columns={'from_source': ['*']},
        foreign_keys={'tables': {}, 'relations': []},
        enum_values={},
        functions={},
        procedures={},
    )

    dest = SQLCompleter()
    dest.set_dbname('current')
    dest.dbmetadata['tables']['shared'] = {'from_dest': ['*']}

    dest.copy_other_schemas_from(source, exclude='current')

    # Destination's existing data wins over source when a conflict exists.
    assert dest.dbmetadata['tables']['shared'] == {'from_dest': ['*']}


def test_load_schema_metadata_ignores_empty_schema() -> None:
    completer = SQLCompleter()

    completer.load_schema_metadata(
        schema='',
        table_columns={'users': ['*', 'id']},
        foreign_keys={'tables': {'users': []}, 'relations': [('users', 'id')]},
        enum_values={'users': {'status': ['pending']}},
        functions={'fn_users': None},
        procedures={'proc_users': None},
    )

    assert completer.dbmetadata['tables'] == {}
    assert completer.dbmetadata['views'] == {}
    assert completer.dbmetadata['functions'] == {}
    assert completer.dbmetadata['procedures'] == {}
    assert completer.dbmetadata['enum_values'] == {}
    assert completer.dbmetadata['foreign_keys'] == {}
    assert 'users' not in completer.all_completions
    assert 'fn_users' not in completer.all_completions

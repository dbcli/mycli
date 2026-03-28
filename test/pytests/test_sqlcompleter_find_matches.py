# type: ignore

import re

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


def test_find_fuzzy_matches_appends_rapidfuzz_results_and_keeps_current_duplicates(monkeypatch) -> None:
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
        ('alphabet', Fuzziness.RAPIDFUZZ),
        ('alphanumeric', Fuzziness.RAPIDFUZZ),
    ]


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

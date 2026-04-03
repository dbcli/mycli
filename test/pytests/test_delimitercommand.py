# type: ignore

from __future__ import annotations

from mycli.packages.special.delimitercommand import DelimiterCommand


def test_delimiter_command_defaults_to_semicolon() -> None:
    command = DelimiterCommand()

    assert command.current == ';'


def test_set_uses_first_argument_token_and_updates_current_delimiter() -> None:
    command = DelimiterCommand()

    result = command.set('$$ select 1 $$')

    assert result[0].status == 'Changed delimiter to $$'
    assert command.current == '$$'


def test_set_rejects_missing_argument() -> None:
    command = DelimiterCommand()

    result = command.set('')

    assert result[0].status == 'Missing required argument, delimiter'
    assert command.current == ';'


def test_set_rejects_delimiter_keyword_case_insensitively() -> None:
    command = DelimiterCommand()

    result = command.set('Delimiter')

    assert result[0].status == 'Invalid delimiter "delimiter"'
    assert command.current == ';'


def test_queries_iter_preserves_statement_text_for_multi_character_delimiter() -> None:
    command = DelimiterCommand()
    command.set('end')

    assert list(command.queries_iter('delete 1end')) == ['delete 1']


def test_queries_iter_with_custom_delimiter_preserves_semicolons_inside_statement() -> None:
    command = DelimiterCommand()
    command.set('$$')

    assert list(command.queries_iter('select 1; select 2$$ select 3$$')) == [
        'select 1; select 2',
        'select 3',
    ]


def test_split_handles_placeholder_collision_in_original_sql() -> None:
    command = DelimiterCommand()
    command.set('$$')

    assert command._split('select \ufffc1; select 2$$ select 3$$') == [
        'select \ufffc1; select 2$$',
        'select 3$$',
    ]


def test_queries_iter_resplits_remaining_input_after_delimiter_change() -> None:
    command = DelimiterCommand()
    queries = command.queries_iter('select 1; delimiter $$ select 2$$ select 3$$')

    assert next(queries) == 'select 1'
    assert next(queries) == 'delimiter $$ select 2$$ select 3$$'

    command.set('$$')

    assert list(queries) == ['select 2', 'select 3']


def test_queries_iter_reappends_old_trailing_delimiter_before_resplitting(monkeypatch) -> None:
    command = DelimiterCommand()
    command._delimiter = ';;'
    split_calls: list[str] = []

    def fake_split(sql: str) -> list[str]:
        split_calls.append(sql)
        if len(split_calls) == 1:
            return ['delimiter $$;;', 'select 2$$']
        return ['ignored', 'select 2']

    monkeypatch.setattr(command, '_split', fake_split)

    queries = command.queries_iter('ignored')

    assert next(queries) == 'delimiter $$'

    command.set('$$')

    assert list(queries) == ['select 2']
    assert split_calls == ['ignored', 'delimiter $$ select 2$$;;']

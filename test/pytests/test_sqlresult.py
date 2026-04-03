from prompt_toolkit.formatted_text import FormattedText

from mycli.packages.sqlresult import SQLResult


def test_sqlresult_str_includes_all_fields() -> None:
    result = SQLResult(
        preamble='before',
        header=['id'],
        rows=[(1,)],
        postamble='after',
        status='ok',
        command={'name': 'watch', 'seconds': 1.0},
    )

    assert 'before' in str(result)
    assert "['id']" in str(result)
    assert '[(1,)]' in str(result)
    assert 'after' in str(result)
    assert 'ok' in str(result)
    assert "{'name': 'watch', 'seconds': 1.0}" in str(result)


def test_sqlresult_status_plain_handles_none_and_formatted_text() -> None:
    empty = SQLResult()
    formatted = SQLResult(status=FormattedText([('', '1 row in set'), ('', ', '), ('class:warn', '1 warning')]))

    assert empty.status_plain is None
    assert formatted.status_plain == '1 row in set, 1 warning'

from prompt_toolkit.formatted_text import FormattedText

from mycli.packages.sql_result.sql_result import SQLResult


def test_sqlresult_str_includes_all_fields() -> None:
    result = SQLResult(
        preamble='before',
        header=['id'],
        rows=[(1,)],
        postamble='after',
        status='ok',
        command={'name': 'watch', 'seconds': 1.0},
        is_error=True,
    )

    assert 'before' in str(result)
    assert "['id']" in str(result)
    assert '[(1,)]' in str(result)
    assert 'after' in str(result)
    assert 'ok' in str(result)
    assert "{'name': 'watch', 'seconds': 1.0}" in str(result)
    assert 'True' in str(result)


def test_sqlresult_status_plain_handles_none_and_formatted_text() -> None:
    empty = SQLResult()
    formatted = SQLResult(status=FormattedText([('', '1 row in set'), ('', ', '), ('class:warn', '1 warning')]))

    assert empty.status_plain is None
    assert formatted.status_plain == '1 row in set, 1 warning'


def test_finalizing_status_invalidates_cached_plain_text() -> None:
    result = SQLResult(_status_finalizer=lambda: FormattedText([('', '2 rows in set')]))
    assert result.status_plain is None

    result.finalize_status()

    assert result.status_plain == '2 rows in set'


def test_status_is_finalized_only_once() -> None:
    count = 1
    result = SQLResult(_status_finalizer=lambda: FormattedText([('', str(count))]))
    result.finalize_status()
    count = 2
    result.finalize_status()
    assert result.status_plain == '1'


def test_finalizing_static_status_leaves_it_unchanged() -> None:
    result = SQLResult(status='Query OK')
    result.finalize_status()
    assert result.status_plain == 'Query OK'

import click
from click.testing import CliRunner

from mycli.main import (cli, confirm_destructive_query, format_output,
                        is_destructive, query_starts_with, queries_start_with)
from utils import USER, HOST, PORT, PASSWORD, dbtest, run

CLI_ARGS = ['--user', USER, '--host', HOST, '--port', PORT,
            '--password', PASSWORD, '_test_db']

def test_format_output():
    results = format_output('Title', [('abc', 'def')], ['head1', 'head2'],
                            'test status', 'psql')
    expected = ['Title', '+---------+---------+\n| head1   | head2   |\n|---------+---------|\n| abc     | def     |\n+---------+---------+', 'test status']
    assert results == expected

def test_format_output_auto_expand():
    table_results = format_output('Title', [('abc', 'def')],
                                  ['head1', 'head2'], 'test status', 'psql',
                                  max_width=100)
    table = ['Title', '+---------+---------+\n| head1   | head2   |\n|---------+---------|\n| abc     | def     |\n+---------+---------+', 'test status']
    assert table_results == table

    expanded_results = format_output('Title', [('abc', 'def')],
                                     ['head1', 'head2'], 'test status', 'psql',
                                     max_width=1)
    expanded = ['Title', u'***************************[ 1. row ]***************************\nhead1 | abc\nhead2 | def\n', 'test status']
    assert expanded_results == expanded

def test_format_output_no_table():
    results = format_output('Title', [('abc', 'def')], ['head1', 'head2'],
                            'test status', None)
    expected = ['Title', 'head1\thead2', 'abc\tdef', 'test status']
    assert results == expected

@dbtest
def test_batch_mode(executor):
    run(executor, '''create table test(a text)''')
    run(executor, '''insert into test values('abc'), ('def'), ('ghi')''')

    sql = (
        'select count(*) from test;\n'
        'select * from test limit 1;'
    )

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS, input=sql)

    assert result.exit_code == 0
    assert 'count(*)\n3\na\nabc' in result.output

@dbtest
def test_batch_mode_table(executor):
    run(executor, '''create table test(a text)''')
    run(executor, '''insert into test values('abc'), ('def'), ('ghi')''')

    sql = (
        'select count(*) from test;\n'
        'select * from test limit 1;'
    )

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ['-t'], input=sql)

    expected = (
        '|   count(*) |\n|------------|\n|          3 |\n+------------+\n'
        '+-----+\n| a   |\n|-----|\n| abc |\n+-----+'
    )

    assert result.exit_code == 0
    assert expected in result.output

def test_query_starts_with(executor):
    query = 'USE test;'
    assert query_starts_with(query, ('use', )) is True

    query = 'DROP DATABASE test;'
    assert query_starts_with(query, ('use', )) is False

def test_query_starts_with_comment(executor):
    query = '# comment\nUSE test;'
    assert query_starts_with(query, ('use', )) is True

def test_queries_start_with(executor):
    sql = (
        '# comment\n'
        'show databases;'
        'use foo;'
    )
    assert queries_start_with(sql, ('show', 'select')) is True
    assert queries_start_with(sql, ('use', 'drop')) is True
    assert queries_start_with(sql, ('delete', 'update')) is False

def test_is_destructive(executor):
    sql = (
        'use test;\n'
        'show databases;\n'
        'drop database foo;'
    )
    assert is_destructive(sql) is True

def test_confirm_destructive_query_notty(executor):
    stdin = click.get_text_stream('stdin')
    assert stdin.isatty() is False

    sql = 'drop database foo;'
    assert confirm_destructive_query(sql) is None

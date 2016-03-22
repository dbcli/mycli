from click.testing import CliRunner

from mycli.main import cli, format_output
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

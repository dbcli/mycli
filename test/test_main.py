import os

import click
from click.testing import CliRunner

from mycli.main import MyCli, cli, thanks_picker, PACKAGE_ROOT
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from utils import USER, HOST, PORT, PASSWORD, dbtest, run

from textwrap import dedent
from collections import namedtuple

from tempfile import NamedTemporaryFile
from textwrap import dedent

try:
    text_type = basestring
except NameError:
    text_type = str

test_dir = os.path.abspath(os.path.dirname(__file__))
project_dir = os.path.dirname(test_dir)
default_config_file = os.path.join(project_dir, 'test', 'myclirc')
login_path_file = os.path.join(test_dir, 'mylogin.cnf')

os.environ['MYSQL_TEST_LOGIN_FILE'] = login_path_file
CLI_ARGS = ['--user', USER, '--host', HOST, '--port', PORT,
            '--password', PASSWORD, '--myclirc', default_config_file,
            '--defaults-file', default_config_file,
            '_test_db']


@dbtest
def test_execute_arg(executor):
    run(executor, 'create table test (a text)')
    run(executor, 'insert into test values("abc")')

    sql = 'select * from test;'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ['-e', sql])

    assert result.exit_code == 0
    assert '"abc"' in result.output

    result = runner.invoke(cli, args=CLI_ARGS + ['--execute', sql])

    assert result.exit_code == 0
    assert '"abc"' in result.output

    expected = '"a"\n"abc"\n'

    assert expected in result.output


@dbtest
def test_execute_arg_with_table(executor):
    run(executor, 'create table test (a text)')
    run(executor, 'insert into test values("abc")')

    sql = 'select * from test;'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ['-e', sql] + ['--table'])
    expected = '+-----+\n| a   |\n+-----+\n| abc |\n+-----+\n'

    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_execute_arg_with_csv(executor):
    run(executor, 'create table test (a text)')
    run(executor, 'insert into test values("abc")')

    sql = 'select * from test;'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ['-e', sql] + ['--csv'])
    expected = '"a"\n"abc"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


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
    assert '"count(*)"\n"3"\n"a"\n"abc"\n' in "".join(result.output)


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

    expected = (dedent("""\
        +----------+
        | count(*) |
        +----------+
        | 3        |
        +----------+
        +-----+
        | a   |
        +-----+
        | abc |
        +-----+"""))

    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_batch_mode_csv(executor):
    run(executor, '''create table test(a text, b text)''')
    run(executor,
        '''insert into test (a, b) values('abc', 'de\nf'), ('ghi', 'jkl')''')

    sql = 'select * from test;'

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ['--csv'], input=sql)

    expected = '"a","b"\n"abc","de\nf"\n"ghi","jkl"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


def test_thanks_picker_utf8():
    author_file = os.path.join(PACKAGE_ROOT, 'AUTHORS')
    sponsor_file = os.path.join(PACKAGE_ROOT, 'SPONSORS')

    name = thanks_picker((author_file, sponsor_file))
    assert isinstance(name, text_type)


def test_help_strings_end_with_periods():
    """Make sure click options have help text that end with a period."""
    for param in cli.params:
        if isinstance(param, click.core.Option):
            assert hasattr(param, 'help')
            assert param.help.endswith('.')


def test_command_descriptions_end_with_periods():
    """Make sure that mycli commands' descriptions end with a period."""
    MyCli()
    for _, command in SPECIAL_COMMANDS.items():
        assert command[3].endswith('.')


def output(monkeypatch, terminal_size, testdata, explicit_pager, expect_pager):
    global clickoutput
    clickoutput = ""
    m = MyCli()

    class TestOutput():
        def get_size(self):
            size = namedtuple('Size', 'rows columns')
            size.columns, size.rows = terminal_size
            return size

    class TestExecute():
        host = 'test'
        user = 'test'
        dbname = 'test'
        port = 0

        def server_type(self):
            return ['test']

    class CommandLineInterface():
        output = TestOutput()

    m.cli = CommandLineInterface()
    m.sqlexecute = TestExecute()
    m.explicit_pager = explicit_pager

    def echo_via_pager(s):
        assert expect_pager
        global clickoutput
        clickoutput += s

    def secho(s):
        assert not expect_pager
        global clickoutput
        clickoutput += s + "\n"

    monkeypatch.setattr(click, 'echo_via_pager', echo_via_pager)
    monkeypatch.setattr(click, 'secho', secho)
    m.output(testdata)
    if clickoutput.endswith("\n"):
        clickoutput = clickoutput[:-1]
    assert clickoutput == "\n".join(testdata)


def test_conditional_pager(monkeypatch):
    testdata = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do".split(
        " ")
    # User didn't set pager, output doesn't fit screen -> pager
    output(
        monkeypatch,
        terminal_size=(5, 10),
        testdata=testdata,
        explicit_pager=False,
        expect_pager=True
    )
    # User didn't set pager, output fits screen -> no pager
    output(
        monkeypatch,
        terminal_size=(20, 20),
        testdata=testdata,
        explicit_pager=False,
        expect_pager=False
    )
    # User manually configured pager, output doesn't fit screen -> pager
    output(
        monkeypatch,
        terminal_size=(5, 10),
        testdata=testdata,
        explicit_pager=True,
        expect_pager=True
    )
    # User manually configured pager, output fit screen -> pager
    output(
        monkeypatch,
        terminal_size=(20, 20),
        testdata=testdata,
        explicit_pager=True,
        expect_pager=True
    )

    SPECIAL_COMMANDS['nopager'].handler()
    output(
        monkeypatch,
        terminal_size=(5, 10),
        testdata=testdata,
        explicit_pager=False,
        expect_pager=False
    )
    SPECIAL_COMMANDS['pager'].handler('')


def test_reserved_space_is_integer():
    """Make sure that reserved space is returned as an integer."""
    def stub_terminal_size():
        return (5, 5)

    old_func = click.get_terminal_size

    click.get_terminal_size = stub_terminal_size
    mycli = MyCli()
    assert isinstance(mycli.get_reserved_space(), int)

    click.get_terminal_size = old_func


def test_list_dsn():
    runner = CliRunner()
    with NamedTemporaryFile(mode="w") as myclirc:
        myclirc.write(dedent("""\
            [alias_dsn]
            test = mysql://test/test
            """))
        myclirc.flush()
        args = ['--list-dsn', '--myclirc', myclirc.name]
        result = runner.invoke(cli, args=args)
        assert result.output == "test\n"
        result = runner.invoke(cli, args=args + ['--verbose'])
        assert result.output == "test : mysql://test/test\n"

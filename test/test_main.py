from collections import namedtuple
import os
import shutil
from tempfile import NamedTemporaryFile
from textwrap import dedent

import click
from click.testing import CliRunner

from mycli.main import MyCli, cli, thanks_picker
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.sqlexecute import ServerInfo
from test.utils import HOST, PASSWORD, PORT, USER, dbtest, run

test_dir = os.path.abspath(os.path.dirname(__file__))
project_dir = os.path.dirname(test_dir)
default_config_file = os.path.join(project_dir, "test", "myclirc")
login_path_file = os.path.join(test_dir, "mylogin.cnf")

os.environ["MYSQL_TEST_LOGIN_FILE"] = login_path_file
CLI_ARGS = [
    "--user",
    USER,
    "--host",
    HOST,
    "--port",
    PORT,
    "--password",
    PASSWORD,
    "--myclirc",
    default_config_file,
    "--defaults-file",
    default_config_file,
    "mycli_test_db",
]


@dbtest
def test_execute_arg(executor):
    run(executor, "create table test (a text)")
    run(executor, 'insert into test values("abc")')

    sql = "select * from test;"
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["-e", sql])

    assert result.exit_code == 0
    assert "abc" in result.output

    result = runner.invoke(cli, args=CLI_ARGS + ["--execute", sql])

    assert result.exit_code == 0
    assert "abc" in result.output

    expected = "a\nabc\n"

    assert expected in result.output


@dbtest
def test_execute_arg_with_table(executor):
    run(executor, "create table test (a text)")
    run(executor, 'insert into test values("abc")')

    sql = "select * from test;"
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["-e", sql] + ["--table"])
    expected = "+-----+\n| a   |\n+-----+\n| abc |\n+-----+\n"

    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_execute_arg_with_csv(executor):
    run(executor, "create table test (a text)")
    run(executor, 'insert into test values("abc")')

    sql = "select * from test;"
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["-e", sql] + ["--csv"])
    expected = '"a"\n"abc"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


@dbtest
def test_batch_mode(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc'), ('def'), ('ghi')""")

    sql = "select count(*) from test;\nselect * from test limit 1;"

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS, input=sql)

    assert result.exit_code == 0
    assert "count(*)\n3\na\nabc\n" in "".join(result.output)


@dbtest
def test_batch_mode_table(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc'), ('def'), ('ghi')""")

    sql = "select count(*) from test;\nselect * from test limit 1;"

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["-t"], input=sql)

    expected = dedent("""\
        +----------+
        | count(*) |
        +----------+
        | 3        |
        +----------+
        +-----+
        | a   |
        +-----+
        | abc |
        +-----+""")

    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_batch_mode_csv(executor):
    run(executor, """create table test(a text, b text)""")
    run(executor, """insert into test (a, b) values('abc', 'de\nf'), ('ghi', 'jkl')""")

    sql = "select * from test;"

    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv"], input=sql)

    expected = '"a","b"\n"abc","de\nf"\n"ghi","jkl"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


def test_thanks_picker_utf8():
    name = thanks_picker()
    assert name and isinstance(name, str)


def test_help_strings_end_with_periods():
    """Make sure click options have help text that end with a period."""
    for param in cli.params:
        if isinstance(param, click.core.Option):
            assert hasattr(param, "help")
            assert param.help.endswith(".")


def test_command_descriptions_end_with_periods():
    """Make sure that mycli commands' descriptions end with a period."""
    MyCli()
    for _, command in SPECIAL_COMMANDS.items():
        assert command[3].endswith(".")


def output(monkeypatch, terminal_size, testdata, explicit_pager, expect_pager):
    global clickoutput
    clickoutput = ""
    m = MyCli(myclirc=default_config_file)

    class TestOutput:
        def get_size(self):
            size = namedtuple("Size", "rows columns")
            size.columns, size.rows = terminal_size
            return size

    class TestExecute:
        host = "test"
        user = "test"
        dbname = "test"
        server_info = ServerInfo.from_version_string("unknown")
        port = 0

        def server_type(self):
            return ["test"]

    class PromptBuffer:
        output = TestOutput()

    m.prompt_app = PromptBuffer()
    m.sqlexecute = TestExecute()
    m.explicit_pager = explicit_pager

    def echo_via_pager(s):
        assert expect_pager
        global clickoutput
        clickoutput += "".join(s)

    def secho(s):
        assert not expect_pager
        global clickoutput
        clickoutput += s + "\n"

    monkeypatch.setattr(click, "echo_via_pager", echo_via_pager)
    monkeypatch.setattr(click, "secho", secho)
    m.output(testdata)
    if clickoutput.endswith("\n"):
        clickoutput = clickoutput[:-1]
    assert clickoutput == "\n".join(testdata)


def test_conditional_pager(monkeypatch):
    testdata = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do".split(" ")
    # User didn't set pager, output doesn't fit screen -> pager
    output(monkeypatch, terminal_size=(5, 10), testdata=testdata, explicit_pager=False, expect_pager=True)
    # User didn't set pager, output fits screen -> no pager
    output(monkeypatch, terminal_size=(20, 20), testdata=testdata, explicit_pager=False, expect_pager=False)
    # User manually configured pager, output doesn't fit screen -> pager
    output(monkeypatch, terminal_size=(5, 10), testdata=testdata, explicit_pager=True, expect_pager=True)
    # User manually configured pager, output fit screen -> pager
    output(monkeypatch, terminal_size=(20, 20), testdata=testdata, explicit_pager=True, expect_pager=True)

    SPECIAL_COMMANDS["nopager"].handler()
    output(monkeypatch, terminal_size=(5, 10), testdata=testdata, explicit_pager=False, expect_pager=False)
    SPECIAL_COMMANDS["pager"].handler("")


def test_reserved_space_is_integer(monkeypatch):
    """Make sure that reserved space is returned as an integer."""

    def stub_terminal_size():
        return (5, 5)

    with monkeypatch.context() as m:
        m.setattr(shutil, "get_terminal_size", stub_terminal_size)
        mycli = MyCli()
        assert isinstance(mycli.get_reserved_space(), int)


def test_list_dsn():
    runner = CliRunner()
    # keep Windows from locking the file with delete=False
    with NamedTemporaryFile(mode="w", delete=False) as myclirc:
        myclirc.write(
            dedent("""\
            [alias_dsn]
            test = mysql://test/test
            """)
        )
        myclirc.flush()
        args = ["--list-dsn", "--myclirc", myclirc.name]
        result = runner.invoke(cli, args=args)
        assert result.output == "test\n"
        result = runner.invoke(cli, args=args + ["--verbose"])
        assert result.output == "test : mysql://test/test\n"

    # delete=False means we should try to clean up
    try:
        if os.path.exists(myclirc.name):
            os.remove(myclirc.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def test_prettify_statement():
    statement = "SELECT 1"
    m = MyCli()
    pretty_statement = m.handle_prettify_binding(statement)
    assert pretty_statement == "SELECT\n    1;"


def test_unprettify_statement():
    statement = "SELECT\n    1"
    m = MyCli()
    unpretty_statement = m.handle_unprettify_binding(statement)
    assert unpretty_statement == "SELECT 1;"


def test_list_ssh_config():
    runner = CliRunner()
    # keep Windows from locking the file with delete=False
    with NamedTemporaryFile(mode="w", delete=False) as ssh_config:
        ssh_config.write(
            dedent("""\
            Host test
                Hostname test.example.com
                User joe
                Port 22222
                IdentityFile ~/.ssh/gateway
        """)
        )
        ssh_config.flush()
        args = ["--list-ssh-config", "--ssh-config-path", ssh_config.name]
        result = runner.invoke(cli, args=args)
        assert "test\n" in result.output
        result = runner.invoke(cli, args=args + ["--verbose"])
        assert "test : test.example.com\n" in result.output

    # delete=False means we should try to clean up
    try:
        if os.path.exists(ssh_config.name):
            os.remove(ssh_config.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def test_dsn(monkeypatch):
    # Setup classes to mock mycli.main.MyCli
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {"alias_dsn": {}}

        def __init__(self, **args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, "MyCli", MockMyCli)
    runner = CliRunner()

    # When a user supplies a DSN as database argument to mycli,
    # use these values.
    result = runner.invoke(mycli.main.cli, args=["mysql://dsn_user:dsn_passwd@dsn_host:1/dsn_database"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and MockMyCli.connect_args["passwd"] == "dsn_passwd"
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 1
        and MockMyCli.connect_args["database"] == "dsn_database"
    )

    MockMyCli.connect_args = None

    # When a use supplies a DSN as database argument to mycli,
    # and used command line arguments, use the command line
    # arguments.
    result = runner.invoke(
        mycli.main.cli,
        args=[
            "mysql://dsn_user:dsn_passwd@dsn_host:2/dsn_database",
            "--user",
            "arg_user",
            "--password",
            "arg_password",
            "--host",
            "arg_host",
            "--port",
            "3",
            "--database",
            "arg_database",
        ],
    )
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "arg_user"
        and MockMyCli.connect_args["passwd"] == "arg_password"
        and MockMyCli.connect_args["host"] == "arg_host"
        and MockMyCli.connect_args["port"] == 3
        and MockMyCli.connect_args["database"] == "arg_database"
    )

    MockMyCli.config = {"alias_dsn": {"test": "mysql://alias_dsn_user:alias_dsn_passwd@alias_dsn_host:4/alias_dsn_database"}}
    MockMyCli.connect_args = None

    # When a user uses a DSN from the configuration file (alias_dsn),
    # use these values.
    result = runner.invoke(cli, args=["--dsn", "test"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "alias_dsn_user"
        and MockMyCli.connect_args["passwd"] == "alias_dsn_passwd"
        and MockMyCli.connect_args["host"] == "alias_dsn_host"
        and MockMyCli.connect_args["port"] == 4
        and MockMyCli.connect_args["database"] == "alias_dsn_database"
    )

    MockMyCli.config = {"alias_dsn": {"test": "mysql://alias_dsn_user:alias_dsn_passwd@alias_dsn_host:4/alias_dsn_database"}}
    MockMyCli.connect_args = None

    # When a user uses a DSN from the configuration file (alias_dsn)
    # and used command line arguments, use the command line arguments.
    result = runner.invoke(
        cli,
        args=[
            "--dsn",
            "test",
            "",
            "--user",
            "arg_user",
            "--password",
            "arg_password",
            "--host",
            "arg_host",
            "--port",
            "5",
            "--database",
            "arg_database",
        ],
    )
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "arg_user"
        and MockMyCli.connect_args["passwd"] == "arg_password"
        and MockMyCli.connect_args["host"] == "arg_host"
        and MockMyCli.connect_args["port"] == 5
        and MockMyCli.connect_args["database"] == "arg_database"
    )

    # Use a DSN without password
    result = runner.invoke(mycli.main.cli, args=["mysql://dsn_user@dsn_host:6/dsn_database"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and MockMyCli.connect_args["passwd"] is None
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 6
        and MockMyCli.connect_args["database"] == "dsn_database"
    )

    # Use a DSN with query parameters
    result = runner.invoke(mycli.main.cli, args=["mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database?ssl=True"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and MockMyCli.connect_args["passwd"] == "dsn_passwd"
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 6
        and MockMyCli.connect_args["database"] == "dsn_database"
        and MockMyCli.connect_args["ssl"]["enable"] is True
    )

    # When a user uses a DSN with query parameters, and used command line
    # arguments, use the command line arguments.
    result = runner.invoke(
        mycli.main.cli,
        args=[
            "mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database?ssl=False",
            "--ssl",
        ],
    )
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and MockMyCli.connect_args["passwd"] == "dsn_passwd"
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 6
        and MockMyCli.connect_args["database"] == "dsn_database"
        and MockMyCli.connect_args["ssl"]["enable"] is True
    )


def test_ssh_config(monkeypatch):
    # Setup classes to mock mycli.main.MyCli
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {"alias_dsn": {}}

        def __init__(self, **args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, "MyCli", MockMyCli)
    runner = CliRunner()

    # Setup temporary configuration
    # keep Windows from locking the file with delete=False
    with NamedTemporaryFile(mode="w", delete=False) as ssh_config:
        ssh_config.write(
            dedent("""\
            Host test
                Hostname test.example.com
                User joe
                Port 22222
                IdentityFile ~/.ssh/gateway
        """)
        )
        ssh_config.flush()

        # When a user supplies a ssh config.
        result = runner.invoke(mycli.main.cli, args=["--ssh-config-path", ssh_config.name, "--ssh-config-host", "test"])
        assert result.exit_code == 0, result.output + " " + str(result.exception)
        assert (
            MockMyCli.connect_args["ssh_user"] == "joe"
            and MockMyCli.connect_args["ssh_host"] == "test.example.com"
            and MockMyCli.connect_args["ssh_port"] == 22222
            and MockMyCli.connect_args["ssh_key_filename"] == os.path.expanduser("~") + "/.ssh/gateway"
        )

        # When a user supplies a ssh config host as argument to mycli,
        # and used command line arguments, use the command line
        # arguments.
        result = runner.invoke(
            mycli.main.cli,
            args=[
                "--ssh-config-path",
                ssh_config.name,
                "--ssh-config-host",
                "test",
                "--ssh-user",
                "arg_user",
                "--ssh-host",
                "arg_host",
                "--ssh-port",
                "3",
                "--ssh-key-filename",
                "/path/to/key",
            ],
        )
        assert result.exit_code == 0, result.output + " " + str(result.exception)
        assert (
            MockMyCli.connect_args["ssh_user"] == "arg_user"
            and MockMyCli.connect_args["ssh_host"] == "arg_host"
            and MockMyCli.connect_args["ssh_port"] == 3
            and MockMyCli.connect_args["ssh_key_filename"] == "/path/to/key"
        )

    # delete=False means we should try to clean up
    try:
        if os.path.exists(ssh_config.name):
            os.remove(ssh_config.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


@dbtest
def test_init_command_arg(executor):
    init_command = "set sql_select_limit=1000"
    sql = 'show variables like "sql_select_limit";'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["--init-command", init_command], input=sql)

    expected = "sql_select_limit\t1000\n"
    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_init_command_multiple_arg(executor):
    init_command = "set sql_select_limit=2000; set max_join_size=20000"
    sql = 'show variables like "sql_select_limit";\nshow variables like "max_join_size"'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["--init-command", init_command], input=sql)

    expected_sql_select_limit = "sql_select_limit\t2000\n"
    expected_max_join_size = "max_join_size\t20000\n"

    assert result.exit_code == 0
    assert expected_sql_select_limit in result.output
    assert expected_max_join_size in result.output


@dbtest
def test_global_init_commands(executor):
    """Tests that global init-commands from config are executed by default."""
    # The global init-commands section in test/myclirc sets sql_select_limit=9999
    sql = 'show variables like "sql_select_limit";'
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS, input=sql)
    expected = "sql_select_limit\t9999\n"
    assert result.exit_code == 0
    assert expected in result.output

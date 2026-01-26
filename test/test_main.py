# type: ignore

from collections import namedtuple
import csv
import os
import shutil
from tempfile import NamedTemporaryFile
from textwrap import dedent

import click
from click.testing import CliRunner
from pymysql.err import OperationalError

from mycli.main import MyCli, cli, is_valid_connection_scheme, thanks_picker
import mycli.packages.special
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.sqlexecute import ServerInfo, SQLExecute
from test.utils import DATABASE, HOST, PASSWORD, PORT, USER, dbtest, run

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
def test_select_from_empty_table(executor):
    run(executor, """create table t1(id int)""")
    sql = "select * from t1"
    runner = CliRunner()
    result = runner.invoke(cli, args=CLI_ARGS + ["-t"], input=sql)
    expected = dedent("""\
        +----+
        | id |
        +----+
        +----+""")
    assert expected in result.output


def test_is_valid_connection_scheme_valid(executor, capsys):
    is_valid, scheme = is_valid_connection_scheme("mysql://test@localhost:3306/dev")
    assert is_valid


def test_is_valid_connection_scheme_invalid(executor, capsys):
    is_valid, scheme = is_valid_connection_scheme("nope://test@localhost:3306/dev")
    assert not is_valid


@dbtest
def test_ssl_mode_on(executor, capsys):
    runner = CliRunner()
    ssl_mode = "on"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert ssl_cipher


@dbtest
def test_ssl_mode_auto(executor, capsys):
    runner = CliRunner()
    ssl_mode = "auto"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert ssl_cipher


@dbtest
def test_ssl_mode_off(executor, capsys):
    runner = CliRunner()
    ssl_mode = "off"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert not ssl_cipher


@dbtest
def test_ssl_mode_overrides_ssl(executor, capsys):
    runner = CliRunner()
    ssl_mode = "off"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode, "--ssl"], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert not ssl_cipher


@dbtest
def test_ssl_mode_overrides_no_ssl(executor, capsys):
    runner = CliRunner()
    ssl_mode = "on"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode, "--no-ssl"], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert ssl_cipher


@dbtest
def test_reconnect_database_is_selected(executor, capsys):
    m = MyCli()
    m.register_special_commands()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    try:
        next(m.sqlexecute.run(f"use {DATABASE}"))
        next(m.sqlexecute.run(f"kill {m.sqlexecute.connection_id}"))
    except OperationalError:
        pass  # expected as the connection was killed
    except Exception as e:
        raise e
    m.reconnect()
    try:
        next(m.sqlexecute.run("show tables")).results.fetchall()
    except Exception as e:
        raise e


@dbtest
def test_reconnect_no_database(executor, capsys):
    m = MyCli()
    m.register_special_commands()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    sql = "\\r"
    result = next(mycli.packages.special.execute(executor, sql))
    stdout, _stderr = capsys.readouterr()
    assert result.status is None
    assert "Already connected" in stdout


@dbtest
def test_reconnect_with_different_database(executor):
    m = MyCli()
    m.register_special_commands()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    database_1 = "mycli_test_db"
    database_2 = "mysql"
    sql_1 = f"use {database_1}"
    sql_2 = f"\\r {database_2}"
    _result_1 = next(mycli.packages.special.execute(executor, sql_1))
    result_2 = next(mycli.packages.special.execute(executor, sql_2))
    expected = f'You are now connected to database "{database_2}" as user "{USER}"'
    assert expected in result_2.status


@dbtest
def test_reconnect_with_same_database(executor):
    m = MyCli()
    m.register_special_commands()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    database = "mysql"
    sql = f"\\u {database}"
    result = next(mycli.packages.special.execute(executor, sql))
    sql = f"\\r {database}"
    result = next(mycli.packages.special.execute(executor, sql))
    expected = f'You are already connected to database "{database}" as user "{USER}"'
    assert expected in result.status


@dbtest
def test_prompt_no_host_only_socket(executor):
    mycli = MyCli()
    mycli.prompt_format = "\\t \\u@\\h:\\d> "
    mycli.sqlexecute = SQLExecute
    mycli.sqlexecute.server_info = ServerInfo.from_version_string("8.0.44-0ubuntu0.24.04.1")
    mycli.sqlexecute.host = None
    mycli.sqlexecute.socket = "/var/run/mysqld/mysqld.sock"
    mycli.sqlexecute.user = "root"
    mycli.sqlexecute.dbname = "mysql"
    mycli.sqlexecute.port = "3306"
    prompt = mycli.get_prompt(mycli.prompt_format)
    assert prompt == "MySQL root@localhost:mysql> "


@dbtest
def test_enable_show_warnings(executor):
    mycli = MyCli()
    mycli.register_special_commands()
    sql = "\\W"
    result = run(executor, sql)
    assert result[0]["status"] == "Show warnings enabled."


@dbtest
def test_disable_show_warnings(executor):
    mycli = MyCli()
    mycli.register_special_commands()
    sql = "\\w"
    result = run(executor, sql)
    assert result[0]["status"] == "Show warnings disabled."


@dbtest
def test_output_ddl_with_warning_and_show_warnings_enabled(executor):
    runner = CliRunner()
    db = "mycli_test_db"
    table = "table_that_definitely_does_not_exist_1234"
    sql = f"DROP TABLE IF EXISTS {db}.{table}"
    result = runner.invoke(cli, args=CLI_ARGS + ["--show-warnings", "--no-warn"], input=sql)
    expected = "Level\tCode\tMessage\nNote\t1051\tUnknown table 'mycli_test_db.table_that_definitely_does_not_exist_1234'\n"
    assert expected in result.output


@dbtest
def test_output_with_warning_and_show_warnings_enabled(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--show-warnings"], input=sql)
    expected = "1 + '0 foo'\n1.0\nLevel\tCode\tMessage\nWarning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    assert expected in result.output


@dbtest
def test_output_with_warning_and_show_warnings_disabled(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--no-show-warnings"], input=sql)
    expected = "1 + '0 foo'\n1.0\nLevel\tCode\tMessage\nWarning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    assert expected not in result.output


@dbtest
def test_output_with_multiple_warnings_in_single_statement(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo', 2 + '0 foo'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--show-warnings"], input=sql)
    expected = (
        "1 + '0 foo'\t2 + '0 foo'\n"
        "1.0\t2.0\n"
        "Level\tCode\tMessage\n"
        "Warning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
        "Warning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    )
    assert expected in result.output


@dbtest
def test_output_with_multiple_warnings_in_multiple_statements(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo'; SELECT 2 + '0 foo'"
    result = runner.invoke(cli, args=CLI_ARGS + ["--show-warnings"], input=sql)
    expected = (
        "1 + '0 foo'\n"
        "1.0\n"
        "Level\tCode\tMessage\n"
        "Warning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
        "2 + '0 foo'\n"
        "2.0\n"
        "Level\tCode\tMessage\n"
        "Warning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    )
    assert expected in result.output


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
def test_execute_arg_with_checkpoint(executor):
    run(executor, "create table test (a text)")
    run(executor, 'insert into test values("abc")')

    sql = "select * from test;"
    runner = CliRunner()

    with NamedTemporaryFile(mode="w", delete=False) as checkpoint:
        checkpoint.close()

    result = runner.invoke(cli, args=CLI_ARGS + ["--execute", sql, f"--checkpoint={checkpoint.name}"])
    assert result.exit_code == 0

    with open(checkpoint.name, 'r') as f:
        contents = f.read()
    assert sql in contents
    os.remove(checkpoint.name)

    sql = 'select 10 from nonexistent_table;'
    result = runner.invoke(cli, args=CLI_ARGS + ["--execute", sql, f"--checkpoint={checkpoint.name}"])
    assert result.exit_code != 0

    with open(checkpoint.name, 'r') as f:
        contents = f.read()
    assert sql not in contents

    # delete=False means we should try to clean up
    # we don't really need "try" here as open() would have already failed
    try:
        if os.path.exists(checkpoint.name):
            os.remove(checkpoint.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


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
        |        3 |
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


def test_list_dsn(monkeypatch):
    monkeypatch.setattr(MyCli, "system_config_files", [])
    monkeypatch.setattr(MyCli, "pwd_config_file", os.path.join(test_dir, "does_not_exist.myclirc"))
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
            self.ssl_mode = "auto"

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
            self.ssl_mode = "auto"

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


@dbtest
def test_execute_with_logfile(executor):
    """Test that --execute combines with --logfile"""
    sql = 'select 1'
    runner = CliRunner()

    with NamedTemporaryFile(mode="w", delete=False) as logfile:
        result = runner.invoke(mycli.main.cli, args=CLI_ARGS + ["--logfile", logfile.name, "--execute", sql])
        assert result.exit_code == 0

    assert os.path.getsize(logfile.name) > 0

    try:
        if os.path.exists(logfile.name):
            os.remove(logfile.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")

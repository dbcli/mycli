# type: ignore
from __future__ import annotations

import builtins
from collections import namedtuple
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import os
from pathlib import Path
import runpy
import shutil
import sys
from tempfile import NamedTemporaryFile
from textwrap import dedent
from types import SimpleNamespace
from typing import Any, cast

import click
from click.testing import CliRunner
import prompt_toolkit
from prompt_toolkit.formatted_text import (
    FormattedText,
    to_formatted_text,
    to_plain_text,
)
import pymysql
from pymysql.err import OperationalError
import pytest

from mycli import main
import mycli.cli_runner
import mycli.client_connection
from mycli.constants import (
    DEFAULT_DATABASE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USER,
    EMPTY_PASSWORD_FLAG_SENTINEL,
    ER_MUST_CHANGE_PASSWORD_LOGIN,
    TEST_DATABASE,
)
from mycli.main import (
    INT_OR_STRING_CLICK_TYPE,
    CliArgs,
    MyCli,
    click_entrypoint,
    get_password_from_file,
    preprocess_cli_args,
)
import mycli.main_modes.batch
import mycli.main_modes.repl as repl_mode
import mycli.output as output_module
import mycli.packages.cli_utils
import mycli.packages.special
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.packages.sqlresult import SQLResult
from mycli.password_sources import KNOWN_PASSWORD_SOURCES
from mycli.sqlexecute import ServerInfo, SQLExecute
from mycli.types import Query
from test.utils import (
    DATABASE,
    HOST,
    PASSWORD,
    PORT,
    TEMPFILE_PREFIX,
    USER,
    DummyFormatter,
    DummyLogger,
    FakeCursorBase,
    RecordingSQLExecute,
    ReusableLock,
    call_click_entrypoint_direct,
    dbtest,
    make_bare_mycli,
    make_dummy_mycli_class,
    run,
)

pytests_dir = os.path.abspath(os.path.dirname(__file__))
project_root_dir = os.path.abspath(os.path.join(pytests_dir, '..', '..'))
default_config_file = os.path.join(project_root_dir, 'test', 'myclirc')
login_path_file = os.path.join(project_root_dir, 'test', 'mylogin.cnf')

os.environ["MYSQL_TEST_LOGIN_FILE"] = login_path_file
CLI_ARGS_WITHOUT_DB = [
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
]
CLI_ARGS = CLI_ARGS_WITHOUT_DB + [TEST_DATABASE]


def resolve_connect_password(connect_args: dict[str, Any]) -> tuple[str, str | int] | None:
    selected = connect_args['password_candidates'].resolve(KNOWN_PASSWORD_SOURCES)
    if selected is None:
        return None
    return selected.source, selected.value


@dbtest
@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown; try running the test suite under winpty')
def test_binary_display_hex(executor):
    m = MyCli()
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
    )
    m.explicit_pager = False
    sqlresult = next(m.sqlexecute.run("select b'01101010' AS binary_test"))
    formatted = m.format_sqlresult(
        sqlresult,
        is_expanded=False,
        is_redirected=False,
        null_string="<null>",
        numeric_alignment="right",
        binary_display="hex",
        max_width=None,
    )
    f = io.StringIO()
    with redirect_stdout(f):
        m.output(formatted, sqlresult)
    expected = " 0x6a "
    output = f.getvalue()
    assert expected in output


@dbtest
@pytest.mark.skipif(os.name == 'nt', reason='todo: unknown')
def test_binary_display_utf8(executor):
    m = MyCli()
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
    )
    m.explicit_pager = False
    sqlresult = next(m.sqlexecute.run("select b'01101010' AS binary_test"))
    formatted = m.format_sqlresult(
        sqlresult,
        is_expanded=False,
        is_redirected=False,
        null_string="<null>",
        numeric_alignment="right",
        binary_display="utf8",
        max_width=None,
    )
    f = io.StringIO()
    with redirect_stdout(f):
        m.output(formatted, sqlresult)
    expected = " j "
    output = f.getvalue()
    assert expected in output


@dbtest
def test_select_from_empty_table(executor):
    run(executor, """create table t1(id int)""")
    sql = "select * from t1"
    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["-t"], input=sql)
    expected = dedent("""\
        +----+
        | id |
        +----+
        +----+""")
    assert expected in result.output


def test_filtered_sys_argv_maps_single_dash_h_to_help(monkeypatch):
    import mycli.main

    monkeypatch.setattr(sys, 'argv', ['mycli', '-h'])

    assert mycli.packages.cli_utils.filtered_sys_argv() == ['--help']


def test_filtered_sys_argv_preserves_host_option_usage(monkeypatch):
    import mycli.main

    monkeypatch.setattr(sys, 'argv', ['mycli', '-h', 'example.com'])

    assert mycli.packages.cli_utils.filtered_sys_argv() == ['-h', 'example.com']


def test_main_dash_h_and_help_have_equivalent_output(monkeypatch):
    import mycli.main

    def run_main(argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        monkeypatch.setattr(sys, 'argv', argv)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = mycli.main.main()
        return result, stdout.getvalue(), stderr.getvalue()

    dash_h_result, dash_h_stdout, dash_h_stderr = run_main(['mycli', '-h'])
    dash_help_result, dash_help_stdout, dash_help_stderr = run_main(['mycli', '--help'])

    assert dash_h_result == 0
    assert dash_help_result == 0
    assert dash_h_stdout == dash_help_stdout
    assert dash_h_stderr == dash_help_stderr


def test_main_returns_zero_when_click_entrypoint_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', lambda: ['--help'])
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: None)

    assert main.main() == 0


def test_main_returns_click_entrypoint_integer_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', lambda: ['--version'])
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: 7)

    assert main.main() == 7


def test_main_returns_one_for_unexpected_click_entrypoint_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', list)
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: object())

    assert main.main() == 1


def test_main_exits_one_on_click_abort(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', list)
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(click.Abort()))

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    assert excinfo.value.code == 1
    assert 'Aborted!' in capsys.readouterr().err


def test_main_exits_one_on_broken_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, 'filtered_sys_argv', list)
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(BrokenPipeError()))

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    assert excinfo.value.code == 1


def test_main_exits_with_click_exception_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    exception = click.ClickException('bad option')
    exception.exit_code = 9
    show_calls: list[bool] = []
    monkeypatch.setattr(main, 'filtered_sys_argv', list)
    monkeypatch.setattr(exception, 'show', lambda *args, **kwargs: show_calls.append(True))
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(exception))

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    assert excinfo.value.code == 9
    assert show_calls == [True]


def test_main_exits_two_for_click_exception_without_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoExitCodeClickException(click.ClickException):
        def __getattribute__(self, name: str) -> Any:
            if name == 'exit_code':
                raise AttributeError(name)
            return super().__getattribute__(name)

    exception = NoExitCodeClickException('bad option')
    show_calls: list[bool] = []
    monkeypatch.setattr(main, 'filtered_sys_argv', list)
    monkeypatch.setattr(exception, 'show', lambda *args, **kwargs: show_calls.append(True))
    monkeypatch.setattr(main.click_entrypoint, 'main', lambda *args, **kwargs: (_ for _ in ()).throw(exception))

    with pytest.raises(SystemExit) as excinfo:
        main.main()

    assert excinfo.value.code == 2
    assert show_calls == [True]


def test_module_main_guard_calls_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_codes: list[int | None] = []
    monkeypatch.setattr(click.core.Command, 'main', lambda self, *args, **kwargs: 11)
    monkeypatch.setattr(sys, 'exit', lambda code=0: exit_codes.append(code))

    runpy.run_path(main.__file__, run_name='__main__')

    assert exit_codes == [11]


@dbtest
def test_ssl_mode_on(executor, capsys):
    runner = CliRunner()
    ssl_mode = "on"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert ssl_cipher


@dbtest
def test_ssl_mode_auto(executor, capsys):
    runner = CliRunner()
    ssl_mode = "auto"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert ssl_cipher


@dbtest
def test_ssl_mode_off(executor, capsys):
    runner = CliRunner()
    ssl_mode = "off"
    sql = "select * from performance_schema.session_status where variable_name = 'Ssl_cipher'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--csv", "--ssl-mode", ssl_mode], input=sql)
    result_dict = next(csv.DictReader(result.stdout.split("\n")))
    ssl_cipher = result_dict.get("VARIABLE_VALUE", None)
    assert not ssl_cipher


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
        next(m.sqlexecute.run("show tables")).rows.fetchall()
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
    )
    database_1 = TEST_DATABASE
    database_2 = DEFAULT_DATABASE
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
    )
    database = DEFAULT_DATABASE
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
    mycli.sqlexecute.user = DEFAULT_USER
    mycli.sqlexecute.dbname = DEFAULT_DATABASE
    mycli.sqlexecute.port = DEFAULT_PORT
    prompt = repl_mode.render_prompt_string(mycli, mycli.prompt_format, 0)
    prompt_plain = to_plain_text(prompt)
    assert prompt_plain == f"MySQL {DEFAULT_USER}@{DEFAULT_HOST}:{DEFAULT_DATABASE}> "


@dbtest
def test_prompt_socket_overrides_port(executor):
    mycli = MyCli()
    mycli.prompt_format = "\\t \\u@\\h:\\k \\d> "
    mycli.sqlexecute = SQLExecute
    mycli.sqlexecute.server_info = ServerInfo.from_version_string("8.0.44-0ubuntu0.24.04.1")
    mycli.sqlexecute.host = None
    mycli.sqlexecute.socket = "/var/run/mysqld/mysqld.sock"
    mycli.sqlexecute.user = DEFAULT_USER
    mycli.sqlexecute.dbname = DEFAULT_DATABASE
    mycli.sqlexecute.port = DEFAULT_PORT
    prompt = repl_mode.render_prompt_string(mycli, mycli.prompt_format, 0)
    prompt_plain = to_plain_text(prompt)
    assert prompt_plain == f"MySQL {DEFAULT_USER}@{DEFAULT_HOST}:mysqld.sock {DEFAULT_DATABASE}> "


@dbtest
def test_prompt_socket_short_host(executor):
    mycli = MyCli()
    mycli.prompt_format = "\\t \\u@\\H:\\k \\d> "
    mycli.sqlexecute = SQLExecute
    mycli.sqlexecute.server_info = ServerInfo.from_version_string("8.0.44-0ubuntu0.24.04.1")
    mycli.sqlexecute.host = f'{DEFAULT_HOST}.localdomain'
    mycli.sqlexecute.socket = None
    mycli.sqlexecute.user = DEFAULT_USER
    mycli.sqlexecute.dbname = DEFAULT_DATABASE
    mycli.sqlexecute.port = DEFAULT_PORT
    prompt = repl_mode.render_prompt_string(mycli, mycli.prompt_format, 0)
    prompt_plain = to_plain_text(prompt)
    assert prompt_plain == f"MySQL {DEFAULT_USER}@{DEFAULT_HOST}:{DEFAULT_PORT} {DEFAULT_DATABASE}> "


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
    db = TEST_DATABASE
    table = "table_that_definitely_does_not_exist_1234"
    sql = f"DROP TABLE IF EXISTS {db}.{table}"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--show-warnings", "--no-warn"], input=sql)
    expected = f"Level\tCode\tMessage\nNote\t1051\tUnknown table '{db}.table_that_definitely_does_not_exist_1234'\n"
    assert expected in result.output


@dbtest
def test_output_with_warning_and_show_warnings_enabled(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--show-warnings"], input=sql)
    expected = "1 + '0 foo'\n1.0\nLevel\tCode\tMessage\nWarning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    assert expected in result.output


@dbtest
def test_output_with_warning_and_show_warnings_disabled(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--no-show-warnings"], input=sql)
    expected = "1 + '0 foo'\n1.0\nLevel\tCode\tMessage\nWarning\t1292\tTruncated incorrect DOUBLE value: '0 foo'\n"
    assert expected not in result.output


@dbtest
@pytest.mark.skipif(sys.platform == 'darwin', reason='todo: fails on mac+Homebrew in CI, maybe because of MySQL server version')
def test_no_show_warnings_overrides_myclirc_setting(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    sql = 'EXPLAIN SELECT 1'
    expected = 'select 1'

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as myclirc:
        myclirc.write(
            dedent("""\
            [main]
            show_warnings = True
            """)
        )
        myclirc.flush()
        args = [
            '--user',
            USER,
            '--host',
            HOST,
            '--port',
            PORT,
            '--password',
            PASSWORD,
            '--myclirc',
            myclirc.name,
            TEST_DATABASE,
        ]

        result = runner.invoke(click_entrypoint, args=args, input=sql)
        assert expected in result.output

        result = runner.invoke(click_entrypoint, args=args + ['--no-show-warnings'], input=sql)
        assert expected not in result.output

    try:
        if os.path.exists(myclirc.name):
            os.remove(myclirc.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


@dbtest
def test_output_with_multiple_warnings_in_single_statement(executor):
    runner = CliRunner()
    sql = "SELECT 1 + '0 foo', 2 + '0 foo'"
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--show-warnings"], input=sql)
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
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--show-warnings"], input=sql)
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
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["-e", sql])

    assert result.exit_code == 0
    assert "abc" in result.output

    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--execute", sql])

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

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode="w", delete=False) as checkpoint:
        checkpoint.close()

    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--execute", sql, f"--checkpoint={checkpoint.name}"])
    assert result.exit_code == 0

    with open(checkpoint.name, 'r') as f:
        contents = f.read()
    assert sql in contents
    os.remove(checkpoint.name)

    sql = 'select 10 from nonexistent_table;'
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--execute", sql, f"--checkpoint={checkpoint.name}"])
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
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["-e", sql] + ["--table"])
    expected = "+-----+\n| a   |\n+-----+\n| abc |\n+-----+\n"

    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_execute_arg_with_csv(executor):
    run(executor, "create table test (a text)")
    run(executor, 'insert into test values("abc")')

    sql = "select * from test;"
    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["-e", sql] + ["--csv"])
    expected = '"a"\n"abc"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


@dbtest
def test_batch_mode(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc'), ('def'), ('ghi')""")

    sql = "select count(*) from test;\nselect * from test limit 1;"

    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS, input=sql)

    assert result.exit_code == 0
    assert "count(*)\n3\na\nabc\n" in "".join(result.output)


@dbtest
def test_batch_mode_multiline_statement(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc'), ('def'), ('ghi')""")

    sql = "select count(*)\nfrom test;\nselect * from test limit 1;"

    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS, input=sql)

    assert result.exit_code == 0
    assert "count(*)\n3\na\nabc\n" in "".join(result.output)


@dbtest
def test_batch_mode_table(executor):
    run(executor, """create table test(a text)""")
    run(executor, """insert into test values('abc'), ('def'), ('ghi')""")

    sql = "select count(*) from test;\nselect * from test limit 1;"

    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["-t"], input=sql)

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
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--csv"], input=sql)

    expected = '"a","b"\n"abc","de\nf"\n"ghi","jkl"\n'

    assert result.exit_code == 0
    assert expected in "".join(result.output)


def test_help_strings_end_with_periods():
    """Make sure click options have help text that end with a period."""
    for param in click_entrypoint.params:
        if isinstance(param, click.core.Option):
            if param.hidden:
                continue
            assert hasattr(param, "help")
            assert param.help.endswith(".")


def test_command_descriptions_end_with_periods():
    """Make sure that mycli commands' descriptions end with a period."""
    MyCli()
    for _, command in SPECIAL_COMMANDS.items():
        assert command.description.endswith(".")


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
        socket = ''

        def server_type(self):
            return ["test"]

    class TestPromptSession:
        output = TestOutput()
        app = None

    m.prompt_session = TestPromptSession()
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
    m.output(testdata, SQLResult())
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
    runner = CliRunner()
    # keep Windows from locking the file with delete=False
    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode="w", delete=False) as myclirc:
        myclirc.write(
            dedent("""\
            [alias_dsn]
            test = mysql://test/test
            """)
        )
        myclirc.flush()
        args = ["--list-dsn", "--myclirc", myclirc.name]
        result = runner.invoke(click_entrypoint, args=args)
        assert result.output == "test\n"
        result = runner.invoke(click_entrypoint, args=args + ["--verbose"])
        assert result.output == "test : mysql://test/test\n"

    # delete=False means we should try to clean up
    try:
        if os.path.exists(myclirc.name):
            os.remove(myclirc.name)
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
        config = {
            "main": {},
            "alias_dsn": {},
            "connection": {
                "default_keepalive_ticks": 0,
            },
        }

        def __init__(self, **args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = "auto"
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, "MyCli", MockMyCli)
    runner = CliRunner()

    # When a user supplies a DSN as database argument to mycli,
    # use these values.
    result = runner.invoke(mycli.main.click_entrypoint, args=["mysql://dsn_user:dsn_passwd@dsn_host:1/dsn_database"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 1
        and MockMyCli.connect_args["database"] == "dsn_database"
    )

    MockMyCli.connect_args = None

    # When a use supplies a DSN as database argument to mycli,
    # and used command line arguments, use the command line
    # arguments.
    result = runner.invoke(
        mycli.main.click_entrypoint,
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
        and resolve_connect_password(MockMyCli.connect_args) == ('literal', 'arg_password')
        and MockMyCli.connect_args["host"] == "arg_host"
        and MockMyCli.connect_args["port"] == 3
        and MockMyCli.connect_args["database"] == "arg_database"
    )

    MockMyCli.config = {
        "main": {},
        "alias_dsn": {"test": "mysql://alias_dsn_user:alias_dsn_passwd@alias_dsn_host:4/alias_dsn_database"},
        "connection": {
            "default_keepalive_ticks": 0,
        },
    }
    MockMyCli.connect_args = None

    # When a user uses a DSN from the configuration file (alias_dsn),
    # use these values.
    result = runner.invoke(click_entrypoint, args=["--dsn", "test"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "alias_dsn_user"
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'alias_dsn_passwd')
        and MockMyCli.connect_args["host"] == "alias_dsn_host"
        and MockMyCli.connect_args["port"] == 4
        and MockMyCli.connect_args["database"] == "alias_dsn_database"
    )

    MockMyCli.config = {
        "main": {},
        "alias_dsn": {"test": "mysql://alias_dsn_user:alias_dsn_passwd@alias_dsn_host:4/alias_dsn_database"},
        "connection": {
            "default_keepalive_ticks": 0,
        },
    }
    MockMyCli.connect_args = None

    # When a user uses a DSN from the configuration file (alias_dsn)
    # and used command line arguments, use the command line arguments.
    result = runner.invoke(
        click_entrypoint,
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
        and resolve_connect_password(MockMyCli.connect_args) == ('literal', 'arg_password')
        and MockMyCli.connect_args["host"] == "arg_host"
        and MockMyCli.connect_args["port"] == 5
        and MockMyCli.connect_args["database"] == "arg_database"
    )

    # Use a DSN without password
    result = runner.invoke(mycli.main.click_entrypoint, args=["mysql://dsn_user@dsn_host:6/dsn_database"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and resolve_connect_password(MockMyCli.connect_args) is None
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 6
        and MockMyCli.connect_args["database"] == "dsn_database"
    )

    # Use a DSN with query parameters
    result = runner.invoke(mycli.main.click_entrypoint, args=["mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database?ssl_mode=off"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert (
        MockMyCli.connect_args["user"] == "dsn_user"
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
        and MockMyCli.connect_args["host"] == "dsn_host"
        and MockMyCli.connect_args["port"] == 6
        and MockMyCli.connect_args["database"] == "dsn_database"
        and MockMyCli.connect_args["ssl"] is None
    )

    # When a user uses a DSN with query parameters, and also used command line
    # arguments, prefer the command line arguments.
    MockMyCli.connect_args = None
    MockMyCli.config = {
        "main": {},
        "alias_dsn": {},
        "connection": {
            "default_keepalive_ticks": 0,
        },
    }

    # keepalive_ticks as a query parameter
    result = runner.invoke(mycli.main.click_entrypoint, args=["mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database?keepalive_ticks=30"])
    assert result.exit_code == 0, result.output + " " + str(result.exception)
    assert MockMyCli.connect_args["keepalive_ticks"] == 30

    MockMyCli.connect_args = None

    # When a user uses a DSN with query parameters, and also used command line
    # arguments, use the command line arguments.
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            'mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database?ssl_mode=off',
            '--ssl-mode=on',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'dsn_user'
    assert resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
    assert MockMyCli.connect_args['host'] == 'dsn_host'
    assert MockMyCli.connect_args['port'] == 6
    assert MockMyCli.connect_args['database'] == 'dsn_database'
    assert MockMyCli.connect_args['ssl']['mode'] == 'on'

    # Accept a literal DSN with the --dsn flag (not only an alias)
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--dsn',
            'mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert (
        MockMyCli.connect_args['user'] == 'dsn_user'
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
        and MockMyCli.connect_args['host'] == 'dsn_host'
        and MockMyCli.connect_args['port'] == 6
        and MockMyCli.connect_args['database'] == 'dsn_database'
    )

    # accept socket as a query parameter
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            f'mysql://dsn_user:dsn_passwd@{DEFAULT_HOST}/dsn_database?socket=mysql.sock',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'dsn_user'
    assert resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
    assert MockMyCli.connect_args['host'] == DEFAULT_HOST
    assert MockMyCli.connect_args['database'] == 'dsn_database'
    assert MockMyCli.connect_args['socket'] == 'mysql.sock'

    # accept character_set as a query parameter
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            f'mysql://dsn_user:dsn_passwd@{DEFAULT_HOST}/dsn_database?character_set=latin1',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'dsn_user'
    assert resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
    assert MockMyCli.connect_args['host'] == DEFAULT_HOST
    assert MockMyCli.connect_args['database'] == 'dsn_database'
    assert MockMyCli.connect_args['character_set'] == 'latin1'

    # --character_set overrides character_set as a query parameter
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            f'mysql://dsn_user:dsn_passwd@{DEFAULT_HOST}/dsn_database?character_set=latin1',
            '--character-set=utf8mb3',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'dsn_user'
    assert resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
    assert MockMyCli.connect_args['host'] == DEFAULT_HOST
    assert MockMyCli.connect_args['database'] == 'dsn_database'
    assert MockMyCli.connect_args['character_set'] == 'utf8mb3'


def test_mysql_dsn_envvar(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    monkeypatch.setenv('MYSQL_DSN', 'mysql://dsn_user:dsn_passwd@dsn_host:7/dsn_database')
    runner = CliRunner()

    result = runner.invoke(mycli.main.click_entrypoint)
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert 'DSN environment variable is deprecated' not in result.output
    assert (
        MockMyCli.connect_args['user'] == 'dsn_user'
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
        and MockMyCli.connect_args['host'] == 'dsn_host'
        and MockMyCli.connect_args['port'] == 7
        and MockMyCli.connect_args['database'] == 'dsn_database'
    )


def test_password_option_uses_cleartext_value(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--user',
            'user',
            '--host',
            DEFAULT_HOST,
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
            '--password',
            'cleartext_password',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert resolve_connect_password(MockMyCli.connect_args) == ('literal', 'cleartext_password')


def test_password_option_overrides_password_file_and_mysql_pwd(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    monkeypatch.setenv('MYSQL_PWD', 'env_password')
    runner = CliRunner()

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as password_file:
        password_file.write('file_password\n')
        password_file.flush()

    try:
        result = runner.invoke(
            mycli.main.click_entrypoint,
            args=[
                '--user',
                'user',
                '--host',
                DEFAULT_HOST,
                '--port',
                f'{DEFAULT_PORT}',
                '--database',
                'database',
                '--password',
                'option_password',
                '--password-file',
                password_file.name,
            ],
        )
        assert result.exit_code == 0, result.output + ' ' + str(result.exception)
        assert resolve_connect_password(MockMyCli.connect_args) == ('literal', 'option_password')
    finally:
        os.remove(password_file.name)


def test_password_file_option_reads_password(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as password_file:
        password_file.write('file_password\nsecond line ignored\n')
        password_file.flush()

    try:
        result = runner.invoke(
            mycli.main.click_entrypoint,
            args=[
                '--user',
                'user',
                '--host',
                DEFAULT_HOST,
                '--port',
                f'{DEFAULT_PORT}',
                '--database',
                'database',
                '--password-file',
                password_file.name,
            ],
        )
        assert result.exit_code == 0, result.output + ' ' + str(result.exception)
        assert resolve_connect_password(MockMyCli.connect_args) == ('file', 'file_password')
    finally:
        os.remove(password_file.name)


def test_password_file_option_missing_file():
    runner = CliRunner()
    missing_path = 'definitely_missing_password_file.txt'

    result = runner.invoke(
        click_entrypoint,
        args=[
            '--password-file',
            missing_path,
        ],
    )

    assert result.exit_code == 1
    assert f"Password file '{missing_path}' not found" in result.output


def test_username_option_and_mysql_user_envvar(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--username',
            'option_user',
            '--host',
            DEFAULT_HOST,
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'option_user'

    MockMyCli.connect_args = None
    monkeypatch.setenv('MYSQL_USER', 'env_user')
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--host',
            DEFAULT_HOST,
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'env_user'


def test_host_option_and_mysql_host_envvar(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--host',
            'option_host',
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['host'] == 'option_host'

    MockMyCli.connect_args = None
    monkeypatch.setenv('MYSQL_HOST', 'env_host')
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['host'] == 'env_host'


def test_hostname_option_alias(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--hostname',
            'alias_host',
            '--port',
            f'{DEFAULT_PORT}',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0
    assert MockMyCli.connect_args['host'] == 'alias_host'


def test_port_option_and_mysql_tcp_port_envvar(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--host',
            DEFAULT_HOST,
            '--port',
            '12345',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['port'] == 12345

    MockMyCli.connect_args = None
    monkeypatch.setenv('MYSQL_TCP_PORT', '23456')
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--host',
            DEFAULT_HOST,
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['port'] == 23456


def test_socket_option_and_mysql_unix_socket_envvar(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {},
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    runner = CliRunner()

    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--socket',
            'option.sock',
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['socket'] == 'option.sock'

    MockMyCli.connect_args = None
    monkeypatch.setenv('MYSQL_UNIX_SOCKET', 'env.sock')
    result = runner.invoke(
        mycli.main.click_entrypoint,
        args=[
            '--database',
            'database',
        ],
    )
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['socket'] == 'env.sock'


def test_mysql_user_envvar_overrides_dsn_resolution(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        config = {
            'main': {},
            'alias_dsn': {
                'prod': 'mysql://alias_user:alias_password@alias_host:4/alias_database',
            },
            'connection': {
                'default_keepalive_ticks': 0,
            },
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0

        def connect(self, **args):
            MockMyCli.connect_args = args

        def run_query(self, query, new_line=True):
            pass

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    monkeypatch.setenv('MYSQL_USER', 'env_user')
    runner = CliRunner()

    result = runner.invoke(mycli.main.click_entrypoint, args=['prod'])
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert MockMyCli.connect_args['user'] == 'env_user'
    assert resolve_connect_password(MockMyCli.connect_args) is None
    assert MockMyCli.connect_args['host'] is None
    assert MockMyCli.connect_args['port'] is None
    assert MockMyCli.connect_args['database'] == 'prod'

    MockMyCli.connect_args = None
    result = runner.invoke(mycli.main.click_entrypoint, args=['mysql://dsn_user:dsn_passwd@dsn_host:6/dsn_database'])
    assert result.exit_code == 0, result.output + ' ' + str(result.exception)
    assert (
        MockMyCli.connect_args['user'] == 'env_user'
        and resolve_connect_password(MockMyCli.connect_args) == ('dsn', 'dsn_passwd')
        and MockMyCli.connect_args['host'] == 'dsn_host'
        and MockMyCli.connect_args['port'] == 6
        and MockMyCli.connect_args['database'] == 'dsn_database'
    )


@dbtest
def test_init_command_arg(executor):
    init_command = "set sql_select_limit=1000"
    sql = 'show variables like "sql_select_limit";'
    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--init-command", init_command], input=sql)

    expected = "sql_select_limit\t1000\n"
    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_init_command_multiple_arg(executor):
    init_command = "set sql_select_limit=2000; set max_join_size=20000"
    sql = 'show variables like "sql_select_limit";\nshow variables like "max_join_size"'
    runner = CliRunner()
    result = runner.invoke(click_entrypoint, args=CLI_ARGS + ["--init-command", init_command], input=sql)

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
    result = runner.invoke(click_entrypoint, args=CLI_ARGS, input=sql)
    expected = "sql_select_limit\t9999\n"
    assert result.exit_code == 0
    assert expected in result.output


@dbtest
def test_execute_with_logfile(executor):
    """Test that --execute combines with --logfile"""
    sql = 'select 1'
    runner = CliRunner()

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode="w", delete=False) as logfile:
        result = runner.invoke(mycli.main.click_entrypoint, args=CLI_ARGS + ["--logfile", logfile.name, "--execute", sql])
        assert result.exit_code == 0

    assert os.path.getsize(logfile.name) > 0

    try:
        if os.path.exists(logfile.name):
            os.remove(logfile.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


@dbtest
def test_execute_with_short_logfile_option(executor):
    """Test that --execute combines with -l"""
    sql = 'select 1'
    runner = CliRunner()

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode="w", delete=False) as logfile:
        result = runner.invoke(mycli.main.click_entrypoint, args=CLI_ARGS + ["-l", logfile.name, "--execute", sql])
        assert result.exit_code == 0

    assert os.path.getsize(logfile.name) > 0

    try:
        if os.path.exists(logfile.name):
            os.remove(logfile.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def noninteractive_mock_mycli(monkeypatch):
    class Formatter:
        format_name = None

    class Logger:
        def debug(self, *args, **args_dict):
            pass

        def error(self, *args, **args_dict):
            pass

        def warning(self, *args, **args_dict):
            pass

    class MockMyCli:
        connect_calls = 0
        ran_queries = []

        config = {
            'main': {
                'use_keyring': 'False',
            },
            'connection': {},
        }

        def __init__(self, **_args):
            self.logger = Logger()
            self.destructive_warning = False
            self.main_formatter = Formatter()
            self.redirect_formatter = Formatter()
            self.ssl_mode = 'auto'
            self.default_keepalive_ticks = 0
            self.config_without_package_defaults = {'connection': {}}

        def connect(self, **_args):
            MockMyCli.connect_calls += 1

        def run_query(self, query, checkpoint=None, new_line=True):
            MockMyCli.ran_queries.append(query)

        def run_cli(self):
            raise AssertionError('should not enter interactive cli')

        def close(self):
            pass

    import mycli.main

    monkeypatch.setattr(mycli.main, 'MyCli', MockMyCli)
    return mycli.main, mycli.main_modes.batch, MockMyCli


def test_execute_arg_warns_about_ignoring_stdin(monkeypatch):
    mycli_main, mycli_main_batch, MockMyCli = noninteractive_mock_mycli(monkeypatch)
    runner = CliRunner()

    # the test env should make sure stdin is not a TTY
    result = runner.invoke(mycli_main.click_entrypoint, args=['--execute', 'select 1;'])

    # this exit_code is as written currently, but a debatable choice,
    # since there was a warning
    assert result.exit_code == 0
    assert 'Ignoring STDIN' in result.output


def test_verbose_and_quiet_are_incompatible() -> None:
    runner = CliRunner()

    result = runner.invoke(click_entrypoint, args=['--verbose', '--quiet'])

    assert result.exit_code == 1
    assert 'incompatible.' in result.output


def test_quiet_sets_negative_cli_verbosity(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))

    cli_args = main.CliArgs()
    cli_args.quiet = True

    call_click_entrypoint_direct(cli_args)

    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.init_kwargs['cli_verbosity'] == -1


def test_resume_requires_batch() -> None:
    runner = CliRunner()

    result = runner.invoke(click_entrypoint, args=['--checkpoint', os.devnull, '--resume'])

    assert result.exit_code == 1
    assert 'Error:' in result.output


def test_resume_requires_checkpoint() -> None:
    runner = CliRunner()

    result = runner.invoke(click_entrypoint, args=['--batch', os.devnull, '--resume'])

    assert result.exit_code == 1
    assert 'Error:' in result.output


def test_execute_arg_supersedes_batch_file(monkeypatch):
    mycli_main, mycli_main_batch, MockMyCli = noninteractive_mock_mycli(monkeypatch)
    runner = CliRunner()

    with NamedTemporaryFile(prefix=TEMPFILE_PREFIX, mode='w', delete=False) as batch_file:
        batch_file.write('select 2;\n')
        batch_file.flush()

    try:
        result = runner.invoke(
            mycli_main.click_entrypoint,
            args=['--execute', 'select 1;', '--batch', batch_file.name],
        )
        # this exit_code is as written currently, but a debatable choice,
        # since there was a warning
        assert result.exit_code == 0
        assert MockMyCli.ran_queries == ['select 1;']
    finally:
        os.remove(batch_file.name)


@dbtest
def test_null_string_config(monkeypatch):
    monkeypatch.setattr(MyCli, 'system_config_files', [])
    runner = CliRunner()
    # keep Windows from locking the file with delete=False
    with NamedTemporaryFile(mode='w', delete=False) as myclirc:
        myclirc.write(
            dedent("""\
            [main]
            null_string = <nope>
            """)
        )
        myclirc.flush()
        args = CLI_ARGS_WITHOUT_DB + ['--myclirc', myclirc.name, '--format=table', '--execute', 'SELECT NULL']
        result = runner.invoke(main.click_entrypoint, args=args)
        assert '<nope>' in result.output
        assert '<null>' not in result.output

    # delete=False means we should try to clean up
    try:
        if os.path.exists(myclirc.name):
            os.remove(myclirc.name)
    except Exception as e:
        print(f'An error occurred while attempting to delete the file: {e}')


def test_change_prompt_format_requires_argument() -> None:
    cli = make_bare_mycli()
    assert main.MyCli.change_prompt_format(cli, '')[0].status == 'Missing required argument, format.'


def test_change_prompt_format_updates_prompt() -> None:
    cli = make_bare_mycli()
    assert main.MyCli.change_prompt_format(cli, '\\u@\\h> ')[0].status == 'Changed prompt format to \\u@\\h> '


def test_output_timing_logs_and_prints_with_warning_style(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    timings_logged: list[str] = []
    cli.log_output = lambda text: timings_logged.append(text)  # type: ignore[assignment]
    printed: list[tuple[Any, Any]] = []
    monkeypatch.setattr(prompt_toolkit, 'print_formatted_text', lambda text, style=None: printed.append((text, style)))
    main.MyCli.output_timing(cli, 'Time: 1.000s', is_warnings_style=True)
    assert timings_logged == ['Time: 1.000s']
    assert printed[-1][1] == cli.ptoolkit_style


def test_get_output_margin_uses_prompt_session_render_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    render_counters: list[int] = []
    cli.prompt_lines = 0
    cli.get_reserved_space = lambda: 2  # type: ignore[assignment]
    cli.prompt_session = cast(
        Any,
        SimpleNamespace(app=SimpleNamespace(render_counter=7)),
    )

    def fake_render_prompt_string(mycli: Any, string: str, render_counter: int) -> FormattedText:
        render_counters.append(render_counter)
        return to_formatted_text('line1\nline2')

    monkeypatch.setattr(repl_mode, 'render_prompt_string', fake_render_prompt_string)
    monkeypatch.setattr(mycli.packages.special, 'is_timing_enabled', lambda: False)
    assert main.MyCli.get_output_margin(cli, 'ok') == 5
    assert render_counters == [7]


def test_on_completions_refreshed_updates_completer_and_invalidates_prompt() -> None:
    cli = make_bare_mycli()
    entered_lock = {'count': 0}
    invalidated: list[bool] = []
    cli._completer_lock = cast(Any, ReusableLock(lambda: entered_lock.__setitem__('count', entered_lock['count'] + 1)))
    cli.prompt_session = cast(Any, SimpleNamespace(app=SimpleNamespace(invalidate=lambda: invalidated.append(True))))
    cli.completer = cast(Any, SimpleNamespace(dbmetadata={}))
    copy_calls: list[tuple[Any, str | None]] = []
    new_completer = cast(
        Any,
        SimpleNamespace(
            dbname='current',
            get_completions=lambda document, event: ['done'],
            copy_other_schemas_from=lambda source, exclude: copy_calls.append((source, exclude)),
        ),
    )
    main.MyCli._on_completions_refreshed(cli, new_completer)
    assert cli.completer is new_completer
    assert invalidated == [True]
    assert entered_lock['count'] == 1
    assert copy_calls == [(copy_calls[0][0], 'current')]


def test_click_entrypoint_callback_covers_dsn_list_init_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {'prod': 'mysql://u:p@h/db'},
            'alias_dsn.init-commands': {'prod': ['set a=1', 'set b=2']},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)

    cli_args = main.CliArgs()
    cli_args.dsn = 'prod'
    cli_args.init_command = 'set c=3'
    call_click_entrypoint_direct(cli_args)

    dummy = dummy_class.last_instance
    assert dummy is not None
    assert dummy.connect_calls[-1]['init_command'] == 'set a=1; set b=2; set c=3'


def test_click_entrypoint_callback_uses_batch_with_progress_path(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(mycli.cli_runner, 'main_batch_with_progress_bar', lambda mycli, cli_args: 12)

    cli_args = main.CliArgs()
    cli_args.batch = 'queries.sql'
    cli_args.progress = True
    with pytest.raises(SystemExit) as excinfo:
        call_click_entrypoint_direct(cli_args)
    assert excinfo.value.code == 12


def test_click_entrypoint_callback_uses_batch_without_progress_path(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_class = make_dummy_mycli_class(
        config={
            'main': {'use_keyring': 'false'},
            'connection': {'default_keepalive_ticks': 0},
            'alias_dsn': {},
        }
    )
    monkeypatch.setattr(main, 'MyCli', dummy_class)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(sys.stderr, 'isatty', lambda: True)
    monkeypatch.setattr(mycli.cli_runner, 'main_batch_without_progress_bar', lambda mycli, cli_args: 13)

    cli_args = main.CliArgs()
    cli_args.batch = 'queries.sql'
    cli_args.progress = False
    with pytest.raises(SystemExit) as excinfo:
        call_click_entrypoint_direct(cli_args)
    assert excinfo.value.code == 13


def test_format_sqlresult_uses_redirect_formatter_when_redirected() -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    cli.redirect_formatter = DummyFormatter()

    result = SQLResult(header=['id'], rows=[(1,)], status='ok')
    assert list(main.MyCli.format_sqlresult(cli, result, is_redirected=True)) == ['plain output']

    assert cli.main_formatter.calls == []
    assert len(cli.redirect_formatter.calls) == 1


def test_format_sqlresult_materializes_cursor_rows_when_width_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.main_formatter = DummyFormatter()
    rows = FakeCursorBase(rows=[(1,)], rowcount=1, description=[('id', 3)])
    monkeypatch.setattr(output_module, 'Cursor', FakeCursorBase)

    result = SQLResult(header=['id'], rows=cast(Any, rows), status='ok')
    list(main.MyCli.format_sqlresult(cli, result, max_width=100))

    formatted_rows = cli.main_formatter.calls[-1][0][0]
    assert formatted_rows == [(1,)]


def test_format_sqlresult_appends_postamble() -> None:
    cli = make_bare_mycli()
    result = SQLResult(header=['id'], rows=[(1,)], status='ok', postamble='done')

    assert list(main.MyCli.format_sqlresult(cli, result))[-1] == 'done'


def test_get_last_query_returns_latest_query() -> None:
    cli = make_bare_mycli()
    cli.query_history = [Query('select 1', True, False)]

    assert main.MyCli.get_last_query(cli) == 'select 1'


def test_connect_reports_expired_password_login_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config_without_package_defaults = {'connection': {}}
    cli.config = {'connection': {}, 'main': {}}
    cli.logger = cast(Any, DummyLogger())
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(str(message))  # type: ignore[assignment]
    monkeypatch.setattr(mycli.client_connection, 'WIN', False)
    monkeypatch.setattr(mycli.client_connection, 'str_to_bool', lambda value: False)

    class ExpiredPasswordSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = [pymysql.OperationalError(ER_MUST_CHANGE_PASSWORD_LOGIN, 'must change password')]

    monkeypatch.setattr(mycli.client_connection, 'SQLExecute', ExpiredPasswordSQLExecute)

    with pytest.raises(SystemExit):
        main.MyCli.connect(cli, host='db', port=3307)

    assert any('password has expired' in message for message in echo_calls)


def test_connect_sets_cli_sandbox_mode_when_sqlexecute_enters_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    cli = make_bare_mycli()
    cli.config_without_package_defaults = {'connection': {}}
    cli.config = {'connection': {}, 'main': {}}
    cli.logger = cast(Any, DummyLogger())
    echo_calls: list[str] = []
    cli.echo = lambda message, **kwargs: echo_calls.append(str(message))  # type: ignore[assignment]
    monkeypatch.setattr(mycli.client_connection, 'WIN', False)
    monkeypatch.setattr(mycli.client_connection, 'str_to_bool', lambda value: False)

    class SandboxSQLExecute(RecordingSQLExecute):
        calls: list[dict[str, Any]] = []
        side_effects: list[Any] = []

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.sandbox_mode = True

    monkeypatch.setattr(mycli.client_connection, 'SQLExecute', SandboxSQLExecute)

    main.MyCli.connect(cli, host='db', port=3307)

    assert cli.sandbox_mode is True
    assert any('password has expired' in message for message in echo_calls)


def valid_connection_scheme(value: str) -> tuple[bool, str | None]:
    scheme, _, _ = value.partition('://')
    return scheme == 'mysql', scheme or None


def test_int_or_string_click_type_accepts_int_string_and_none() -> None:
    assert INT_OR_STRING_CLICK_TYPE.convert(7, None, None) == 7
    assert INT_OR_STRING_CLICK_TYPE.convert('secret', None, None) == 'secret'
    assert INT_OR_STRING_CLICK_TYPE.convert(None, None, None) is None


def test_int_or_string_click_type_rejects_other_values() -> None:
    with pytest.raises(click.BadParameter, match='Not a valid password string'):
        INT_OR_STRING_CLICK_TYPE.convert(object(), None, None)


def test_get_password_from_file_reads_first_line_without_trailing_newline(tmp_path: Path) -> None:
    password_file = tmp_path / 'password.txt'
    password_file.write_text('secret\nignored\n', encoding='utf8')

    assert get_password_from_file(str(password_file)) == 'secret'


def test_get_password_from_file_returns_none_for_missing_path() -> None:
    assert get_password_from_file(None) is None
    assert get_password_from_file('') is None


@pytest.mark.parametrize(
    ('exception', 'expected'),
    [
        (FileNotFoundError(), "Password file 'secret.txt' not found"),
        (PermissionError(), "Permission denied reading password file 'secret.txt'"),
        (IsADirectoryError(), "Path 'secret.txt' is a directory, not a file"),
        (RuntimeError('boom'), "Error reading password file 'secret.txt': boom"),
    ],
)
def test_get_password_from_file_exits_with_error_for_read_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception: Exception,
    expected: str,
) -> None:
    def raise_error(*_args: Any, **_kwargs: Any) -> None:
        raise exception

    monkeypatch.setattr(builtins, 'open', raise_error)

    with pytest.raises(SystemExit) as excinfo:
        get_password_from_file('secret.txt')

    assert excinfo.value.code == 1
    assert expected in capsys.readouterr().err


def test_preprocess_cli_args_moves_dsn_from_password_to_database() -> None:
    cli_args = CliArgs()
    cli_args.password = 'mysql://user:pass@host/db'

    verbosity = preprocess_cli_args(cli_args, valid_connection_scheme)

    assert verbosity == 0
    assert cli_args.database == 'mysql://user:pass@host/db'
    assert cli_args.password == EMPTY_PASSWORD_FLAG_SENTINEL  # type: ignore[comparison-overlap]


def test_preprocess_cli_args_rejects_unknown_dsn_scheme(capsys: pytest.CaptureFixture[str]) -> None:
    cli_args = CliArgs()
    cli_args.password = 'postgres://user:pass@host/db'

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert 'Unknown connection scheme provided for DSN URI (postgres://)' in capsys.readouterr().err


def test_preprocess_cli_args_preserves_password_file_when_password_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = CliArgs()
    cli_args.password_file = 'secret.txt'
    get_password_calls: list[str] = []
    monkeypatch.setattr(main, 'get_password_from_file', lambda password_file: get_password_calls.append(password_file))

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password is None
    assert cli_args.password_file == 'secret.txt'
    assert get_password_calls == []


def test_preprocess_cli_args_preserves_mysql_pwd_when_password_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = CliArgs()
    monkeypatch.setenv('MYSQL_PWD', 'env-secret')

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password is None


def test_preprocess_cli_args_prefers_existing_password_over_mysql_pwd(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = CliArgs()
    cli_args.password = 'cli-secret'
    monkeypatch.setenv('MYSQL_PWD', 'env-secret')

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password == 'cli-secret'


def test_click_entrypoint_populates_password_vault_options(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args_calls: list[CliArgs] = []
    monkeypatch.setattr(main, 'run_from_cli_args', lambda cli_args, client_factory: cli_args_calls.append(cli_args))

    result = CliRunner().invoke(
        click_entrypoint,
        [
            '--vault-address',
            'https://vault.example.com',
            '--vault-mount',
            'kv',
            '--vault-secret',
            'database/prod',
            '--vault-password-field',
            'mysql_password',
            '--vault-username-field',
            'mysql_username',
        ],
    )

    assert result.exit_code == 0
    assert cli_args_calls[-1].vault_address == 'https://vault.example.com'
    assert cli_args_calls[-1].vault_mount == 'kv'
    assert cli_args_calls[-1].vault_secret == 'database/prod'
    assert cli_args_calls[-1].vault_password_field == 'mysql_password'
    assert cli_args_calls[-1].vault_username_field == 'mysql_username'


@pytest.mark.parametrize(
    ('checkpoint', 'batch', 'expected'),
    [
        (None, 'batch.sql', 'Error: --resume requires a --checkpoint file.'),
        (object(), None, 'Error: --resume requires a --batch file.'),
    ],
)
def test_preprocess_cli_args_validates_resume_requirements(
    capsys: pytest.CaptureFixture[str],
    checkpoint: object | None,
    batch: str | None,
    expected: str,
) -> None:
    cli_args = CliArgs()
    cli_args.resume = True
    cli_args.checkpoint = checkpoint  # type: ignore[assignment]
    cli_args.batch = batch

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert expected in capsys.readouterr().err


def test_preprocess_cli_args_rejects_same_batch_and_checkpoint_file(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    batch_path = tmp_path / 'batch.sql'
    batch_path.write_text('select 1;\n', encoding='utf-8')
    cli_args = CliArgs()
    cli_args.batch = str(batch_path)
    cli_args.checkpoint = str(batch_path)

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert 'Error: --batch and --checkpoint must be different files.' in capsys.readouterr().err


def test_preprocess_cli_args_rejects_same_batch_and_logfile(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    batch_path = tmp_path / 'batch.sql'
    batch_path.write_text('select 1;\n', encoding='utf-8')
    cli_args = CliArgs()
    cli_args.batch = str(batch_path)
    cli_args.logfile = batch_path.open('a', encoding='utf-8')  # type: ignore[assignment]

    try:
        with pytest.raises(SystemExit) as excinfo:
            preprocess_cli_args(cli_args, valid_connection_scheme)
    finally:
        cli_args.logfile.close()

    assert excinfo.value.code == 1
    assert 'Error: --batch and --logfile must be different files.' in capsys.readouterr().err


def test_preprocess_cli_args_rejects_verbose_and_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    cli_args = CliArgs()
    cli_args.verbose = 1
    cli_args.quiet = True

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert 'Error: --verbose and --quiet are incompatible.' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('verbose', 'quiet', 'expected'),
    [
        (2, False, 2),
        (0, True, -1),
        (0, False, 0),
    ],
)
def test_preprocess_cli_args_returns_cli_verbosity(verbose: int, quiet: bool, expected: int) -> None:
    cli_args = CliArgs()
    cli_args.verbose = verbose
    cli_args.quiet = quiet

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == expected

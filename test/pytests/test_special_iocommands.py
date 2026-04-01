# type: ignore

import builtins
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from time import time
from types import SimpleNamespace
from typing import Any, Generator
from unittest.mock import patch

from pymysql import ProgrammingError
import pytest

import mycli.packages.special
from mycli.packages.special import iocommands
from mycli.packages.sqlresult import SQLResult
from test.utils import TEMPFILE_PREFIX, db_connection, dbtest, send_ctrl_c


class FakeFavoriteQueries:
    usage = '\nFAKE FAVORITES'

    def __init__(self, queries: dict[str, str] | None = None) -> None:
        self.queries = {} if queries is None else dict(queries)
        self.saved: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def list(self) -> list[str]:
        return list(self.queries)

    def get(self, name: str) -> str | None:
        return self.queries.get(name)

    def save(self, name: str, query: str) -> None:
        self.saved.append((name, query))
        self.queries[name] = query

    def delete(self, name: str) -> str:
        self.deleted.append(name)
        return f'{name}: Deleted.'


class FakeCursor:
    def __init__(self, descriptions: dict[str, list[tuple[str]] | None] | None = None) -> None:
        self.descriptions = {} if descriptions is None else descriptions
        self.description: list[tuple[str]] | None = None
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        self.description = self.descriptions.get(sql)


class SequenceCursor:
    def __init__(self, descriptions: list[list[tuple[str]] | None]) -> None:
        self.descriptions = descriptions
        self.description: list[tuple[str]] | None = None
        self.executed: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        self.description = self.descriptions.pop(0)


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes | str = b'',
        stderr: bytes | str = b'',
        returncode: int = 0,
        raise_timeout: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.raise_timeout = raise_timeout
        self.communicate_calls = 0
        self.communicate_timeouts: list[int | None] = []
        self.killed = False

    def communicate(self, input: str | None = None, timeout: int | None = None) -> tuple[bytes | str, bytes | str]:  # noqa: A002
        self.communicate_calls += 1
        self.communicate_timeouts.append(timeout)
        if self.raise_timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd='fake', timeout=timeout or 0)
        return (self.stdout, self.stderr)

    def kill(self) -> None:
        self.killed = True


@pytest.fixture(autouse=True)
def reset_iocommands_state(monkeypatch) -> Generator[None, None, None]:
    original_timing = iocommands.TIMING_ENABLED
    original_pager = iocommands.PAGER_ENABLED
    original_show_favorite = iocommands.SHOW_FAVORITE_QUERY
    original_force_horizontal = iocommands.force_horizontal_output
    original_destructive_keywords = list(iocommands.DESTRUCTIVE_KEYWORDS)
    original_once_file = iocommands.once_file
    original_tee_file = iocommands.tee_file
    original_written = iocommands.written_to_once_file
    original_pipe_once = dict(iocommands.PIPE_ONCE)
    original_favoritequeries = iocommands.favoritequeries
    had_instance = hasattr(iocommands.FavoriteQueries, 'instance')
    original_instance = getattr(iocommands.FavoriteQueries, 'instance', None)

    yield

    if iocommands.once_file and iocommands.once_file is not original_once_file:
        iocommands.once_file.close()
    if iocommands.tee_file and iocommands.tee_file is not original_tee_file:
        iocommands.tee_file.close()

    iocommands.TIMING_ENABLED = original_timing
    iocommands.PAGER_ENABLED = original_pager
    iocommands.SHOW_FAVORITE_QUERY = original_show_favorite
    iocommands.force_horizontal_output = original_force_horizontal
    iocommands.DESTRUCTIVE_KEYWORDS = original_destructive_keywords
    iocommands.once_file = original_once_file
    iocommands.tee_file = original_tee_file
    iocommands.written_to_once_file = original_written
    iocommands.PIPE_ONCE.clear()
    iocommands.PIPE_ONCE.update(original_pipe_once)
    iocommands.favoritequeries = original_favoritequeries
    if had_instance:
        iocommands.FavoriteQueries.instance = original_instance


@pytest.fixture
def favorite_queries_instance(monkeypatch) -> None:
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', iocommands.favoritequeries, raising=False)


def test_set_get_pager(monkeypatch):
    monkeypatch.setenv('PAGER', '')
    mycli.packages.special.set_pager_enabled(True)
    assert mycli.packages.special.is_pager_enabled()
    mycli.packages.special.set_pager_enabled(False)
    assert not mycli.packages.special.is_pager_enabled()
    mycli.packages.special.set_pager("less")
    assert os.environ["PAGER"] == "less"
    mycli.packages.special.set_pager(False)
    assert os.environ["PAGER"] == "less"
    del os.environ["PAGER"]
    mycli.packages.special.set_pager(False)
    mycli.packages.special.disable_pager()
    assert not mycli.packages.special.is_pager_enabled()


def test_set_get_timing():
    mycli.packages.special.set_timing_enabled(True)
    assert mycli.packages.special.is_timing_enabled()
    mycli.packages.special.set_timing_enabled(False)
    assert not mycli.packages.special.is_timing_enabled()


def test_set_get_expanded_output():
    mycli.packages.special.set_expanded_output(True)
    assert mycli.packages.special.is_expanded_output()
    mycli.packages.special.set_expanded_output(False)
    assert not mycli.packages.special.is_expanded_output()


def test_editor_command(monkeypatch):
    monkeypatch.setenv('EDITOR', 'true')
    monkeypatch.setenv('VISUAL', 'true')

    assert mycli.packages.special.editor_command(r"hello\e")
    assert mycli.packages.special.editor_command(r"hello\edit")
    assert mycli.packages.special.editor_command(r"\e hello")
    assert mycli.packages.special.editor_command(r"\edit hello")

    assert not mycli.packages.special.editor_command(r"hello")
    assert not mycli.packages.special.editor_command(r"\ehello")
    assert not mycli.packages.special.editor_command(r"\edithello")

    assert mycli.packages.special.get_filename(r"\e filename") == "filename"

    if os.name != "nt":
        assert mycli.packages.special.open_external_editor(sql=r"select 1") == ('select 1', None)
    else:
        pytest.skip("Skipping on Windows platform.")


def test_tee_command():
    mycli.packages.special.write_tee("hello world")  # write without file set
    # keep Windows from locking the file with delete=False
    with tempfile.NamedTemporaryFile(prefix=TEMPFILE_PREFIX, delete=False) as f:
        mycli.packages.special.execute(None, "tee " + f.name)
        mycli.packages.special.write_tee("hello world")
        if os.name == "nt":
            assert f.read() == b"hello world\r\n"
        else:
            assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, "tee -o " + f.name)
        mycli.packages.special.write_tee("hello world")
        f.seek(0)
        if os.name == "nt":
            assert f.read() == b"hello world\r\n"
        else:
            assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, "notee")
        mycli.packages.special.write_tee("hello world")
        f.seek(0)
        if os.name == "nt":
            assert f.read() == b"hello world\r\n"
        else:
            assert f.read() == b"hello world\n"

    # remove temp file
    # delete=False means we should try to clean up
    try:
        if os.path.exists(f.name):
            os.remove(f.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def test_tee_command_error():
    with pytest.raises(TypeError):
        mycli.packages.special.execute(None, "tee")

    with pytest.raises(OSError):
        with tempfile.NamedTemporaryFile(prefix=TEMPFILE_PREFIX) as f:
            os.chmod(f.name, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            mycli.packages.special.execute(None, f"tee {f.name}")


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_favorite_query(favorite_queries_instance) -> None:
    with db_connection().cursor() as cur:
        query = 'select "✔"'
        mycli.packages.special.execute(cur, f"\\fs check {query}")
        assert next(mycli.packages.special.execute(cur, "\\f check")).preamble == "> " + query


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: fails on Windows, needs fixing, singleton of FQ not working right")
def test_special_favorite_query(favorite_queries_instance) -> None:
    with db_connection().cursor() as cur:
        query = r'\?'
        mycli.packages.special.execute(cur, rf"\fs special {query}")
        assert (r'\G', None, r'<query>\G', 'Display query results vertically.') in next(
            mycli.packages.special.execute(cur, r'\f special')
        ).rows


def test_once_command():
    with pytest.raises(TypeError):
        mycli.packages.special.execute(None, "\\once")

    with pytest.raises(OSError):
        mycli.packages.special.execute(None, "\\once /proc/access-denied")

    mycli.packages.special.write_once("hello world")  # write without file set
    # keep Windows from locking the file with delete=False
    with tempfile.NamedTemporaryFile(prefix=TEMPFILE_PREFIX, delete=False) as f:
        mycli.packages.special.execute(None, "\\once " + f.name)
        mycli.packages.special.write_once("hello world")
        if os.name == "nt":
            assert f.read() == b"hello world\r\n"
        else:
            assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, "\\once -o " + f.name)
        mycli.packages.special.write_once("hello world line 1")
        mycli.packages.special.write_once("hello world line 2")
        f.seek(0)
        if os.name == "nt":
            assert f.read() == b"hello world line 1\r\nhello world line 2\r\n"
        else:
            assert f.read() == b"hello world line 1\nhello world line 2\n"
    # delete=False means we should try to clean up
    try:
        if os.path.exists(f.name):
            os.remove(f.name)
    except Exception as e:
        print(f"An error occurred while attempting to delete the file: {e}")


def test_pipe_once_command():
    with pytest.raises(IOError):
        mycli.packages.special.execute(None, "\\pipe_once")

    with pytest.raises(OSError):
        mycli.packages.special.execute(None, "\\pipe_once /proc/access-denied")
        mycli.packages.special.write_pipe_once("select 1")
        mycli.packages.special.flush_pipe_once_if_written(None)

    if os.name == "nt":
        mycli.packages.special.execute(None, '\\pipe_once python -c "import sys; print(len(sys.stdin.read().strip()))"')
        mycli.packages.special.write_once("hello world")
        mycli.packages.special.flush_pipe_once_if_written(None)
    else:
        with tempfile.NamedTemporaryFile(prefix=TEMPFILE_PREFIX) as f:
            mycli.packages.special.execute(None, "\\pipe_once tee " + f.name)
            mycli.packages.special.write_pipe_once("hello world")
            mycli.packages.special.flush_pipe_once_if_written(None)
            f.seek(0)
            assert f.read() == b"hello world\n"


def test_parseargfile():
    """Test that parseargfile expands the user directory."""
    expected = (os.path.join(os.path.expanduser("~"), "filename"), "a")

    if os.name == "nt":
        assert expected == mycli.packages.special.iocommands.parseargfile("~\\filename")
    else:
        assert expected == mycli.packages.special.iocommands.parseargfile("~/filename")

    expected = (os.path.join(os.path.expanduser("~"), "filename"), "w")
    if os.name == "nt":
        assert expected == mycli.packages.special.iocommands.parseargfile("-o ~\\filename")
    else:
        assert expected == mycli.packages.special.iocommands.parseargfile("-o ~/filename")


def test_parseargfile_no_file():
    """Test that parseargfile raises a TypeError if there is no filename."""
    with pytest.raises(TypeError):
        mycli.packages.special.iocommands.parseargfile("")

    with pytest.raises(TypeError):
        mycli.packages.special.iocommands.parseargfile("-o ")


@dbtest
def test_watch_query_iteration():
    """Test that a single iteration of the result of `watch_query` executes
    the desired query and returns the given results."""
    expected_value = "1"
    query = f"SELECT {expected_value}"
    expected_preamble = f"> {query}"
    with db_connection().cursor() as cur:
        result = next(mycli.packages.special.iocommands.watch_query(arg=query, cur=cur))
    assert result.preamble == expected_preamble
    assert result.header[0] == expected_value


@dbtest
@pytest.mark.skipif(os.name == "nt", reason="Bug: Win handles this differently.  May need to refactor watch_query to work for Win")
def test_watch_query_full():
    """Test that `watch_query`:

    * Returns the expected results.
    * Executes the defined times inside the given interval, in this case with
      a 0.3 seconds wait, it should execute 4 times inside a 1 seconds
      interval.
    * Stops at Ctrl-C

    """
    watch_seconds = 0.3
    wait_interval = 1
    expected_value = "1"
    query = f"SELECT {expected_value}"
    expected_preamble = f"> {query}"
    # Python 3.14 is skipping ahead to 6 or 7
    # Python 3.11 is as slow as 3
    expected_results = [3, 4, 5, 6, 7]
    ctrl_c_process = send_ctrl_c(wait_interval)
    with db_connection().cursor() as cur:
        results = list(mycli.packages.special.iocommands.watch_query(arg=f"{watch_seconds} {query}", cur=cur))
    ctrl_c_process.join(1)
    assert len(results) in expected_results
    for result in results:
        assert result.preamble == expected_preamble
        assert result.header[0] == expected_value


@dbtest
@patch("click.clear")
def test_watch_query_clear(clear_mock):
    """Test that the screen is cleared with the -c flag of `watch` command
    before execute the query."""
    with db_connection().cursor() as cur:
        watch_gen = mycli.packages.special.iocommands.watch_query(arg="0.1 -c select 1;", cur=cur)
        assert not clear_mock.called
        next(watch_gen)
        assert clear_mock.called
        clear_mock.reset_mock()
        next(watch_gen)
        assert clear_mock.called
        clear_mock.reset_mock()


@dbtest
def test_watch_query_bad_arguments():
    """Test different incorrect combinations of arguments for `watch`
    command."""
    watch_query = mycli.packages.special.iocommands.watch_query
    with db_connection().cursor() as cur:
        with pytest.raises(ProgrammingError):
            next(watch_query("a select 1;", cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query("-a select 1;", cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query("1 -a select 1;", cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query("-c -a select 1;", cur=cur))


@dbtest
@patch("click.clear")
def test_watch_query_interval_clear(clear_mock):
    """Test `watch` command with interval and clear flag."""

    def test_asserts(gen):
        clear_mock.reset_mock()
        start = time()
        next(gen)
        assert clear_mock.called
        next(gen)
        exec_time = time() - start
        assert exec_time > seconds and exec_time < (seconds + seconds)

    seconds = 1.0
    watch_query = mycli.packages.special.iocommands.watch_query
    with db_connection().cursor() as cur:
        test_asserts(watch_query(f"{seconds} -c select 1;", cur=cur))
        test_asserts(watch_query(f"-c {seconds} select 1;", cur=cur))


def test_split_sql_by_delimiter():
    for delimiter_str in (";", "$", "😀"):
        mycli.packages.special.set_delimiter(delimiter_str)
        sql_input = f"select 1{delimiter_str} select \ufffc2"
        queries = ("select 1", "select \ufffc2")
        for query, parsed_query in zip(queries, mycli.packages.special.split_queries(sql_input), strict=True):
            assert query == parsed_query


def test_switch_delimiter_within_query():
    mycli.packages.special.set_delimiter(";")
    sql_input = "select 1; delimiter $$ select 2 $$ select 3 $$"
    queries = ("select 1", "delimiter $$ select 2 $$ select 3 $$")
    for query, parsed_query in zip(queries, mycli.packages.special.split_queries(sql_input), strict=True):
        assert query == parsed_query


def test_set_delimiter():
    for delim in ("foo", "bar"):
        mycli.packages.special.set_delimiter(delim)
        assert mycli.packages.special.get_current_delimiter() == delim


def teardown_function():
    mycli.packages.special.set_delimiter(";")


def test_simple_setters_and_toggle_timing() -> None:
    config = {'favorite_queries': {'demo': 'select 1'}}

    iocommands.set_favorite_queries(config)
    assert iocommands.favoritequeries.config is config

    iocommands.set_show_favorite_query(False)
    assert iocommands.is_show_favorite_query() is False

    iocommands.set_destructive_keywords(['drop'])
    assert iocommands.DESTRUCTIVE_KEYWORDS == ['drop']

    iocommands.set_forced_horizontal_output(True)
    assert iocommands.forced_horizontal() is True

    iocommands.set_timing_enabled(False)
    assert iocommands.toggle_timing()[0].status == 'Timing is on.'
    assert iocommands.toggle_timing()[0].status == 'Timing is off.'


def test_editor_helpers_strip_commands() -> None:
    assert iocommands.get_filename(r'\edit  ') is None
    assert iocommands.get_filename('select 1') is None
    assert iocommands.get_editor_query(r' select * from style\edit\e ') == 'select * from style'


def test_open_external_editor_filename_paths(monkeypatch, tmp_path: Path) -> None:
    filename = tmp_path / 'query.sql'
    filename.write_text('select 1\n', encoding='utf-8')
    edit_calls: list[str] = []

    monkeypatch.setattr(iocommands.click, 'edit', lambda filename: edit_calls.append(filename))
    query, message = iocommands.open_external_editor(filename=f'{filename} ignored', sql='unused')

    assert query == 'select 1'
    assert message is None
    assert edit_calls == [str(filename)]

    def raise_ioerror(*_args, **_kwargs):
        raise IOError('boom')

    monkeypatch.setattr(iocommands.click, 'edit', lambda filename: None)
    monkeypatch.setattr(builtins, 'open', raise_ioerror)

    query, message = iocommands.open_external_editor(filename=str(filename))

    assert query == ''
    assert message == f'Error reading file: {filename}'


def test_open_external_editor_without_filename(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    marker = '# Type your query above this line.\n'

    def fake_edit(text: str, extension: str) -> str:
        calls.append((text, extension))
        return f'select 1\n\n{marker}ignored'

    monkeypatch.setattr(iocommands.click, 'edit', fake_edit)
    query, message = iocommands.open_external_editor(sql='select 1')

    assert query == 'select 1'
    assert message is None
    assert calls == [(f'select 1\n\n{marker}', '.sql')]

    monkeypatch.setattr(iocommands.click, 'edit', lambda text, extension: None)
    query, message = iocommands.open_external_editor(sql='select fallback')

    assert query == 'select fallback'
    assert message is None


def test_clip_helpers_and_clipboard(monkeypatch) -> None:
    assert iocommands.clip_command(r'\clip select 1')
    assert iocommands.clip_command(r'select 1 \clip')
    assert not iocommands.clip_command(r'select 1')
    assert iocommands.get_clip_query(r'\clip select 1\clip') == ' select 1'

    copied: list[str] = []
    monkeypatch.setattr(iocommands.pyperclip, 'copy', lambda text: copied.append(text))
    assert iocommands.copy_query_to_clipboard('select 1') is None
    assert copied == ['select 1']

    def raise_runtime_error(_text: str) -> None:
        raise RuntimeError('no clipboard')

    monkeypatch.setattr(iocommands.pyperclip, 'copy', raise_runtime_error)
    assert iocommands.copy_query_to_clipboard() == 'Error clipping query: no clipboard.'


def test_set_redirect_routes_to_pipe_once_and_once(monkeypatch) -> None:
    pipe_calls: list[str] = []
    once_calls: list[str] = []

    def fake_set_pipe_once(arg: str) -> list[tuple[str]]:
        pipe_calls.append(arg)
        return [('pipe',)]

    def fake_set_once(arg: str) -> list[tuple[str]]:
        once_calls.append(arg)
        return [('once',)]

    monkeypatch.setattr(iocommands, 'set_pipe_once', fake_set_pipe_once)
    monkeypatch.setattr(iocommands, 'set_once', fake_set_once)

    iocommands.PIPE_ONCE['stdout_file'] = None
    iocommands.PIPE_ONCE['stdout_mode'] = None
    result = iocommands.set_redirect('cat', '>', 'out.txt')
    assert result == [('pipe',)]
    assert pipe_calls == ['cat']
    assert iocommands.PIPE_ONCE['stdout_file'] == 'out.txt'
    assert iocommands.PIPE_ONCE['stdout_mode'] == 'w'

    assert iocommands.set_redirect(None, '>', 'other.txt') == [('once',)]
    assert iocommands.set_redirect(None, None, 'append.txt') == [('once',)]
    assert once_calls == ['-o other.txt', 'append.txt']


def test_execute_favorite_query_list_missing_and_bad_args(monkeypatch) -> None:
    favorite_queries = FakeFavoriteQueries({'demo': 'select $1'})
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', favorite_queries, raising=False)

    listed = SQLResult(status='listed')
    monkeypatch.setattr(iocommands, 'list_favorite_queries', lambda: [listed])
    assert list(iocommands.execute_favorite_query(FakeCursor(), '')) == [listed]

    missing = list(iocommands.execute_favorite_query(FakeCursor(), 'unknown'))
    assert missing[0].status == 'No favorite query: unknown'

    bad_args = list(iocommands.execute_favorite_query(FakeCursor(), 'demo'))
    assert bad_args[0].status == 'missing substitution for $1 in query:\n  select $1'


def test_execute_favorite_query_special_and_plain_sql(monkeypatch) -> None:
    favorite_queries = FakeFavoriteQueries({'combo': 'help demo; select 1'})
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', favorite_queries, raising=False)
    monkeypatch.setattr(iocommands, 'SPECIAL_COMMANDS', {'help': object()})
    monkeypatch.setattr(iocommands, 'special_execute', lambda cur, sql: [SQLResult(status=f'ran {sql}')])

    cursor = FakeCursor({'select 1': None})
    results = list(iocommands.execute_favorite_query(cursor, 'combo'))

    assert results[0].status == 'ran help demo'
    assert results[0].preamble == '> help demo'
    assert results[1].preamble == '> select 1'
    assert results[1].header is None
    assert cursor.executed == ['select 1']


def test_execute_favorite_query_returns_header_for_result_sets(monkeypatch) -> None:
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', FakeFavoriteQueries({'rows': 'select 2'}), raising=False)

    cursor = FakeCursor({'select 2': [('col',)]})
    results = list(iocommands.execute_favorite_query(cursor, 'rows'))

    assert results[0].preamble == '> select 2'
    assert results[0].header == ['col']
    assert results[0].rows is cursor


def test_list_substitute_save_delete_and_redirect_state(tmp_path: Path, monkeypatch) -> None:
    empty_favorites = FakeFavoriteQueries()
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', empty_favorites, raising=False)
    empty_result = iocommands.list_favorite_queries()[0]
    assert empty_result.header == ['Name', 'Query']
    assert empty_result.rows == []
    assert empty_result.status == '\nNo favorite queries found.' + empty_favorites.usage

    populated_favorites = FakeFavoriteQueries({'demo': 'select 1'})
    monkeypatch.setattr(iocommands.FavoriteQueries, 'instance', populated_favorites, raising=False)
    rows_result = iocommands.list_favorite_queries()[0]
    assert rows_result.rows == [('demo', 'select 1')]
    assert rows_result.status == ''

    assert iocommands.subst_favorite_query_args('select $1', ['x']) == ['select x', None]
    assert iocommands.subst_favorite_query_args('select 1', ['x']) == [None, 'query does not have substitution parameter $1:\n  select 1']
    assert iocommands.subst_favorite_query_args('select $1, $2', ['x']) == [None, 'missing substitution for $2 in query:\n  select x, $2']

    assert iocommands.save_favorite_query('', cur=None)[0].status == 'Syntax: \\fs name query.\n\n' + populated_favorites.usage
    assert iocommands.save_favorite_query('onlyname', cur=None)[0].status == (
        'Syntax: \\fs name query.\n\n' + populated_favorites.usage + ' Err: Both name and query are required.'
    )
    assert iocommands.save_favorite_query('saved select 2', cur=None)[0].status == 'Saved.'
    assert populated_favorites.saved == [('saved', 'select 2')]

    assert iocommands.delete_favorite_query('', cur=None)[0].status == 'Syntax: \\fd name.\n\n' + populated_favorites.usage
    assert iocommands.delete_favorite_query('saved', cur=None)[0].status == 'saved: Deleted.'
    assert populated_favorites.deleted == ['saved']

    iocommands.once_file = None
    iocommands.PIPE_ONCE['process'] = None
    assert iocommands.is_redirected() is False
    redirect_file = (tmp_path / 'redirect.txt').open('w', encoding='utf-8')
    iocommands.once_file = redirect_file
    assert iocommands.is_redirected() is True
    redirect_file.close()
    iocommands.once_file = None
    iocommands.PIPE_ONCE['process'] = SimpleNamespace()
    assert iocommands.is_redirected() is True


def test_execute_system_command_usage_parse_and_cd(monkeypatch) -> None:
    usage = 'Syntax: system [-r] [command].\n-r denotes "raw" mode, in which output is passed through without formatting.'
    assert iocommands.execute_system_command('')[0].status == usage
    assert iocommands.execute_system_command('-r')[0].status == usage

    def raise_value_error(*_args, **_kwargs):
        raise ValueError('bad quoting')

    monkeypatch.setattr(iocommands.shlex, 'split', raise_value_error)
    assert iocommands.execute_system_command('broken')[0].status == 'Cannot parse system command: bad quoting'

    monkeypatch.setattr(iocommands.shlex, 'split', lambda arg, posix: ['cd', '/tmp'])
    monkeypatch.setattr(iocommands, 'handle_cd_command', lambda command: (False, 'cd failed'))
    assert iocommands.execute_system_command('cd /tmp')[0].status == 'cd failed'

    monkeypatch.setattr(iocommands, 'handle_cd_command', lambda command: (True, None))
    success_result = iocommands.execute_system_command('cd /tmp')[0]
    assert success_result.status is None
    assert success_result.preamble is None


@pytest.mark.parametrize(
    ('command', 'returncode', 'expected_status'),
    [
        ('-r echo ok', 0, None),
        ('vim file.sql', 1, 'Command exited with return code 1'),
    ],
)
def test_execute_system_command_raw_modes(
    monkeypatch,
    command: str,
    returncode: int,
    expected_status: str | None,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool = False) -> SimpleNamespace:
        calls.append(cmd)
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(iocommands.subprocess, 'run', fake_run)
    result = iocommands.execute_system_command(command)[0]

    assert calls
    assert result.status == expected_status


def test_execute_system_command_nonraw_paths(monkeypatch) -> None:
    monkeypatch.setattr(iocommands.locale, 'getpreferredencoding', lambda do_setlocale: 'utf-8')

    timeout_process = FakeProcess(stdout=b'timed out output', stderr=b'', returncode=0, raise_timeout=True)
    timeout_popen_calls: list[tuple[list[str], int, int]] = []

    def fake_timeout_popen(command: list[str], stdout: int, stderr: int) -> FakeProcess:
        timeout_popen_calls.append((command, stdout, stderr))
        return timeout_process

    monkeypatch.setattr(
        iocommands.subprocess,
        'Popen',
        fake_timeout_popen,
    )
    result = iocommands.execute_system_command('echo slow')[0]
    assert result.preamble == 'timed out output'
    assert result.status is None
    assert timeout_popen_calls == [
        (
            ['echo', 'slow'],
            iocommands.subprocess.PIPE,
            iocommands.subprocess.PIPE,
        )
    ]
    assert timeout_process.communicate_timeouts == [60, None]
    assert timeout_process.killed is True

    error_process = FakeProcess(stdout=b'ignored', stderr=b'boom', returncode=7)
    error_popen_calls: list[tuple[list[str], int, int]] = []

    def fake_error_popen(command: list[str], stdout: int, stderr: int) -> FakeProcess:
        error_popen_calls.append((command, stdout, stderr))
        return error_process

    monkeypatch.setattr(
        iocommands.subprocess,
        'Popen',
        fake_error_popen,
    )
    error_result = iocommands.execute_system_command('echo fail')[0]
    assert error_result.preamble == 'boom'
    assert error_result.status == 'Command exited with return code 7'
    assert error_popen_calls == [
        (
            ['echo', 'fail'],
            iocommands.subprocess.PIPE,
            iocommands.subprocess.PIPE,
        )
    ]
    assert error_process.communicate_timeouts == [60]

    def raise_oserror(command, stdout, stderr):
        raise OSError(0, 'bad command')

    monkeypatch.setattr(iocommands.subprocess, 'Popen', raise_oserror)
    assert iocommands.execute_system_command('echo nope')[0].status == 'OSError: bad command'


def test_unset_once_and_post_redirect_hook(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / 'once.txt'
    iocommands.once_file = target.open('w', encoding='utf-8')
    iocommands.written_to_once_file = True
    hook_calls: list[tuple[str, str]] = []
    original_run_post_redirect_hook = iocommands._run_post_redirect_hook

    def fake_run_post_redirect_hook(command: str, filename: str) -> None:
        hook_calls.append((command, filename))

    monkeypatch.setattr(iocommands, '_run_post_redirect_hook', fake_run_post_redirect_hook)

    iocommands.unset_once_if_written('post {}')

    assert iocommands.once_file is None
    assert hook_calls == [('post {}', str(target))]  # type: ignore[unreachable]
    monkeypatch.setattr(iocommands, '_run_post_redirect_hook', original_run_post_redirect_hook)

    run_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def fake_run(*args, **kwargs) -> SimpleNamespace:
        run_calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(iocommands.subprocess, 'run', fake_run)
    iocommands._run_post_redirect_hook('', str(target))
    assert run_calls == []

    iocommands._run_post_redirect_hook('cat {}', str(target))
    assert run_calls[0][0] == ('cat ' + iocommands.shlex.quote(str(target)),)
    assert run_calls[0][1] == {
        'shell': True,
        'check': True,
        'stdin': iocommands.subprocess.DEVNULL,
        'stdout': iocommands.subprocess.DEVNULL,
        'stderr': iocommands.subprocess.DEVNULL,
    }

    def raise_run(*_args, **_kwargs):
        raise RuntimeError('hook failed')

    monkeypatch.setattr(iocommands.subprocess, 'run', raise_run)
    with pytest.raises(OSError, match='Redirect post hook failed: hook failed'):
        iocommands._run_post_redirect_hook('cat {}', str(target))


def test_set_pipe_once_and_flush_short_circuits(monkeypatch) -> None:
    popen_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(iocommands, 'WIN', True)
    monkeypatch.setattr(iocommands.shlex, 'split', lambda arg: ['cmd', '/c', arg])

    def fake_popen(*args, **kwargs) -> SimpleNamespace:
        popen_calls.append((args, kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(iocommands.subprocess, 'Popen', fake_popen)

    assert iocommands.set_pipe_once('echo test')[0].status == ''
    assert popen_calls == [
        (
            (['cmd', '/c', 'echo test'],),
            {
                'stdin': iocommands.subprocess.PIPE,
                'stdout': iocommands.subprocess.PIPE,
                'stderr': iocommands.subprocess.PIPE,
                'encoding': 'UTF-8',
                'universal_newlines': True,
            },
        )
    ]

    iocommands.PIPE_ONCE['process'] = None
    iocommands.PIPE_ONCE['stdin'] = ['line']
    iocommands.flush_pipe_once_if_written('post {}')

    iocommands.PIPE_ONCE['process'] = SimpleNamespace()
    iocommands.PIPE_ONCE['stdin'] = []
    iocommands.flush_pipe_once_if_written('post {}')


def test_flush_pipe_once_timeout_and_nonzero_exit(monkeypatch, tmp_path: Path) -> None:
    output_file = tmp_path / 'pipe.txt'
    process = FakeProcess(stdout='stdout data', stderr='stderr data', returncode=9, raise_timeout=True)
    hook_calls: list[tuple[str, str]] = []
    secho_calls: list[tuple[str, dict[str, Any]]] = []

    monkeypatch.setattr(iocommands, '_run_post_redirect_hook', lambda command, filename: hook_calls.append((command, filename)))
    monkeypatch.setattr(iocommands.click, 'secho', lambda message, **kwargs: secho_calls.append((message, kwargs)))

    iocommands.PIPE_ONCE['process'] = process
    iocommands.PIPE_ONCE['stdin'] = ['select 1']
    iocommands.PIPE_ONCE['stdout_file'] = str(output_file)
    iocommands.PIPE_ONCE['stdout_mode'] = 'w'

    with pytest.raises(OSError, match='process exited with nonzero code 9'):
        iocommands.flush_pipe_once_if_written('post {}')

    assert process.killed is True
    assert output_file.read_text(encoding='utf-8') == 'stdout data\n'
    assert hook_calls == [('post {}', str(output_file))]
    assert secho_calls == [('stderr data', {'err': True, 'fg': 'red'})]
    assert iocommands.PIPE_ONCE == {
        'process': None,
        'stdin': [],
        'stdout_file': None,
        'stdout_mode': None,
    }


def test_watch_query_usage_and_destructive_cancel(monkeypatch) -> None:
    usage_results = list(iocommands.watch_query('', cur=SequenceCursor([None])))
    assert usage_results[0].status and usage_results[0].status.startswith('Syntax: watch')

    usage_missing_statement = list(iocommands.watch_query('5 -c', cur=SequenceCursor([None])))
    assert usage_missing_statement[0].status and usage_missing_statement[0].status.startswith('Syntax: watch')

    secho_calls: list[str] = []
    monkeypatch.setattr(iocommands, 'confirm_destructive_query', lambda keywords, statement: False)
    monkeypatch.setattr(iocommands.click, 'secho', lambda message, **kwargs: secho_calls.append(message))

    assert list(iocommands.watch_query('drop table t', cur=SequenceCursor([None]))) == []
    assert secho_calls == ['Wise choice!']


def test_watch_query_confirmed_without_description_and_keyboard_interrupt(monkeypatch) -> None:
    cursor = SequenceCursor([None])
    secho_calls: list[str] = []

    monkeypatch.setattr(iocommands, 'confirm_destructive_query', lambda keywords, statement: True)
    monkeypatch.setattr(iocommands.click, 'secho', lambda message, **kwargs: secho_calls.append(message))
    monkeypatch.setattr(iocommands, 'sleep', lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    iocommands.set_pager_enabled(True)
    generator = iocommands.watch_query('0.1 select 1;', cur=cursor)
    result = next(generator)

    assert result.preamble == '> select 1;'
    assert result.header is None
    assert result.command == {'name': 'watch', 'seconds': 0.1}
    assert iocommands.is_pager_enabled() is False

    with pytest.raises(StopIteration):
        next(generator)

    assert secho_calls == ['Your call!', '']
    assert iocommands.is_pager_enabled() is True

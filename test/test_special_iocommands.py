# coding: utf-8
import os
import stat
import tempfile
from time import time
from mock import patch

import pytest
from pymysql import ProgrammingError

import mycli.packages.special

from utils import dbtest, db_connection, send_ctrl_c


def test_set_get_pager():
    mycli.packages.special.set_pager_enabled(True)
    assert mycli.packages.special.is_pager_enabled()
    mycli.packages.special.set_pager_enabled(False)
    assert not mycli.packages.special.is_pager_enabled()
    mycli.packages.special.set_pager('less')
    assert os.environ['PAGER'] == "less"
    mycli.packages.special.set_pager(False)
    assert os.environ['PAGER'] == "less"
    del os.environ['PAGER']
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


def test_editor_command():
    assert mycli.packages.special.editor_command(r'hello\e')
    assert mycli.packages.special.editor_command(r'\ehello')
    assert not mycli.packages.special.editor_command(r'hello')

    assert mycli.packages.special.get_filename(r'\e filename') == "filename"

    os.environ['EDITOR'] = 'true'
    mycli.packages.special.open_external_editor(r'select 1') == "select 1"


def test_tee_command():
    mycli.packages.special.write_tee(u"hello world")  # write without file set
    with tempfile.NamedTemporaryFile() as f:
        mycli.packages.special.execute(None, u"tee " + f.name)
        mycli.packages.special.write_tee(u"hello world")
        assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, u"tee -o " + f.name)
        mycli.packages.special.write_tee(u"hello world")
        f.seek(0)
        assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, u"notee")
        mycli.packages.special.write_tee(u"hello world")
        f.seek(0)
        assert f.read() == b"hello world\n"


def test_tee_command_error():
    with pytest.raises(TypeError):
        mycli.packages.special.execute(None, 'tee')

    with pytest.raises(OSError):
        with tempfile.NamedTemporaryFile() as f:
            os.chmod(f.name, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            mycli.packages.special.execute(None, 'tee {}'.format(f.name))


@dbtest
def test_favorite_query():
    with db_connection().cursor() as cur:
        query = u'select "✔"'
        mycli.packages.special.execute(cur, u'\\fs check {0}'.format(query))
        assert next(mycli.packages.special.execute(
            cur, u'\\f check'))[0] == "> " + query


def test_once_command():
    with pytest.raises(TypeError):
        mycli.packages.special.execute(None, u"\\once")

    mycli.packages.special.execute(None, u"\\once /proc/access-denied")
    with pytest.raises(OSError):
        mycli.packages.special.write_once(u"hello world")

    mycli.packages.special.write_once(u"hello world")  # write without file set
    with tempfile.NamedTemporaryFile() as f:
        mycli.packages.special.execute(None, u"\\once " + f.name)
        mycli.packages.special.write_once(u"hello world")
        assert f.read() == b"hello world\n"

        mycli.packages.special.execute(None, u"\\once -o " + f.name)
        mycli.packages.special.write_once(u"hello world")
        f.seek(0)
        assert f.read() == b"hello world\n"


def test_parseargfile():
    """Test that parseargfile expands the user directory."""
    expected = {'file': os.path.join(os.path.expanduser('~'), 'filename'),
                'mode': 'a'}
    assert expected == mycli.packages.special.iocommands.parseargfile(
        '~/filename')

    expected = {'file': os.path.join(os.path.expanduser('~'), 'filename'),
                'mode': 'w'}
    assert expected == mycli.packages.special.iocommands.parseargfile(
        '-o ~/filename')


def test_parseargfile_no_file():
    """Test that parseargfile raises a TypeError if there is no filename."""
    with pytest.raises(TypeError):
        mycli.packages.special.iocommands.parseargfile('')

    with pytest.raises(TypeError):
        mycli.packages.special.iocommands.parseargfile('-o ')


@dbtest
def test_watch_query_iteration():
    """Test that a single iteration of the result of `watch_query` executes
    the desired query and returns the given results."""
    expected_value = "1"
    query = "SELECT {0!s}".format(expected_value)
    expected_title = '> {0!s}'.format(query)
    with db_connection().cursor() as cur:
        result = next(mycli.packages.special.iocommands.watch_query(
            arg=query, cur=cur
        ))
    assert result[0] == expected_title
    assert result[2][0] == expected_value


@dbtest
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
    query = "SELECT {0!s}".format(expected_value)
    expected_title = '> {0!s}'.format(query)
    expected_results = 4
    ctrl_c_process = send_ctrl_c(wait_interval)
    with db_connection().cursor() as cur:
        results = list(
            result for result in mycli.packages.special.iocommands.watch_query(
                arg='{0!s} {1!s}'.format(watch_seconds, query), cur=cur
            )
        )
    ctrl_c_process.join(1)
    assert len(results) == expected_results
    for result in results:
        assert result[0] == expected_title
        assert result[2][0] == expected_value


@dbtest
@patch('click.clear')
def test_watch_query_clear(clear_mock):
    """Test that the screen is cleared with the -c flag of `watch` command
    before execute the query."""
    with db_connection().cursor() as cur:
        watch_gen = mycli.packages.special.iocommands.watch_query(
            arg='0.1 -c select 1;', cur=cur
        )
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
            next(watch_query('a select 1;', cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query('-a select 1;', cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query('1 -a select 1;', cur=cur))
        with pytest.raises(ProgrammingError):
            next(watch_query('-c -a select 1;', cur=cur))


@dbtest
@patch('click.clear')
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
        test_asserts(watch_query('{0!s} -c select 1;'.format(seconds),
                                 cur=cur))
        test_asserts(watch_query('-c {0!s} select 1;'.format(seconds),
                                 cur=cur))

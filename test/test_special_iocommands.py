# coding: utf-8
import os
import stat
import tempfile

import pytest

import mycli.packages.special
import utils


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


def test_favorite_query():
    with utils.db_connection().cursor() as cur:
        query = u'select "✔"'
        mycli.packages.special.execute(cur, u'\\fs check {0}'.format(query))
        assert next(mycli.packages.special.execute(
            cur, u'\\f check'))[0] == "> " + query


def test_get_set_redirected_output():
    mycli.packages.special.set_redirected_output()
    assert not mycli.packages.special.get_redirected_output()["enabled"]


def test_redirectmatch():
    for sql, result in (
        (r"select 1",           {"sql": r"select 1",
                                 "enabled": False, "filename": None, "append": False}),
        (r"select 1 \> on",     {"sql": r"select 1",
                                 "enabled": True,  "filename": "on", "append": False}),
        (r'select 1 \> "on"',   {"sql": r"select 1",
                                 "enabled": True,  "filename": "on", "append": False}),
        (r"select 1 \>> 'on'",  {"sql": r"select 1",
                                 "enabled": True,  "filename": "on", "append": True}),
        (r"select \"\>\"",      {"sql": r"select \"\>\"",
                                 "enabled": False, "filename": None, "append": False}),
        (r"select '\>'",        {"sql": r"select '\>'",
                                 "enabled": False, "filename": None, "append": False}),
        (r"select",             {"sql": r"select",
                                 "enabled": False, "filename": None, "append": False}),
        (r"select\>",           {"sql": r"select\>",
                                 "enabled": False, "filename": None, "append": False}),
        (r"select\> ",          {"sql": r"select",
                                 "enabled": True,  "filename": "",   "append": False}),
        (r"select\>on",         {"sql": r"select",
                                 "enabled": True,  "filename": "on", "append": False}),
        (r"select 1 \> '\'o'",  {"sql": r"select 1",
                                 "enabled": True,  "filename": "'o", "append": False}),
        (r"select 1 where 2>1", {"sql": r"select 1 where 2>1",
                                 "enabled": False, "filename": None, "append": False}),
        (r"''",                 {
         "sql": "''",             "enabled": False, "filename": None, "append": False}),
    ):
        rsql, r = mycli.packages.special.redirectmatch(sql)
        assert rsql == result["sql"]
        assert r["enabled"] == result["enabled"]
        assert r["filename"] == result["filename"]
        assert r["append"] == result["append"]

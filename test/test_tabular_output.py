# type: ignore

"""Test the sql output adapter."""

import os
from textwrap import dedent

from cli_helpers.utils import strip_ansi
from pymysql.constants import FIELD_TYPE
import pytest

from mycli.main import MyCli
from mycli.packages.sqlresult import SQLResult
from test.utils import HOST, PASSWORD, PORT, USER, dbtest

default_config_file = os.path.join(os.path.dirname(__file__), "myclirc")


@pytest.fixture
def mycli():
    cli = MyCli()
    cli.connect(None, USER, PASSWORD, HOST, PORT, None, init_command=None)
    yield cli
    cli.sqlexecute.conn.close()


@dbtest
def test_sql_output(mycli):
    """Test the sql output adapter."""
    header = ["letters", "number", "optional", "float", "binary"]

    class FakeCursor:
        def __init__(self):
            self.data = [("abc", 1, None, 10.0, b"\xaa"), ("d", 456, "1", 0.5, b"\xaa\xbb")]
            self.description = [
                (None, FIELD_TYPE.VARCHAR),
                (None, FIELD_TYPE.LONG),
                (None, FIELD_TYPE.LONG),
                (None, FIELD_TYPE.FLOAT),
                (None, FIELD_TYPE.BLOB),
            ]

        def __iter__(self):
            return self

        def __next__(self):
            if self.data:
                return self.data.pop(0)
            else:
                raise StopIteration()

        def description(self):
            return self.description

    # Test sql-update output format
    assert list(mycli.change_table_format("sql-update")) == [SQLResult(status="Changed table format to sql-update")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    actual = "\n".join(output)
    assert actual == dedent("""\
            UPDATE `DUAL` SET
              `number` = 1
            , `optional` = NULL
            , `float` = 10.0e0
            , `binary` = 0xaa
            WHERE `letters` = 'abc';
            UPDATE `DUAL` SET
              `number` = 456
            , `optional` = '1'
            , `float` = 0.5e0
            , `binary` = 0xaabb
            WHERE `letters` = 'd';""")
    # Test sql-update-2 output format
    assert list(mycli.change_table_format("sql-update-2")) == [SQLResult(status="Changed table format to sql-update-2")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    assert "\n".join(output) == dedent("""\
            UPDATE `DUAL` SET
              `optional` = NULL
            , `float` = 10.0e0
            , `binary` = 0xaa
            WHERE `letters` = 'abc' AND `number` = 1;
            UPDATE `DUAL` SET
              `optional` = '1'
            , `float` = 0.5e0
            , `binary` = 0xaabb
            WHERE `letters` = 'd' AND `number` = 456;""")
    # Test sql-insert output format (without table name)
    assert list(mycli.change_table_format("sql-insert")) == [SQLResult(status="Changed table format to sql-insert")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    assert "\n".join(output) == dedent("""\
            INSERT INTO `DUAL` (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, 0xaa)
            , ('d', 456, '1', 0.5e0, 0xaabb)
            ;""")
    # Test sql-insert output format (with table name)
    assert list(mycli.change_table_format("sql-insert")) == [SQLResult(status="Changed table format to sql-insert")]
    mycli.main_formatter.query = "SELECT * FROM `table`"
    mycli.redirect_formatter.query = "SELECT * FROM `table`"
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    assert "\n".join(output) == dedent("""\
            INSERT INTO table (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, 0xaa)
            , ('d', 456, '1', 0.5e0, 0xaabb)
            ;""")
    # Test sql-insert output format (with database + table name)
    assert list(mycli.change_table_format("sql-insert")) == [SQLResult(status="Changed table format to sql-insert")]
    mycli.main_formatter.query = "SELECT * FROM `database`.`table`"
    mycli.redirect_formatter.query = "SELECT * FROM `database`.`table`"
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    assert "\n".join(output) == dedent("""\
            INSERT INTO database.table (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, 0xaa)
            , ('d', 456, '1', 0.5e0, 0xaabb)
            ;""")
    # Test binary output format is a hex string
    assert list(mycli.change_table_format("psql")) == [SQLResult(status="Changed table format to psql")]
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor()))
    assert '0xaabb' in '\n'.join(output)


@dbtest
def test_postamble_output(mycli):
    """Test the postamble output property."""
    header = ['letters', 'number', 'optional', 'float']

    class FakeCursor:
        def __init__(self):
            self.data = [('abc', 1, None, 10.0)]
            self.description = [
                (None, FIELD_TYPE.VARCHAR),
                (None, FIELD_TYPE.LONG),
                (None, FIELD_TYPE.LONG),
                (None, FIELD_TYPE.FLOAT),
            ]

        def __iter__(self):
            return self

        def __next__(self):
            if self.data:
                return self.data.pop(0)
            else:
                raise StopIteration()

        def description(self):
            return self.description

    postamble = 'postamble:\nfooter content'
    mycli.change_table_format('ascii')
    mycli.main_formatter.query = ''
    output = mycli.format_sqlresult(SQLResult(header=header, rows=FakeCursor(), postamble=postamble))
    actual = "\n".join(output)
    assert actual.endswith(postamble)


def test_tabulate_output_preserves_multiline_whitespace(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mycli = MyCli(myclirc=default_config_file)
    mycli.helpers_style = None
    mycli.helpers_warnings_style = None

    assert list(mycli.change_table_format("ascii")) == [SQLResult(status="Changed table format to ascii")]

    output = mycli.format_sqlresult(SQLResult(header=["text"], rows=[["  one\n       two\nthree"]]))

    assert strip_ansi("\n".join(output)) == dedent("""\
        +------------+
        | text       |
        +------------+
        |   one      |
        |        two |
        | three      |
        +------------+""")

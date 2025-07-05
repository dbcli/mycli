"""Test the sql output adapter."""

from textwrap import dedent

from pymysql.constants import FIELD_TYPE
import pytest

from mycli.main import MyCli
from test.utils import HOST, PASSWORD, PORT, USER, dbtest


@pytest.fixture
def mycli():
    cli = MyCli()
    cli.connect(None, USER, PASSWORD, HOST, PORT, None, init_command=None)
    return cli


@dbtest
def test_sql_output(mycli):
    """Test the sql output adapter."""
    headers = ["letters", "number", "optional", "float", "binary"]

    class FakeCursor(object):
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
    assert list(mycli.change_table_format("sql-update")) == [(None, None, None, "Changed table format to sql-update")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers, False, False)
    actual = "\n".join(output)
    assert actual == dedent("""\
            UPDATE `DUAL` SET
              `number` = 1
            , `optional` = NULL
            , `float` = 10.0e0
            , `binary` = X'aa'
            WHERE `letters` = 'abc';
            UPDATE `DUAL` SET
              `number` = 456
            , `optional` = '1'
            , `float` = 0.5e0
            , `binary` = X'aabb'
            WHERE `letters` = 'd';""")
    # Test sql-update-2 output format
    assert list(mycli.change_table_format("sql-update-2")) == [(None, None, None, "Changed table format to sql-update-2")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers, False, False)
    assert "\n".join(output) == dedent("""\
            UPDATE `DUAL` SET
              `optional` = NULL
            , `float` = 10.0e0
            , `binary` = X'aa'
            WHERE `letters` = 'abc' AND `number` = 1;
            UPDATE `DUAL` SET
              `optional` = '1'
            , `float` = 0.5e0
            , `binary` = X'aabb'
            WHERE `letters` = 'd' AND `number` = 456;""")
    # Test sql-insert output format (without table name)
    assert list(mycli.change_table_format("sql-insert")) == [(None, None, None, "Changed table format to sql-insert")]
    mycli.main_formatter.query = ""
    mycli.redirect_formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers, False, False)
    assert "\n".join(output) == dedent("""\
            INSERT INTO `DUAL` (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, X'aa')
            , ('d', 456, '1', 0.5e0, X'aabb')
            ;""")
    # Test sql-insert output format (with table name)
    assert list(mycli.change_table_format("sql-insert")) == [(None, None, None, "Changed table format to sql-insert")]
    mycli.main_formatter.query = "SELECT * FROM `table`"
    mycli.redirect_formatter.query = "SELECT * FROM `table`"
    output = mycli.format_output(None, FakeCursor(), headers, False, False)
    assert "\n".join(output) == dedent("""\
            INSERT INTO table (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, X'aa')
            , ('d', 456, '1', 0.5e0, X'aabb')
            ;""")
    # Test sql-insert output format (with database + table name)
    assert list(mycli.change_table_format("sql-insert")) == [(None, None, None, "Changed table format to sql-insert")]
    mycli.main_formatter.query = "SELECT * FROM `database`.`table`"
    mycli.redirect_formatter.query = "SELECT * FROM `database`.`table`"
    output = mycli.format_output(None, FakeCursor(), headers, False, False)
    assert "\n".join(output) == dedent("""\
            INSERT INTO database.table (`letters`, `number`, `optional`, `float`, `binary`) VALUES
              ('abc', 1, NULL, 10.0e0, X'aa')
            , ('d', 456, '1', 0.5e0, X'aabb')
            ;""")

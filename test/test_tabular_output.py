# -*- coding: utf-8 -*-
"""Test the sql output adapter."""

from __future__ import unicode_literals
from textwrap import dedent

from mycli.packages.tabular_output import sql_format
from cli_helpers.tabular_output import TabularOutputFormatter

from utils import USER, PASSWORD, HOST, PORT, dbtest

import pytest
from mycli.main import MyCli

from pymysql.constants import FIELD_TYPE


@pytest.fixture
def mycli():
    cli = MyCli()
    cli.connect(None, USER, PASSWORD, HOST, PORT, None)
    return cli


@dbtest
def test_sql_output(mycli):
    """Test the sql output adapter."""
    headers = ['letters', 'number', 'optional', 'float']

    class FakeCursor(object):
        def __init__(self):
            self.data = [('abc', 1, None, 10.0), ('d', 456, '1', 0.5)]
            self.description = [(None, FIELD_TYPE.VARCHAR), (None, FIELD_TYPE.LONG),
                                (None, FIELD_TYPE.LONG), (None, FIELD_TYPE.FLOAT)]

        def __iter__(self):
            return self

        def __next__(self):
            if self.data:
                return self.data.pop(0)
            else:
                raise StopIteration()

        next = __next__  # Python 2

        def description(self):
            return self.description

    # Test sql-update output format
    assert list(mycli.change_table_format("sql-update")) == \
        [(None, None, None, 'Changed table format to sql-update')]
    mycli.formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers)
    assert "\n".join(output) == dedent('''\
            UPDATE `DUAL` SET
              `number` = 1
            , `optional` = NULL
            , `float` = 10
            WHERE `letters` = 'abc';
            UPDATE `DUAL` SET
              `number` = 456
            , `optional` = '1'
            , `float` = 0.5
            WHERE `letters` = 'd';''')
    # Test sql-update-2 output format
    assert list(mycli.change_table_format("sql-update-2")) == \
        [(None, None, None, 'Changed table format to sql-update-2')]
    mycli.formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers)
    assert "\n".join(output) == dedent('''\
            UPDATE `DUAL` SET
              `optional` = NULL
            , `float` = 10
            WHERE `letters` = 'abc' AND `number` = 1;
            UPDATE `DUAL` SET
              `optional` = '1'
            , `float` = 0.5
            WHERE `letters` = 'd' AND `number` = 456;''')
    # Test sql-insert output format (without table name)
    assert list(mycli.change_table_format("sql-insert")) == \
        [(None, None, None, 'Changed table format to sql-insert')]
    mycli.formatter.query = ""
    output = mycli.format_output(None, FakeCursor(), headers)
    assert "\n".join(output) == dedent('''\
            INSERT INTO `DUAL` (`letters`, `number`, `optional`, `float`) VALUES
              ('abc', 1, NULL, 10)
            , ('d', 456, '1', 0.5)
            ;''')
    # Test sql-insert output format (with table name)
    assert list(mycli.change_table_format("sql-insert")) == \
        [(None, None, None, 'Changed table format to sql-insert')]
    mycli.formatter.query = "SELECT * FROM `table`"
    output = mycli.format_output(None, FakeCursor(), headers)
    assert "\n".join(output) == dedent('''\
            INSERT INTO `table` (`letters`, `number`, `optional`, `float`) VALUES
              ('abc', 1, NULL, 10)
            , ('d', 456, '1', 0.5)
            ;''')
    # Test sql-insert output format (with database + table name)
    assert list(mycli.change_table_format("sql-insert")) == \
        [(None, None, None, 'Changed table format to sql-insert')]
    mycli.formatter.query = "SELECT * FROM `database`.`table`"
    output = mycli.format_output(None, FakeCursor(), headers)
    assert "\n".join(output) == dedent('''\
            INSERT INTO `database`.`table` (`letters`, `number`, `optional`, `float`) VALUES
              ('abc', 1, NULL, 10)
            , ('d', 456, '1', 0.5)
            ;''')

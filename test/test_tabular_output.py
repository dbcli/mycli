# -*- coding: utf-8 -*-
"""Test the sql output adapter."""

from __future__ import unicode_literals
from textwrap import dedent

from mycli.packages.tabular_output import sql_format
from cli_helpers.tabular_output import TabularOutputFormatter

from utils import USER, PASSWORD, HOST, PORT, dbtest

import pytest
import mycli.main


@pytest.fixture
def formatter():
    formatter = TabularOutputFormatter(format_name='psql')
    formatter.query = ""
    formatter.mycli = mycli.main.MyCli()
    formatter.mycli.connect(None, USER, PASSWORD, HOST, PORT, None)
    return formatter


@dbtest
def test_sql_output(formatter):
    """Test the sql output adapter."""
    sql_format.register_new_formatter(formatter)
    headers = ['letters', 'number', 'optional']
    data = [['abc', 1, None], ['d', 456, '1']]
    column_types = [str, int, str]
    # Test sql-update output format
    output = formatter.format_output(
        iter(data), headers, format_name='sql-update',
        column_types=column_types
    )
    assert "\n".join(output) == dedent('''\
            UPDATE `DUAL` SET
              `number` = 1
            , `optional` = NULL
            WHERE `letters` = 'abc';
            UPDATE `DUAL` SET
              `number` = 456
            , `optional` = '1'
            WHERE `letters` = 'd';''')
    # Test sql-update-2 output format
    output = formatter.format_output(
        iter(data), headers, format_name='sql-update-2',
        column_types=column_types
    )
    assert "\n".join(output) == dedent('''\
            UPDATE `DUAL` SET
              `optional` = NULL
            WHERE `letters` = 'abc' AND `number` = 1;
            UPDATE `DUAL` SET
              `optional` = '1'
            WHERE `letters` = 'd' AND `number` = 456;''')
    # Test sql-insert output format (without table name)
    output = formatter.format_output(
        iter(data), headers, format_name='sql-insert',
        column_types=column_types
    )
    assert "\n".join(output) == dedent('''\
            INSERT INTO `DUAL` (`letters`, `number`, `optional`) VALUES
              ('abc', 1, NULL)
            , ('d', 456, '1')
            ;''')
    # Test sql-insert output format (with table name)
    formatter.query = "SELECT * FROM `table`"
    output = formatter.format_output(
        iter(data), headers, format_name='sql-insert',
        column_types=column_types
    )
    assert "\n".join(output) == dedent('''\
            INSERT INTO `table` (`letters`, `number`, `optional`) VALUES
              ('abc', 1, NULL)
            , ('d', 456, '1')
            ;''')
    # Test sql-insert output format (with database + table name)
    formatter.query = "SELECT * FROM `database`.`table`"
    output = formatter.format_output(
        iter(data), headers, format_name='sql-insert',
        column_types=column_types
    )
    assert "\n".join(output) == dedent('''\
            INSERT INTO `database`.`table` (`letters`, `number`, `optional`) VALUES
              ('abc', 1, NULL)
            , ('d', 456, '1')
            ;''')

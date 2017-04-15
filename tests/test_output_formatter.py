# -*- coding: utf-8 -*-
"""Test the generic output formatter interface."""

from __future__ import unicode_literals
from decimal import Decimal
from textwrap import dedent

from mycli.output_formatter.preprocessors import (align_decimals,
                                                  bytes_to_string,
                                                  convert_to_string,
                                                  quote_whitespaces,
                                                  override_missing_value,
                                                  to_string)
from mycli.output_formatter.output_formatter import OutputFormatter
from mycli.output_formatter.delimited_output_adapter import (
    adapter as csv_wrapper)
from mycli.output_formatter.tabulate_adapter import (
    adapter as tabulate_wrapper)
from mycli.output_formatter.terminaltables_adapter import (
    adapter as terminal_tables_wrapper)


def test_to_string():
    """Test the *output_formatter.to_string()* function."""
    assert 'a' == to_string('a')
    assert 'a' == to_string(b'a')
    assert '1' == to_string(1)
    assert '1.23' == to_string(1.23)


def test_convert_to_string():
    """Test the *output_formatter.convert_to_string()* function."""
    data = [[1, 'John'], [2, 'Jill']]
    headers = [0, 'name']
    expected = ([['1', 'John'], ['2', 'Jill']], ['0', 'name'])

    assert expected == convert_to_string(data, headers)


def test_override_missing_values():
    """Test the *output_formatter.override_missing_values()* function."""
    data = [[1, None], [2, 'Jill']]
    headers = [0, 'name']
    expected = ([[1, '<EMPTY>'], [2, 'Jill']], [0, 'name'])

    assert expected == override_missing_value(data, headers,
                                              missing_value='<EMPTY>')


def test_bytes_to_string():
    """Test the *output_formatter.bytes_to_string()* function."""
    data = [[1, 'John'], [2, b'Jill']]
    headers = [0, 'name']
    expected = ([[1, 'John'], [2, 'Jill']], [0, 'name'])

    assert expected == bytes_to_string(data, headers)


def test_align_decimals():
    """Test the *align_decimals()* function."""
    data = [[Decimal('200'), Decimal('1')], [
        Decimal('1.00002'), Decimal('1.0')]]
    headers = ['num1', 'num2']
    expected = ([['200', '1'], ['  1.00002', '1.0']], ['num1', 'num2'])

    assert expected == align_decimals(data, headers)


def test_align_decimals_empty_result():
    """Test *align_decimals()* with no results."""
    data = []
    headers = ['num1', 'num2']
    expected = ([], ['num1', 'num2'])

    assert expected == align_decimals(data, headers)


def test_quote_whitespaces():
    """Test the *quote_whitespaces()* function."""
    data = [["  before", "after  "], ["  both  ", "none"]]
    headers = ['h1', 'h2']
    expected = ([["'  before'", "'after  '"], ["'  both  '", "'none'"]],
                ['h1', 'h2'])

    assert expected == quote_whitespaces(data, headers)


def test_quote_whitespaces_empty_result():
    """Test the *quote_whitespaces()* function with no results."""
    data = []
    headers = ['h1', 'h2']
    expected = ([], ['h1', 'h2'])

    assert expected == quote_whitespaces(data, headers)


def test_tabulate_wrapper():
    """Test the *output_formatter.tabulate_wrapper()* function."""
    data = [['abc', 1], ['d', 456]]
    headers = ['letters', 'number']
    output = tabulate_wrapper(data, headers, table_format='psql')
    assert output == dedent('''\
        +-----------+----------+
        | letters   | number   |
        |-----------+----------|
        | abc       | 1        |
        | d         | 456      |
        +-----------+----------+''')


def test_csv_wrapper():
    """Test the *output_formatter.csv_wrapper()* function."""
    # Test comma-delimited output.
    data = [['abc', 1], ['d', 456]]
    headers = ['letters', 'number']
    output = csv_wrapper(data, headers)
    assert output == dedent('''\
        letters,number\r\n\
        abc,1\r\n\
        d,456\r\n''')

    # Test tab-delimited output.
    data = [['abc', 1], ['d', 456]]
    headers = ['letters', 'number']
    output = csv_wrapper(data, headers, table_format='tsv')
    assert output == dedent('''\
        letters\tnumber\r\n\
        abc\t1\r\n\
        d\t456\r\n''')


def test_terminal_tables_wrapper():
    """Test the *output_formatter.terminal_tables_wrapper()* function."""
    data = [['abc', 1], ['d', 456]]
    headers = ['letters', 'number']
    output = terminal_tables_wrapper(data, headers, table_format='ascii')
    assert output == dedent('''\
        +---------+--------+
        | letters | number |
        +---------+--------+
        | abc     | 1      |
        | d       | 456    |
        +---------+--------+''')


def test_output_formatter():
    """Test the *output_formatter.OutputFormatter* class."""
    data = [['abc', Decimal(1)], ['defg', Decimal('11.1')],
            ['hi', Decimal('1.1')]]
    headers = ['text', 'numeric']
    expected = dedent('''\
        +------+---------+
        | text | numeric |
        +------+---------+
        | abc  |  1      |
        | defg | 11.1    |
        | hi   |  1.1    |
        +------+---------+''')

    assert expected == OutputFormatter().format_output(data, headers,
                                                       format_name='ascii')

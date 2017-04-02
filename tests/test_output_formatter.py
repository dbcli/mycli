# -*- coding: utf-8 -*-
"""Test the generic output formatter interface."""

from __future__ import unicode_literals

from textwrap import dedent

from mycli.output_formatter import (bytes_to_string, convert_to_string,
                                    csv_wrapper, OutputFormatter,
                                    override_missing_value,
                                    terminal_tables_wrapper, to_string)


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
    output = csv_wrapper(data, headers, delimiter='\t')
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

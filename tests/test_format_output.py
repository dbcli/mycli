# -*- coding: UTF-8 -*-
from mycli.main import format_output
from textwrap import dedent

def test_happy_path():
    title = ''
    rows = [['abc', 'def'], ['ghi', 'jkl']]
    headers = ['first', 'second']
    status = 'status message'
    table_format = ''
    output = format_output(title, rows, headers, status, table_format)
    expected = dedent(u'''
    +-------+--------+
    | first | second |
    +-------+--------+
    | abc   | def    |
    | ghi   | jkl    |
    +-------+--------+
    status message''').strip()
    assert '\n'.join(output) == expected

def test_dont_strip_leading_whitespace():
    title = ''
    rows = [['    abc']]
    headers = ['xyz']
    status = ''
    table_format = ''
    output = format_output(title, rows, headers, status, table_format)
    expected = dedent(u'''
        +---------+
        | xyz     |
        +---------+
        |     abc |
        +---------+
        ''').strip()
    assert '\n'.join(output) == expected

def test_handle_unicode_values():
    title = ''
    rows = [['日本語']]
    headers = ['xyz']
    status = ''
    table_format = ''
    output = format_output(title, rows, headers, status, table_format)
    expected = dedent(u'''
        +--------+
        | xyz    |
        +--------+
        | 日本語 |
        +--------+
        ''').strip()
    assert '\n'.join(output) == expected

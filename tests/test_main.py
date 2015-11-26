import pytest
from mycli.main import format_output

def test_format_output():
    results = format_output('Title', [('abc', 'def')], ['head1', 'head2'],
                            'test status', 'psql')
    expected = ['Title', '+---------+---------+\n| head1   | head2   |\n|---------+---------|\n| abc     | def     |\n+---------+---------+', 'test status']
    assert results == expected

def test_format_output_auto_expand():
    table_results = format_output('Title', [('abc', 'def')],
                                  ['head1', 'head2'], 'test status', 'psql',
                                  max_width=100)
    table = ['Title', '+---------+---------+\n| head1   | head2   |\n|---------+---------|\n| abc     | def     |\n+---------+---------+', 'test status']
    assert table_results == table

    expanded_results = format_output('Title', [('abc', 'def')],
                                     ['head1', 'head2'], 'test status', 'psql',
                                     max_width=1)
    expanded = ['Title', u'***************************[ 1. row ]***************************\nhead1 | abc    \nhead2 | def    \n', 'test status']
    assert expanded_results == expanded

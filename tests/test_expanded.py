"""Test the vertical, expanded table formatter."""
from textwrap import dedent

from mycli.output_formatter.expanded import expanded_table
from mycli.encodingutils import text_type


def test_expanded_table_renders():
    results = [('hello', text_type(123)), ('world', text_type(456))]

    expected = dedent("""\
        ***************************[ 1. row ]***************************
        name | hello
        age  | 123
        ***************************[ 2. row ]***************************
        name | world
        age  | 456
        """)
    assert expected == expanded_table(results, ('name', 'age'))

from mycli.packages.expanded import expanded_table
from mycli.encodingutils import text_type

def test_expanded_table_renders():
    input = [("hello", text_type(123)), ("world", text_type(456))]

    expected = """***************************[ 1. row ]***************************
name | hello
age  | 123
***************************[ 2. row ]***************************
name | world
age  | 456
"""
    assert expected == expanded_table(input, ["name", "age"])

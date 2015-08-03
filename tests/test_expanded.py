from mycli.packages.expanded import expanded_table

def test_expanded_table_renders():
    input = [("hello", 123), ("world", 456)]

    expected = """***************************[ 1. row ]***************************
name | hello
age  | 123
***************************[ 2. row ]***************************
name | world
age  | 456
"""
    assert expected == expanded_table(input, ["name", "age"])

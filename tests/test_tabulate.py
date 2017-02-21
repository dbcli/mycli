from mycli.packages.tabulate import tabulate
from textwrap import dedent


def test_dont_strip_leading_whitespace():
    data = [['    abc']]
    headers = ['xyz']
    tbl, _ = tabulate(data, headers, tablefmt='psql')
    assert tbl == dedent('''
        +---------+
        | xyz     |
        |---------|
        |     abc |
        +---------+ ''').strip()
def test_dont_add_whitespace():
    data = [[3, 4]]
    headers = ['1', '2']
    tbl, _ = tabulate(data, headers, tablefmt='tsv')
    assert tbl == dedent('''
        1\t2
        3\t4
        ''').strip()

from textwrap import dedent

from mycli.packages import tabulate

tabulate.PRESERVE_WHITESPACE = True


def test_dont_strip_leading_whitespace():
    data = [['    abc']]
    headers = ['xyz']
    tbl = tabulate.tabulate(data, headers, tablefmt='psql')
    assert tbl == dedent('''
        +---------+
        | xyz     |
        |---------|
        |     abc |
        +---------+ ''').strip()

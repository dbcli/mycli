from pygments.token import Keyword, Name

from mycli.lexer import MyCliLexer


def test_mysql_lexer_keeps_identifiers_starting_with_set_together():
    tokens = list(MyCliLexer().get_tokens("SELECT * FROM settings_123 WHERE id = 123;"))

    assert (Name, "settings_123") in tokens
    assert (Keyword, "set") not in tokens

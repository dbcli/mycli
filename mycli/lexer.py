from pygments.lexer import inherit
from pygments.lexers.sql import MySqlLexer
from pygments.token import Keyword


class MyCliLexer(MySqlLexer):
    """Extends MySQL lexer to add keywords."""

    tokens = {
        'root': [(r'\brepair\b', Keyword),
                 (r'\boffset\b', Keyword), inherit],
    }

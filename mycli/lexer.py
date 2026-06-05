from pygments.lexer import inherit
from pygments.lexers.sql import MySqlLexer
from pygments.token import Keyword, Name


class MyCliLexer(MySqlLexer):
    """Extends MySQL lexer to add keywords."""

    tokens = {
        "root": [
            # TODO: Remove once Pygments is upgraded above v2.20.0.
            (r"\bset[\w$]+\b", Name),
            (r"\brepair\b", Keyword),
            (r"\boffset\b", Keyword),
            inherit,
        ],
    }

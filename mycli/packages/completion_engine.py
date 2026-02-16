import functools
import re
from typing import Any, Literal

import sqlparse
from sqlparse.sql import Comparison, Identifier, Token, Where

from mycli.packages.parseutils import extract_tables, find_prev_keyword, last_word
from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.packages.special.main import parse_special_command

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

_ENUM_VALUE_RE = re.compile(
    r"(?P<lhs>(?:`[^`]+`|[\w$]+)(?:\.(?:`[^`]+`|[\w$]+))?)\s*=\s*$",
    re.IGNORECASE,
)


def _enum_value_suggestion(text_before_cursor: str, full_text: str) -> dict[str, Any] | None:
    match = _ENUM_VALUE_RE.search(text_before_cursor)
    if not match:
        return None
    if is_inside_quotes(text_before_cursor, match.start("lhs")):
        return None

    lhs = match.group("lhs")
    if "." in lhs:
        parent, column = lhs.split(".", 1)
    else:
        parent, column = None, lhs

    return {
        "type": "enum_value",
        "tables": extract_tables(full_text),
        "column": column,
        "parent": parent,
    }


def _is_where_or_having(token: Token | None) -> bool:
    return bool(token and token.value and token.value.lower() in ("where", "having"))


def _find_doubled_backticks(text: str) -> list[int]:
    length = len(text)
    doubled_backticks: list[int] = []
    backtick = '`'

    for index in range(0, length):
        ch = text[index]
        if ch != backtick:
            index += 1
            continue
        if index + 1 < length and text[index + 1] == backtick:
            doubled_backticks.append(index)
            doubled_backticks.append(index + 1)
            index += 2
            continue
        index += 1

    return doubled_backticks


@functools.lru_cache(maxsize=128)
def is_inside_quotes(text: str, pos: int) -> Literal[False, 'single', 'double', 'backtick']:
    in_single = False
    in_double = False
    in_backticks = False
    escaped = False
    doubled_backtick_positions = []
    single_quote = "'"
    double_quote = '"'
    backtick = '`'
    backslash = '\\'

    # scanning the string twice seems to be needed to handle doubled backticks
    if backtick in text:
        doubled_backtick_positions = _find_doubled_backticks(text)

    length = len(text)
    if pos < 0:
        pos = length + pos
        pos = max(pos, 0)
    pos = min(length, pos)

    # optimization
    up_to_pos = text[:pos]
    if backtick not in up_to_pos and single_quote not in up_to_pos and double_quote not in up_to_pos:
        return False

    for index in range(0, pos):
        ch = text[index]
        if index in doubled_backtick_positions:
            index += 1
            continue
        if escaped and (in_double or in_single):
            escaped = False
            index += 1
            continue
        if ch == backslash and (in_double or in_single):
            escaped = True
            index += 1
            continue
        if ch == backtick and not in_double and not in_single:
            in_backticks = not in_backticks
        elif ch == single_quote and not in_double and not in_backticks:
            in_single = not in_single
        elif ch == double_quote and not in_single and not in_backticks:
            in_double = not in_double
        index += 1

    if in_single:
        return 'single'
    elif in_double:
        return 'double'
    elif in_backticks:
        return 'backtick'
    else:
        return False


def suggest_type(full_text: str, text_before_cursor: str) -> list[dict[str, Any]]:
    """Takes the full_text that is typed so far and also the text before the
    cursor to suggest completion type and scope.

    Returns a tuple with a type of entity ('table', 'column' etc) and a scope.
    A scope for a column category will be a list of tables.
    """

    word_before_cursor = last_word(text_before_cursor, include="many_punctuations")

    identifier: Identifier | None = None

    # here should be removed once sqlparse has been fixed
    try:
        # If we've partially typed a word then word_before_cursor won't be an empty
        # string. In that case we want to remove the partially typed string before
        # sending it to the sqlparser. Otherwise the last token will always be the
        # partially typed string which renders the smart completion useless because
        # it will always return the list of keywords as completion.
        if word_before_cursor:
            if word_before_cursor.endswith("(") or word_before_cursor.startswith("\\"):
                parsed = sqlparse.parse(text_before_cursor)
            else:
                parsed = sqlparse.parse(text_before_cursor[: -len(word_before_cursor)])

                # word_before_cursor may include a schema qualification, like
                # "schema_name.partial_name" or "schema_name.", so parse it
                # separately
                p = sqlparse.parse(word_before_cursor)[0]

                if p.tokens and isinstance(p.tokens[0], Identifier):
                    identifier = p.tokens[0]
        else:
            parsed = sqlparse.parse(text_before_cursor)
    except (TypeError, AttributeError):
        return [{"type": "keyword"}]

    if len(parsed) > 1:
        # Multiple statements being edited -- isolate the current one by
        # cumulatively summing statement lengths to find the one that bounds the
        # current position
        current_pos = len(text_before_cursor)
        stmt_start, stmt_end = 0, 0

        for statement in parsed:
            stmt_len = len(str(statement))
            stmt_start, stmt_end = stmt_end, stmt_end + stmt_len

            if stmt_end >= current_pos:
                text_before_cursor = full_text[stmt_start:current_pos]
                full_text = full_text[stmt_start:]
                break

    elif parsed:
        # A single statement
        statement = parsed[0]
    else:
        # The empty string
        statement = None

    # Check for special commands and handle those separately
    if statement:
        # Be careful here because trivial whitespace is parsed as a statement,
        # but the statement won't have a first token
        tok1 = statement.token_first()
        # lenient because \. will parse as two tokens
        if tok1 and tok1.value.startswith('\\'):
            return suggest_special(text_before_cursor)
        elif tok1:
            if tok1.value.lower() in SPECIAL_COMMANDS:
                return suggest_special(text_before_cursor)

    last_token = statement and statement.token_prev(len(statement.tokens))[1] or ""

    # todo: unsure about empty string as identifier
    return suggest_based_on_last_token(last_token, text_before_cursor, word_before_cursor, full_text, identifier or Identifier(''))


def suggest_special(text: str) -> list[dict[str, Any]]:
    text = text.lstrip()
    cmd, _separator, _arg = parse_special_command(text)

    if cmd == text:
        # Trying to complete the special command itself
        return [{"type": "special"}]

    if cmd in ("\\u", "\\r"):
        return [{"type": "database"}]

    if cmd.lower() in ('use', 'connect'):
        return [{'type': 'database'}]

    if cmd in (r'\T', r'\Tr'):
        return [{"type": "table_format"}]

    if cmd.lower() in ('tableformat', 'redirectformat'):
        return [{"type": "table_format"}]

    if cmd in ["\\f", "\\fs", "\\fd"]:
        return [{"type": "favoritequery"}]

    if cmd in ["\\dt", "\\dt+"]:
        return [
            {"type": "table", "schema": []},
            {"type": "view", "schema": []},
            {"type": "schema"},
        ]
    elif cmd.lower() in ["\\.", "source"]:
        return [{"type": "file_name"}]
    if cmd in ["\\llm", "\\ai"]:
        return [{"type": "llm"}]

    return [{"type": "keyword"}, {"type": "special"}]


def suggest_based_on_last_token(
    token: str | Token | None,
    text_before_cursor: str,
    word_before_cursor: str | None,
    full_text: str,
    identifier: Identifier,
) -> list[dict[str, Any]]:

    # don't suggest anything inside a string or number
    if word_before_cursor:
        if re.match(r'^[\d\.]', word_before_cursor[0]):
            return []
        # more efficient if no space was typed yet in the string
        if word_before_cursor[0] in ('"', "'"):
            return []
        # less efficient, but handles all cases
        # in fact, this is quite slow, but not as slow as offering completions!
        # faster would be to peek inside the Pygments lexer run by prompt_toolkit -- how?
        if is_inside_quotes(text_before_cursor, -1) in ['single', 'double']:
            return []

    if isinstance(token, str):
        token_v = token.lower()
    elif isinstance(token, Comparison):
        # If 'token' is a Comparison type such as
        # 'select * FROM abc a JOIN def d ON a.id = d.'. Then calling
        # token.value on the comparison type will only return the lhs of the
        # comparison. In this case a.id. So we need to do token.tokens to get
        # both sides of the comparison and pick the last token out of that
        # list.
        token_v = token.tokens[-1].value.lower()
    elif isinstance(token, Where):
        # sqlparse groups all tokens from the where clause into a single token
        # list. This means that token.value may be something like
        # 'where foo > 5 and '. We need to look "inside" token.tokens to handle
        # suggestions in complicated where clauses correctly
        original_text = text_before_cursor
        prev_keyword, text_before_cursor = find_prev_keyword(text_before_cursor)
        enum_suggestion = _enum_value_suggestion(original_text, full_text)
        fallback = suggest_based_on_last_token(prev_keyword, text_before_cursor, None, full_text, identifier)
        if enum_suggestion and _is_where_or_having(prev_keyword):
            return [enum_suggestion] + fallback
        return fallback
    elif token is None:
        return [{"type": "keyword"}]
    else:
        token_v = token.value.lower()

    is_operand = lambda x: x and any(x.endswith(op) for op in ["+", "-", "*", "/"])  # noqa: E731

    if not token:
        return [{"type": "keyword"}, {"type": "special"}]
    elif token_v == "*":
        return [{"type": "keyword"}]
    elif token_v.endswith("("):
        p = sqlparse.parse(text_before_cursor)[0]

        if p.tokens and isinstance(p.tokens[-1], Where):
            # Four possibilities:
            #  1 - Parenthesized clause like "WHERE foo AND ("
            #        Suggest columns/functions
            #  2 - Function call like "WHERE foo("
            #        Suggest columns/functions
            #  3 - Subquery expression like "WHERE EXISTS ("
            #        Suggest keywords, in order to do a subquery
            #  4 - Subquery OR array comparison like "WHERE foo = ANY("
            #        Suggest columns/functions AND keywords. (If we wanted to be
            #        really fancy, we could suggest only array-typed columns)

            column_suggestions = suggest_based_on_last_token("where", text_before_cursor, None, full_text, identifier)

            # Check for a subquery expression (cases 3 & 4)
            where = p.tokens[-1]
            _idx, prev_tok = where.token_prev(len(where.tokens) - 1)

            if isinstance(prev_tok, Comparison):
                # e.g. "SELECT foo FROM bar WHERE foo = ANY("
                prev_tok = prev_tok.tokens[-1]

            prev_tok = prev_tok.value.lower()
            if prev_tok == "exists":
                return [{"type": "keyword"}]
            else:
                return column_suggestions

        # Get the token before the parens
        idx, prev_tok = p.token_prev(len(p.tokens) - 1)
        if prev_tok and prev_tok.value and prev_tok.value.lower() == "using":
            # tbl1 INNER JOIN tbl2 USING (col1, col2)
            tables = extract_tables(full_text)

            # suggest columns that are present in more than one table
            return [{"type": "column", "tables": tables, "drop_unique": True}]
        elif p.token_first().value.lower() == "select":
            # If the lparen is preceeded by a space chances are we're about to
            # do a sub-select.
            if last_word(text_before_cursor, "all_punctuations").startswith("("):
                return [{"type": "keyword"}]
        elif p.token_first().value.lower() == "show":
            return [{"type": "show"}]

        # We're probably in a function argument list
        return [{"type": "column", "tables": extract_tables(full_text)}]
    elif token_v in ("call"):
        return [{"type": "procedure", "schema": []}]
    elif token_v in ("set", "order by", "distinct"):
        return [{"type": "column", "tables": extract_tables(full_text)}]
    elif token_v == "as":
        # Don't suggest anything for an alias
        return []
    elif token_v in ("show"):
        return [{"type": "show"}]
    elif token_v in ("to",):
        p = sqlparse.parse(text_before_cursor)[0]
        if p.token_first().value.lower() == "change":
            return [{"type": "change"}]
        else:
            return [{"type": "user"}]
    elif token_v in ("user", "for"):
        return [{"type": "user"}]
    elif token_v in ("select", "where", "having"):
        # Check for a table alias or schema qualification
        parent = (identifier and identifier.get_parent_name()) or []

        tables = extract_tables(full_text)
        if parent:
            tables = [t for t in tables if identifies(parent, *t)]
            return [
                {"type": "column", "tables": tables},
                {"type": "table", "schema": parent},
                {"type": "view", "schema": parent},
                {"type": "function", "schema": parent},
            ]
        else:
            aliases = [alias or table for (schema, table, alias) in tables]
            return [
                {"type": "column", "tables": tables},
                {"type": "function", "schema": []},
                {"type": "alias", "aliases": aliases},
                {"type": "keyword"},
            ]
    elif (
        (token_v.endswith("join") and isinstance(token, Token) and token.is_keyword)
        or (token_v in ("copy", "from", "update", "into", "describe", "truncate", "desc", "explain"))
        # todo: the create table regex fails to match on multi-statement queries, which
        # suggests a bug above in suggest_type()
        or (token_v == "like" and re.match(r'^\s*create\s+table\s', full_text, re.IGNORECASE))
    ):
        schema = (identifier and identifier.get_parent_name()) or []

        # Suggest tables from either the currently-selected schema or the
        # public schema if no schema has been specified
        suggest = [{"type": "table", "schema": schema}]

        if not schema:
            # Suggest schemas
            suggest.append({"type": "database"})

        # Only tables can be TRUNCATED, otherwise suggest views
        if token_v != "truncate":
            suggest.append({"type": "view", "schema": schema})

        return suggest

    elif token_v in ("table", "view", "function"):
        # E.g. 'DROP FUNCTION <funcname>', 'ALTER TABLE <tablname>'
        rel_type = token_v
        schema = (identifier and identifier.get_parent_name()) or []
        if schema:
            return [{"type": rel_type, "schema": schema}]
        else:
            return [{"type": "schema"}, {"type": rel_type, "schema": []}]
    elif token_v == "on":
        tables = extract_tables(full_text)  # [(schema, table, alias), ...]
        parent = (identifier and identifier.get_parent_name()) or []
        if parent:
            # "ON parent.<suggestion>"
            # parent can be either a schema name or table alias
            tables = [t for t in tables if identifies(parent, *t)]
            return [
                {"type": "column", "tables": tables},
                {"type": "table", "schema": parent},
                {"type": "view", "schema": parent},
                {"type": "function", "schema": parent},
            ]
        else:
            # ON <suggestion>
            # Use table alias if there is one, otherwise the table name
            aliases = [alias or table for (schema, table, alias) in tables]
            suggest = [{"type": "alias", "aliases": aliases}]

            # The lists of 'aliases' could be empty if we're trying to complete
            # a GRANT query. eg: GRANT SELECT, INSERT ON <tab>
            # In that case we just suggest all schemata and all tables.
            if not aliases:
                suggest.append({"type": "database"})
                suggest.append({"type": "table", "schema": parent})
            return suggest

    elif token_v in ("database", "template"):
        # "\c <db", "use <db>", "DROP DATABASE <db>",
        # "CREATE DATABASE <newdb> WITH TEMPLATE <db>"
        return [{"type": "database"}]

    elif is_inside_quotes(text_before_cursor, -1) in ['single', 'double']:
        return []

    elif token_v.endswith(",") or is_operand(token_v) or token_v in ["=", "and", "or"]:
        original_text = text_before_cursor
        prev_keyword, text_before_cursor = find_prev_keyword(text_before_cursor)
        enum_suggestion = _enum_value_suggestion(original_text, full_text)
        fallback = suggest_based_on_last_token(prev_keyword, text_before_cursor, None, full_text, identifier) if prev_keyword else []
        if enum_suggestion and _is_where_or_having(prev_keyword):
            return [enum_suggestion] + fallback
        return fallback

    else:
        return [{"type": "keyword"}]


def identifies(
    identifier: Any,
    schema: str | None,
    table: str,
    alias: str,
) -> bool:
    if identifier == alias:
        return True
    if identifier == table:
        return True
    if schema and identifier == (schema + "." + table):
        return True
    return False

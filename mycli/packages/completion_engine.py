from dataclasses import dataclass
import functools
import re
from typing import Any, Callable, Literal

import sqlparse
from sqlparse.sql import Comparison, Identifier, Token, Where

from mycli.packages.special.main import COMMANDS as SPECIAL_COMMANDS
from mycli.packages.special.main import parse_special_command
from mycli.packages.sql_utils import extract_tables, find_prev_keyword, last_word

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

_ENUM_VALUE_RE = re.compile(
    r"(?P<lhs>(?:`[^`]+`|[\w$]+)(?:\.(?:`[^`]+`|[\w$]+))?)\s*=\s*$",
    re.IGNORECASE,
)

# missing because not binary
#   BETWEEN
#   CASE
# missing because parens are used
#   IN(), and others
# unary operands might need to have another set
#   not, !, ~
# arrow operators only take a literal on the right
#   and so might need different treatment
# := might also need a different context
# sqlparse would call these identifiers, so they are excluded
#   xor
# these are hitting the recursion guard, and so not completing after
# so we might as well leave them out:
#   is, 'is not', mod
# sqlparse might also parse "not null" together
# should also verify how sqlparse parses every space-containing case
BINARY_OPERANDS = {
    '&', '>', '>>', '>=', '<', '<>', '!=', '<<', '<=', '<=>', '%',
    '*', '+', '-', '->', '->>', '/', ':=', '=', '^', 'and', '&&', 'div',
    'like', 'not like', 'not regexp', 'or', '||', 'regexp', 'rlike',
    'sounds like', '|',
}  # fmt: skip

Suggestion = dict[str, Any]
Predicate = Callable[['SuggestContext'], bool]
Emitter = Callable[['SuggestContext'], list[Suggestion]]


@dataclass(frozen=True)
class SuggestContext:
    token: str | Token | None
    token_value: str | None
    text_before_cursor: str
    word_before_cursor: str | None
    full_text: str
    identifier: Identifier
    parsed_cb: Callable[[], sqlparse.sql.Statement]
    tokens_wo_space_cb: Callable[[], list[Token]]


@dataclass(frozen=True)
class SuggestRule:
    name: str
    predicate: Predicate
    emit: Emitter


def _keyword_suggestions() -> list[Suggestion]:
    return [{'type': 'keyword'}]


def _keyword_and_special_suggestions() -> list[Suggestion]:
    return [{'type': 'keyword'}, {'type': 'special'}]


@functools.lru_cache(maxsize=128)
def _parse_suggestion_statement(text_before_cursor: str) -> sqlparse.sql.Statement:
    try:
        return sqlparse.parse(text_before_cursor)[0]
    except (AttributeError, IndexError, ValueError, sqlparse.exceptions.SQLParseError):
        return sqlparse.sql.Statement()


@functools.lru_cache(maxsize=128)
def _tokens_wo_space(text_before_cursor: str) -> list[Token]:
    parsed = _parse_suggestion_statement(text_before_cursor)
    return [x for x in parsed.tokens if x.ttype != sqlparse.tokens.Token.Text.Whitespace]


def _normalize_token_value(token: str | Token | None) -> str | None:
    if isinstance(token, str):
        return token.lower()
    if isinstance(token, Comparison):
        # If 'token' is a Comparison type such as
        # 'select * FROM abc a JOIN def d ON a.id = d.'. Then calling
        # token.value on the comparison type will only return the lhs of the
        # comparison. In this case a.id. So we need to do token.tokens to get
        # both sides of the comparison and pick the last token out of that
        # list.
        return token.tokens[-1].value.lower()
    if token is None:
        return None
    return token.value.lower()


def _build_suggest_context(
    token: str | Token | None,
    text_before_cursor: str,
    word_before_cursor: str | None,
    full_text: str,
    identifier: Identifier,
) -> SuggestContext:
    return SuggestContext(
        token=token,
        token_value=_normalize_token_value(token),
        text_before_cursor=text_before_cursor,
        word_before_cursor=word_before_cursor,
        full_text=full_text,
        identifier=identifier,
        parsed_cb=functools.partial(_parse_suggestion_statement, text_before_cursor),
        tokens_wo_space_cb=functools.partial(_tokens_wo_space, text_before_cursor),
    )


def _is_single_or_double_quoted(ctx: SuggestContext) -> bool:
    return is_inside_quotes(ctx.text_before_cursor, -1) in ['single', 'double']


def _parent_name(ctx: SuggestContext) -> str | list[Any]:
    return (ctx.identifier and ctx.identifier.get_parent_name()) or []


def _tables(ctx: SuggestContext) -> list[tuple[str | None, str, str]]:
    return extract_tables(ctx.full_text)


def _aliases(tables: list[tuple[str | None, str, str]]) -> list[str]:
    return [alias or table for (schema, table, alias) in tables]


def _emit_none_token(_ctx: SuggestContext) -> list[Suggestion]:
    return _keyword_suggestions()


def _emit_blank_token(_ctx: SuggestContext) -> list[Suggestion]:
    return _keyword_and_special_suggestions()


def _emit_star(_ctx: SuggestContext) -> list[Suggestion]:
    return _keyword_suggestions()


def _emit_lparen(ctx: SuggestContext) -> list[Suggestion]:
    if ctx.parsed_cb().tokens and isinstance(ctx.parsed_cb().tokens[-1], Where):
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

        # override a few properties in the SuggestContext
        column_suggestions = _emit_select_like(
            SuggestContext(
                token='where',
                token_value='where',
                text_before_cursor=ctx.text_before_cursor,
                word_before_cursor=None,
                full_text=ctx.full_text,
                identifier=ctx.identifier,
                parsed_cb=ctx.parsed_cb,
                tokens_wo_space_cb=ctx.tokens_wo_space_cb,
            )
        )

        # Check for a subquery expression (cases 3 & 4)
        where = ctx.parsed_cb().tokens[-1]
        _idx, prev_tok = where.token_prev(len(where.tokens) - 1)

        if isinstance(prev_tok, Comparison):
            # e.g. "SELECT foo FROM bar WHERE foo = ANY("
            prev_tok = prev_tok.tokens[-1]

        prev_tok = prev_tok.value.lower()
        if prev_tok == 'exists':
            return _keyword_suggestions()
        return column_suggestions

    # Get the token before the parens
    _idx, prev_tok = ctx.parsed_cb().token_prev(len(ctx.parsed_cb().tokens) - 1)
    if prev_tok and prev_tok.value and prev_tok.value.lower() == 'using':
        # tbl1 INNER JOIN tbl2 USING (col1, col2)
        # suggest columns that are present in more than one table
        return [{'type': 'column', 'tables': _tables(ctx), 'drop_unique': True}]
    if ctx.parsed_cb().tokens and ctx.parsed_cb().token_first() and ctx.parsed_cb().token_first().value.lower() == 'select':
        # If the lparen is preceeded by a space chances are we're about to
        # do a sub-select.
        if last_word(ctx.text_before_cursor, 'all_punctuations').startswith('('):
            return _keyword_suggestions()
    elif ctx.parsed_cb().tokens and ctx.parsed_cb().token_first() and ctx.parsed_cb().token_first().value.lower() == 'show':
        return [{'type': 'show'}]

    # We're probably in a function argument list
    return [{'type': 'column', 'tables': _tables(ctx)}]


def _emit_procedure(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'procedure', 'schema': []}]


def _emit_character_set(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'character_set'}]


def _emit_column_for_tables(ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'column', 'tables': _tables(ctx)}]


def _emit_nothing(_ctx: SuggestContext) -> list[Suggestion]:
    return []


def _emit_show(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'show'}]


def _emit_to(ctx: SuggestContext) -> list[Suggestion]:
    if ctx.parsed_cb().tokens and ctx.parsed_cb().token_first() and ctx.parsed_cb().token_first().value.lower() == 'change':
        return [{'type': 'change'}]
    return [{'type': 'user'}]


def _emit_user(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'user'}]


def _emit_collation(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'collation'}]


def _emit_select_like(ctx: SuggestContext) -> list[Suggestion]:
    parent = _parent_name(ctx)
    tables = _tables(ctx)
    if parent:
        tables = [t for t in tables if identifies(parent, *t)]
        return [
            {'type': 'column', 'tables': tables},
            {'type': 'table', 'schema': parent},
            {'type': 'view', 'schema': parent},
            {'type': 'function', 'schema': parent},
        ]
    if is_inside_quotes(ctx.text_before_cursor, -1) == 'backtick':
        # todo: this should be revised, since we complete too exuberantly within
        # backticks, including keywords
        aliases = _aliases(tables)
        return [
            {'type': 'column', 'tables': tables},
            {'type': 'function', 'schema': []},
            {'type': 'alias', 'aliases': aliases},
            {'type': 'keyword'},
        ]

    aliases = _aliases(tables)
    return [
        {'type': 'column', 'tables': tables},
        {'type': 'function', 'schema': []},
        {'type': 'introducer'},
        {'type': 'alias', 'aliases': aliases},
    ]


def _emit_relation_like(ctx: SuggestContext) -> list[Suggestion]:
    schema = _parent_name(ctx)
    is_join = bool(ctx.token_value and ctx.token_value.endswith('join') and isinstance(ctx.token, Token) and ctx.token.is_keyword)

    # Suggest tables from either the currently-selected schema or the
    # public schema if no schema has been specified
    table_suggestion: Suggestion = {'type': 'table', 'schema': schema}
    if is_join:
        table_suggestion['join'] = True
    suggest: list[Suggestion] = [table_suggestion]

    if not schema:
        # Suggest schemas
        suggest.append({'type': 'database'})

    # Only tables can be TRUNCATED, otherwise suggest views
    if ctx.token_value != 'truncate':
        suggest.append({'type': 'view', 'schema': schema})

    return suggest


def _emit_relation_name(ctx: SuggestContext) -> list[Suggestion]:
    rel_type = ctx.token_value
    assert rel_type is not None
    schema = _parent_name(ctx)
    if schema:
        return [{'type': rel_type, 'schema': schema}]
    return [{'type': 'database'}, {'type': rel_type, 'schema': []}]


def _emit_on(ctx: SuggestContext) -> list[Suggestion]:
    tables = _tables(ctx)  # [(schema, table, alias), ...]
    parent = _parent_name(ctx)
    if parent:
        # "ON parent.<suggestion>"
        # parent can be either a schema name or table alias
        # todo recognize and separate schema and table suggestions
        # todo remove function suggestions here
        tables = [t for t in tables if identifies(parent, *t)]
        return [
            {'type': 'column', 'tables': tables},
            {'type': 'table', 'schema': parent},
            {'type': 'view', 'schema': parent},
            {'type': 'function', 'schema': parent},
        ]

    # ON <suggestion>
    # Use table alias if there is one, otherwise the table name
    aliases = _aliases(tables)
    suggest: list[Suggestion] = [{'type': 'fk_join', 'tables': tables}, {'type': 'alias', 'aliases': aliases}]

    # The lists of 'aliases' could be empty if we're trying to complete
    # a GRANT query. eg: GRANT SELECT, INSERT ON <tab>
    # In that case we just suggest all schemata and all tables.
    if not aliases:
        suggest.append({'type': 'database'})
        suggest.append({'type': 'table', 'schema': parent})
    return suggest


def _emit_database(_ctx: SuggestContext) -> list[Suggestion]:
    return [{'type': 'database'}]


def _emit_where_token(ctx: SuggestContext) -> list[Suggestion]:
    assert isinstance(ctx.token, Where)
    # sqlparse groups all tokens from the where clause into a single token
    # list. This means that token.value may be something like
    # 'where foo > 5 and '. We need to look "inside" token.tokens to handle
    # suggestions in complicated where clauses correctly.
    #
    # This logic also needs to look even deeper in to the WHERE clause.
    # We recapitulate some transcoding suggestions here, but cannot
    # recapitulate the entire logic of this function.
    where_tokens = [x for x in ctx.token.tokens if x.ttype != sqlparse.tokens.Token.Text.Whitespace]
    if transcoding_suggestion := _charset_suggestion(where_tokens):
        return transcoding_suggestion

    original_text = ctx.text_before_cursor
    prev_keyword, rewound_text = find_prev_keyword(ctx.text_before_cursor)
    enum_suggestion = _enum_value_suggestion(original_text, ctx.full_text)
    fallback = suggest_based_on_last_token(prev_keyword, rewound_text, None, ctx.full_text, ctx.identifier)
    if enum_suggestion and _is_where_or_having(prev_keyword):
        return [enum_suggestion] + fallback
    return fallback


def _emit_binary_or_comma(ctx: SuggestContext) -> list[Suggestion]:
    original_text = ctx.text_before_cursor
    prev_keyword, rewound_text = find_prev_keyword(ctx.text_before_cursor)
    enum_suggestion = _enum_value_suggestion(original_text, ctx.full_text)

    # guard against non-progressing parser rewinds, which can otherwise
    # recurse forever on some operator shapes.
    if prev_keyword and rewound_text.rstrip() != original_text.rstrip():
        fallback = suggest_based_on_last_token(prev_keyword, rewound_text, None, ctx.full_text, ctx.identifier)
    else:
        # perhaps this fallback should include columns
        fallback = _keyword_suggestions()

    if enum_suggestion and _is_where_or_having(prev_keyword):
        return [enum_suggestion] + fallback
    return fallback


def _word_starts_with_digit_or_dot(ctx: SuggestContext) -> bool:
    return bool(ctx.word_before_cursor and re.match(r'^[\d\.]', ctx.word_before_cursor[0]))


def _word_starts_with_quote(ctx: SuggestContext) -> bool:
    return bool(ctx.word_before_cursor and ctx.word_before_cursor[0] in ('"', "'"))


def _word_inside_single_or_double_quotes(ctx: SuggestContext) -> bool:
    return bool(ctx.word_before_cursor and _is_single_or_double_quoted(ctx))


def _token_is_none(ctx: SuggestContext) -> bool:
    return ctx.token is None


def _token_is_blank(ctx: SuggestContext) -> bool:
    return not ctx.token


def _token_value_is(ctx: SuggestContext, *values: str) -> bool:
    return bool(ctx.token_value and ctx.token_value in values)


def _token_is_lparen(ctx: SuggestContext) -> bool:
    return bool(ctx.token_value and ctx.token_value.endswith('('))


def _token_is_relation_keyword(ctx: SuggestContext) -> bool:
    return bool(
        (ctx.token_value and ctx.token_value.endswith('join') and isinstance(ctx.token, Token) and ctx.token.is_keyword)
        or (ctx.token_value in ('copy', 'from', 'update', 'into', 'describe', 'truncate', 'desc', 'explain'))
        or (ctx.token_value == 'like' and re.match(r'^\s*create\s+table\s', ctx.full_text, re.IGNORECASE))
    )


def _token_is_binary_or_comma(ctx: SuggestContext) -> bool:
    return bool(ctx.token_value and (ctx.token_value.endswith(',') or ctx.token_value in BINARY_OPERANDS))


SUGGEST_BASED_ON_LAST_TOKEN_RULES = [
    SuggestRule(
        'guard_number_or_dot',
        _word_starts_with_digit_or_dot,
        _emit_nothing,
    ),
    SuggestRule(
        'guard_quote_prefix',
        _word_starts_with_quote,
        _emit_nothing,
    ),
    SuggestRule(
        'guard_inside_single_or_double',
        _word_inside_single_or_double_quotes,
        _emit_nothing,
    ),
    SuggestRule(
        'where_token',
        lambda ctx: isinstance(ctx.token, Where),
        _emit_where_token,
    ),
    SuggestRule(
        'none_token',
        _token_is_none,
        _emit_none_token,
    ),
    SuggestRule(
        'blank_token',
        _token_is_blank,
        _emit_blank_token,
    ),
    SuggestRule(
        'star_token',
        lambda ctx: _token_value_is(ctx, '*'),
        _emit_star,
    ),
    SuggestRule(
        'lparen_token',
        _token_is_lparen,
        _emit_lparen,
    ),
    SuggestRule(
        'call',
        lambda ctx: _token_value_is(ctx, 'call'),
        _emit_procedure,
    ),
    SuggestRule(
        'character_set_after_character',
        lambda ctx: (
            _token_value_is(ctx, 'set') and len(ctx.tokens_wo_space_cb()) >= 3 and ctx.tokens_wo_space_cb()[-3].value.lower() == 'character'
        ),
        _emit_character_set,
    ),
    SuggestRule(
        'character_set_after_character_short',
        lambda ctx: (
            _token_value_is(ctx, 'set') and len(ctx.tokens_wo_space_cb()) >= 2 and ctx.tokens_wo_space_cb()[-2].value.lower() == 'character'
        ),
        _emit_character_set,
    ),
    SuggestRule(
        'set_order_by_distinct',
        lambda ctx: _token_value_is(ctx, 'set', 'order by', 'distinct'),
        _emit_column_for_tables,
    ),
    SuggestRule(
        'as',
        lambda ctx: _token_value_is(ctx, 'as'),
        _emit_nothing,
    ),
    SuggestRule(
        'show',
        lambda ctx: _token_value_is(ctx, 'show'),
        _emit_show,
    ),
    SuggestRule(
        'to',
        lambda ctx: _token_value_is(ctx, 'to'),
        _emit_to,
    ),
    SuggestRule(
        'user_or_for',
        lambda ctx: _token_value_is(ctx, 'user', 'for'),
        _emit_user,
    ),
    SuggestRule(
        'collate',
        lambda ctx: _token_value_is(ctx, 'collate'),
        _emit_collation,
    ),
    SuggestRule(
        'using_after_convert_long',
        lambda ctx: (
            _token_value_is(ctx, 'using') and len(ctx.tokens_wo_space_cb()) >= 5 and ctx.tokens_wo_space_cb()[-5].value.lower() == 'convert'
        ),
        _emit_character_set,
    ),
    SuggestRule(
        'using_after_convert_short',
        lambda ctx: (
            _token_value_is(ctx, 'using') and len(ctx.tokens_wo_space_cb()) >= 4 and ctx.tokens_wo_space_cb()[-4].value.lower() == 'convert'
        ),
        _emit_character_set,
    ),
    SuggestRule(
        'select_where_having',
        lambda ctx: _token_value_is(ctx, 'select', 'where', 'having'),
        _emit_select_like,
    ),
    SuggestRule(
        'relation_keyword',
        _token_is_relation_keyword,
        _emit_relation_like,
    ),
    SuggestRule(
        'relation_name',
        lambda ctx: _token_value_is(ctx, 'table', 'view', 'function'),
        _emit_relation_name,
    ),
    SuggestRule(
        'on',
        lambda ctx: _token_value_is(ctx, 'on'),
        _emit_on,
    ),
    SuggestRule(
        'database_template',
        lambda ctx: _token_value_is(ctx, 'database', 'template'),
        _emit_database,
    ),
    SuggestRule(
        'inside_single_or_double',
        _is_single_or_double_quoted,
        _emit_nothing,
    ),
    SuggestRule(
        'binary_or_comma',
        _token_is_binary_or_comma,
        _emit_binary_or_comma,
    ),
]


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


def _charset_suggestion(tokens: list[Token]) -> list[dict[str, str]] | None:
    token_values = [token.value.lower() for token in tokens if token.value]

    if len(token_values) >= 2 and token_values[-1] == 'set' and token_values[-2] == 'character':
        return [{'type': 'character_set'}]
    if len(token_values) >= 3 and token_values[-2] == 'set' and token_values[-3] == 'character':
        return [{'type': 'character_set'}]
    if len(token_values) >= 5 and token_values[-1] == 'using' and token_values[-4] == 'convert':
        return [{'type': 'character_set'}]
    if len(token_values) >= 6 and token_values[-2] == 'using' and token_values[-5] == 'convert':
        return [{'type': 'character_set'}]
    if len(token_values) >= 1 and token_values[-1] == 'collate':
        return [{'type': 'collation'}]

    return None


def _is_where_or_having(token: Token | None) -> bool:
    return bool(token and token.value and token.value.lower() in ("where", "having"))


def _find_doubled_backticks(text: str) -> list[int]:
    length = len(text)
    doubled_backtick_positions: list[int] = []
    backtick = '`'
    two_backticks = backtick + backtick

    if two_backticks not in text:
        return doubled_backtick_positions

    for index in range(0, length):
        ch = text[index]
        if ch != backtick:
            index += 1
            continue
        if index + 1 < length and text[index + 1] == backtick:
            doubled_backtick_positions.append(index)
            doubled_backtick_positions.append(index + 1)
            index += 2
            continue
        index += 1

    return doubled_backtick_positions


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
    elif cmd.lower() in [
        r'\.',
        'source',
        r'\o',
        r'\once',
        r'tee',
    ]:
        return [{"type": "file_name"}]
    # todo: why is \edit case-sensitive?
    elif cmd in [
        r'\e',
        r'\edit',
    ]:
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
    ctx = _build_suggest_context(token, text_before_cursor, word_before_cursor, full_text, identifier)
    for rule in SUGGEST_BASED_ON_LAST_TOKEN_RULES:
        if rule.predicate(ctx):
            return rule.emit(ctx)

    return _keyword_suggestions()


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

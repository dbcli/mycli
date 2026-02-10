from __future__ import annotations

import re
from typing import Any, Generator

import sqlglot
import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList, Token, TokenList
from sqlparse.tokens import DML, Keyword, Punctuation

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

cleanup_regex: dict[str, re.Pattern] = {
    # This matches only alphanumerics and underscores.
    "alphanum_underscore": re.compile(r"(\w+)$"),
    # This matches everything except spaces, parens, colon, and comma
    "many_punctuations": re.compile(r"([^():,\s]+)$"),
    # This matches everything except spaces, parens, colon, comma, and period
    "most_punctuations": re.compile(r"([^\.():,\s]+)$"),
    # This matches everything except a space.
    "all_punctuations": re.compile(r"([^\s]+)$"),
}


def is_valid_connection_scheme(text: str) -> tuple[bool, str | None]:
    # exit early if the text does not resemble a DSN URI
    if "://" not in text:
        return False, None
    scheme = text.split("://")[0]
    if scheme not in ("mysql", "mysqlx", "tcp", "socket", "ssh"):
        return False, scheme
    else:
        return True, None


def last_word(text: str, include: str = "alphanum_underscore") -> str:
    r"""
    Find the last word in a sentence.

    >>> last_word('abc')
    'abc'
    >>> last_word(' abc')
    'abc'
    >>> last_word('')
    ''
    >>> last_word(' ')
    ''
    >>> last_word('abc ')
    ''
    >>> last_word('abc def')
    'def'
    >>> last_word('abc def ')
    ''
    >>> last_word('abc def;')
    ''
    >>> last_word('bac $def')
    'def'
    >>> last_word('bac $def', include='most_punctuations')
    '$def'
    >>> last_word('bac \def', include='most_punctuations')
    '\\\\def'
    >>> last_word('bac \def;', include='most_punctuations')
    '\\\\def;'
    >>> last_word('bac::def', include='most_punctuations')
    'def'
    """

    if not text:  # Empty string
        return ""

    if text[-1].isspace():
        return ""
    else:
        regex = cleanup_regex[include]
        matches = regex.search(text)
        if matches:
            return matches.group(0)
        else:
            return ""


# This code is borrowed from sqlparse example script.
# <url>
def is_subselect(parsed: TokenList) -> bool:
    if not parsed.is_group:
        return False
    for item in parsed.tokens:
        if item.ttype is DML and item.value.upper() in ("SELECT", "INSERT", "UPDATE", "CREATE", "DELETE"):
            return True
    return False


def get_last_select(parsed: TokenList) -> TokenList:
    """
    Takes a parsed sql statement and returns the last select query where applicable.

    The intended use case is for when giving table suggestions based on columns, where
    we only want to look at the columns from the most recent select. This works for a single
    select query, or one or more sub queries (the useful part).

    The custom logic is necessary because the typical sqlparse logic for things like finding
    sub selects (i.e. is_subselect) only works on complete statements, such as:

    * select c1 from t1;

    However when suggesting tables based on columns, we only have partial select statements, i.e.:

    * select c1
    * select c1 from (select c2)

    So given the above, we must parse them ourselves as they are not viewed as complete statements.

    Returns a TokenList of the last select statement's tokens.
    """
    select_indexes: list[int] = []

    for token in parsed:
        if token.match(DML, "select"):  # match is case insensitive
            select_indexes.append(parsed.token_index(token))

    last_select = TokenList()

    if select_indexes:
        last_select = TokenList(parsed[select_indexes[-1] :])

    return last_select


def extract_from_part(parsed: TokenList, stop_at_punctuation: bool = True) -> Generator[Any, None, None]:
    tbl_prefix_seen = False
    for item in parsed.tokens:
        if tbl_prefix_seen:
            if is_subselect(item):
                for x in extract_from_part(item, stop_at_punctuation):
                    yield x
            elif stop_at_punctuation and item.ttype is Punctuation:
                return None
            # Multiple JOINs in the same query won't work properly since
            # "ON" is a keyword and will trigger the next elif condition.
            # So instead of stooping the loop when finding an "ON" skip it
            # eg: 'SELECT * FROM abc JOIN def ON abc.id = def.abc_id JOIN ghi'
            elif item.ttype is Keyword and item.value.upper() == "ON":
                tbl_prefix_seen = False
                continue
            # An incomplete nested select won't be recognized correctly as a
            # sub-select. eg: 'SELECT * FROM (SELECT id FROM user'. This causes
            # the second FROM to trigger this elif condition resulting in a
            # StopIteration. So we need to ignore the keyword if the keyword
            # FROM.
            # Also 'SELECT * FROM abc JOIN def' will trigger this elif
            # condition. So we need to ignore the keyword JOIN and its variants
            # INNER JOIN, FULL OUTER JOIN, etc.
            elif item.ttype is Keyword and (not item.value.upper() == "FROM") and (not item.value.upper().endswith("JOIN")):
                return None
            else:
                yield item
        elif (item.ttype is Keyword or item.ttype is Keyword.DML) and item.value.upper() in (
            "COPY",
            "FROM",
            "INTO",
            "UPDATE",
            "TABLE",
            "JOIN",
        ):
            tbl_prefix_seen = True
        # 'SELECT a, FROM abc' will detect FROM as part of the column list.
        # So this check here is necessary.
        elif isinstance(item, IdentifierList):
            for identifier in item.get_identifiers():
                if identifier.ttype is Keyword and identifier.value.upper() == "FROM":
                    tbl_prefix_seen = True
                    break


def extract_table_identifiers(token_stream: Generator[Any, None, None]) -> Generator[tuple[str | None, str, str], None, None]:
    """yields tuples of (schema_name, table_name, table_alias)"""

    for item in token_stream:
        if isinstance(item, IdentifierList):
            for identifier in item.get_identifiers():
                # Sometimes Keywords (such as FROM ) are classified as
                # identifiers which don't have the get_real_name() method.
                try:
                    schema_name = identifier.get_parent_name()
                    real_name = identifier.get_real_name()
                except AttributeError:
                    continue
                if real_name:
                    yield (schema_name, real_name, identifier.get_alias())
        elif isinstance(item, Identifier):
            real_name = item.get_real_name()
            schema_name = item.get_parent_name()

            if real_name:
                yield (schema_name, real_name, item.get_alias())
            else:
                name = item.get_name()
                yield (None, name, item.get_alias() or name)
        elif isinstance(item, Function):
            yield (None, item.get_name(), item.get_name())


# extract_tables is inspired from examples in the sqlparse lib.
def extract_tables(sql: str) -> list[tuple[str | None, str, str]]:
    """Extract the table names from an SQL statement.

    Returns a list of (schema, table, alias) tuples

    """
    parsed = sqlparse.parse(sql)
    if not parsed:
        return []

    # INSERT statements must stop looking for tables at the sign of first
    # Punctuation. eg: INSERT INTO abc (col1, col2) VALUES (1, 2)
    # abc is the table name, but if we don't stop at the first lparen, then
    # we'll identify abc, col1 and col2 as table names.
    insert_stmt = parsed[0].token_first().value.lower() == "insert"
    stream = extract_from_part(parsed[0], stop_at_punctuation=insert_stmt)
    return list(extract_table_identifiers(stream))


def extract_columns_from_select(sql: str) -> list[str]:
    """
    Extract the column names from a select SQL statement.

    Returns a list of columns.
    """
    parsed = sqlparse.parse(sql)
    if not parsed:
        return []

    statement = get_last_select(parsed[0])

    # if there is no select, skip checking for columns
    if not statement:
        return []

    columns = []

    # Loops through the tokens (pieces) of the SQL statement.
    # Once it finds the SELECT token (generally first), it
    # will then start looking for columns from that point on.
    # The get_real_name() function returns the real column name
    # even if an alias is used.
    found_select = False
    for token in statement.tokens:
        if token.ttype is DML and token.value.upper() == 'SELECT':
            found_select = True
        elif found_select:
            if isinstance(token, IdentifierList):
                # multiple columns
                for identifier in token.get_identifiers():
                    column = identifier.get_real_name()
                    columns.append(column)
            elif isinstance(token, Identifier):
                # single column
                column = token.get_real_name()
                columns.append(column)
            elif token.ttype is Keyword:
                break

            if columns:
                break
    return columns


def extract_tables_from_complete_statements(sql: str) -> list[tuple[str | None, str, str | None]]:
    """Extract the table names from a complete and valid series of SQL
    statements.

    Returns a list of (schema, table, alias) tuples

    """
    # sqlglot chokes entirely on things like "\T" that it doesn't know about,
    # but is much better at extracting table names from complete statements.
    # sqlparse can extract the series of statements, though it also doesn't
    # understand "\T".
    roughly_parsed = sqlparse.parse(sql)
    if not roughly_parsed:
        return []

    finely_parsed = []
    for rough_statement in roughly_parsed:
        try:
            finely_parsed.append(sqlglot.parse_one(str(rough_statement), read='mysql'))
        except sqlglot.errors.ParseError:
            pass

    tables = []
    for fine_statement in finely_parsed:
        for identifier in fine_statement.find_all(sqlglot.exp.Table):
            if identifier.parent_select and identifier.parent_select.sql().startswith('WITH'):
                continue
            tables.append((
                None if identifier.db == '' else identifier.db,
                identifier.name,
                None if identifier.alias == '' else identifier.alias,
            ))

    return tables


def find_prev_keyword(sql: str) -> tuple[Token | None, str]:
    """Find the last sql keyword in an SQL statement

    Returns the value of the last keyword, and the text of the query with
    everything after the last keyword stripped
    """
    if not sql.strip():
        return None, ""

    parsed = sqlparse.parse(sql)[0]
    flattened = list(parsed.flatten())

    logical_operators = ("AND", "OR", "NOT", "BETWEEN")

    for t in reversed(flattened):
        if t.value == "(" or (t.is_keyword and (t.value.upper() not in logical_operators)):
            # Find the location of token t in the original parsed statement
            # We can't use parsed.token_index(t) because t may be a child token
            # inside a TokenList, in which case token_index thows an error
            # Minimal example:
            #   p = sqlparse.parse('select * from foo where bar')
            #   t = list(p.flatten())[-3]  # The "Where" token
            #   p.token_index(t)  # Throws ValueError: not in list
            idx = flattened.index(t)

            # Combine the string values of all tokens in the original list
            # up to and including the target keyword token t, to produce a
            # query string with everything after the keyword token removed
            text = "".join(tok.value for tok in flattened[: idx + 1])
            return t, text

    return None, ""


def query_starts_with(query: str, prefixes: list[str]) -> bool:
    """Check if the query starts with any item from *prefixes*."""
    prefixes = [prefix.lower() for prefix in prefixes]
    formatted_sql = sqlparse.format(query.lower(), strip_comments=True)
    return bool(formatted_sql) and formatted_sql.split()[0] in prefixes


def queries_start_with(queries: str, prefixes: list[str]) -> bool:
    """Check if any queries start with any item from *prefixes*."""
    for query in sqlparse.split(queries):
        if query and query_starts_with(query, prefixes) is True:
            return True
    return False


def query_has_where_clause(query: str) -> bool:
    """Check if the query contains a where-clause."""
    return any(isinstance(token, sqlparse.sql.Where) for token_list in sqlparse.parse(query) for token in token_list)


# todo: handle "UPDATE LOW_PRIORITY" and "UPDATE IGNORE"
def query_is_single_table_update(query: str) -> bool:
    """Check if a query is a simple single-table UPDATE."""
    cleaned_query_for_parsing_only = sqlparse.format(query, strip_comments=True)
    cleaned_query_for_parsing_only = re.sub(r'\s+', ' ', cleaned_query_for_parsing_only)
    if not cleaned_query_for_parsing_only:
        return False
    parsed = sqlparse.parse(cleaned_query_for_parsing_only)
    if not parsed:
        return False
    statement = parsed[0]
    return (
        statement[0].value.lower() == 'update'
        and statement[1].is_whitespace
        and ',' not in statement[2].value  # multiple tables
        and statement[3].is_whitespace
        and statement[4].value.lower() == 'set'
    )


def is_destructive(keywords: list[str], queries: str) -> bool:
    """Returns True if any of the queries in *queries* is destructive."""
    for query in sqlparse.split(queries):
        if not query:
            continue
        # subtle: if "UPDATE" is one of our keywords AND "query" starts with "UPDATE"
        if query_starts_with(query, keywords) and query_starts_with(query, ["update"]):
            if query_has_where_clause(query) and query_is_single_table_update(query):
                return False
            else:
                return True
        if query_starts_with(query, keywords):
            return True

    return False


def is_dropping_database(queries: str, dbname: str | None) -> bool:
    """Determine if the query is dropping a specific database."""
    result = False
    if dbname is None:
        return False

    def normalize_db_name(db: str) -> str:
        return db.lower().strip('`"')

    dbname = normalize_db_name(dbname)

    for query in sqlparse.parse(queries):
        keywords = [t for t in query.tokens if t.is_keyword]
        if len(keywords) < 2:
            continue
        if keywords[0].normalized in ("DROP", "CREATE") and keywords[1].value.lower() in (
            "database",
            "schema",
        ):
            database_token = next((t for t in query.tokens if isinstance(t, Identifier)), None)
            if database_token is not None and normalize_db_name(database_token.get_name()) == dbname:
                result = keywords[0].normalized == "DROP"
    return result


if __name__ == "__main__":
    sql = "select * from (select t. from tabl t"
    print(extract_tables(sql))

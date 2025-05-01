import re

import sqlglot
import sqlparse
from sqlparse.sql import Function, Identifier, IdentifierList
from sqlparse.tokens import DML, Keyword, Punctuation

cleanup_regex = {
    # This matches only alphanumerics and underscores.
    "alphanum_underscore": re.compile(r"(\w+)$"),
    # This matches everything except spaces, parens, colon, and comma
    "many_punctuations": re.compile(r"([^():,\s]+)$"),
    # This matches everything except spaces, parens, colon, comma, and period
    "most_punctuations": re.compile(r"([^\.():,\s]+)$"),
    # This matches everything except a space.
    "all_punctuations": re.compile(r"([^\s]+)$"),
}


def last_word(text, include="alphanum_underscore"):
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
def is_subselect(parsed):
    if not parsed.is_group:
        return False
    for item in parsed.tokens:
        if item.ttype is DML and item.value.upper() in ("SELECT", "INSERT", "UPDATE", "CREATE", "DELETE"):
            return True
    return False


def extract_from_part(parsed, stop_at_punctuation=True):
    tbl_prefix_seen = False
    for item in parsed.tokens:
        if tbl_prefix_seen:
            if is_subselect(item):
                for x in extract_from_part(item, stop_at_punctuation):
                    yield x
            elif stop_at_punctuation and item.ttype is Punctuation:
                return
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
                return
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


def extract_table_identifiers(token_stream):
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
def extract_tables(sql):
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


def extract_tables_from_complete_statements(sql):
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
    for statement in roughly_parsed:
        try:
            finely_parsed.append(sqlglot.parse_one(str(statement), read='mysql'))
        except sqlglot.errors.ParseError:
            pass

    tables = []
    for statement in finely_parsed:
        for identifier in statement.find_all(sqlglot.exp.Table):
            if identifier.parent_select.sql().startswith('WITH'):
                continue
            tables.append((
                None if identifier.db == '' else identifier.db,
                identifier.name,
                None if identifier.alias == '' else identifier.alias,
            ))

    return tables


def find_prev_keyword(sql):
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


def query_starts_with(query, prefixes):
    """Check if the query starts with any item from *prefixes*."""
    prefixes = [prefix.lower() for prefix in prefixes]
    formatted_sql = sqlparse.format(query.lower(), strip_comments=True)
    return bool(formatted_sql) and formatted_sql.split()[0] in prefixes


def queries_start_with(queries, prefixes):
    """Check if any queries start with any item from *prefixes*."""
    for query in sqlparse.split(queries):
        if query and query_starts_with(query, prefixes) is True:
            return True
    return False


def query_has_where_clause(query):
    """Check if the query contains a where-clause."""
    return any(isinstance(token, sqlparse.sql.Where) for token_list in sqlparse.parse(query) for token in token_list)


def is_destructive(queries):
    """Returns if any of the queries in *queries* is destructive."""
    keywords = ("drop", "shutdown", "delete", "truncate", "alter")
    for query in sqlparse.split(queries):
        if query:
            if query_starts_with(query, keywords) is True:
                return True
            elif query_starts_with(query, ["update"]) is True and not query_has_where_clause(query):
                return True

    return False


if __name__ == "__main__":
    sql = "select * from (select t. from tabl t"
    print(extract_tables(sql))


def is_dropping_database(queries, dbname):
    """Determine if the query is dropping a specific database."""
    result = False
    if dbname is None:
        return False

    def normalize_db_name(db):
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

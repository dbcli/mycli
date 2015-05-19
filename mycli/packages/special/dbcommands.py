from __future__ import print_function

import logging
from collections import namedtuple

TableInfo = namedtuple("TableInfo", ['checks', 'relkind', 'hasindex',
'hasrules', 'hastriggers', 'hasoids', 'tablespace', 'reloptions', 'reloftype',
'relpersistence'])


log = logging.getLogger(__name__)

def sql_name_pattern(pattern):
    """
    Takes a wildcard-pattern and converts to an appropriate SQL pattern to be
    used in a WHERE clause.

    Returns: schema_pattern, table_pattern

    >>> sql_name_pattern('foo*."b""$ar*"')
    ('^(foo.*)$', '^(b"\\\\$ar\\\\*)$')
    """

    inquotes = False
    relname = ''
    schema = None
    pattern_len = len(pattern)
    i = 0

    while i < pattern_len:
        c = pattern[i]
        if c == '"':
            if inquotes and i + 1 < pattern_len and pattern[i + 1] == '"':
                relname += '"'
                i += 1
            else:
                inquotes = not inquotes
        elif not inquotes and c.isupper():
            relname += c.lower()
        elif not inquotes and c == '*':
            relname += '.*'
        elif not inquotes and c == '?':
            relname += '.'
        elif not inquotes and c == '.':
            # Found schema/name separator, move current pattern to schema
            schema = relname
            relname = ''
        else:
            # Dollar is always quoted, whether inside quotes or not.
            if c == '$' or inquotes and c in '|*+?()[]{}.^\\':
                relname += '\\'
            relname += c
        i += 1

    if relname:
        relname = '^(' + relname + ')$'

    if schema:
        schema = '^(' + schema + ')$'

    return schema, relname

def change_db(cur, arg, db_obj):
    if arg is None:
        db_obj.connect()
    else:
        db_obj.connect(database=arg)

    yield (None, None, None, 'You are now connected to database "%s" as '
            'user "%s"' % (db_obj.dbname, db_obj.user))

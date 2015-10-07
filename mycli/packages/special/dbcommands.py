import logging
from .main import special_command, RAW_QUERY, PARSED_QUERY

log = logging.getLogger(__name__)

@special_command('\\dt', '\\dt [table]', 'List or describe tables.', arg_type=PARSED_QUERY, case_sensitive=True)
def list_tables(cur, arg=None, arg_type=PARSED_QUERY):
    if arg:
        query = 'SHOW FIELDS FROM {0}'.format(arg)
    else:
        query = 'SHOW TABLES'
    log.debug(query)
    cur.execute(query)
    if cur.description:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, '')]
    else:
        return [(None, None, None, '')]

@special_command('\\l', '\\l', 'List databases.', arg_type=RAW_QUERY, case_sensitive=True)
def list_databases(cur, **_):
    query = 'SHOW DATABASES'
    log.debug(query)
    cur.execute(query)
    if cur.description:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, '')]
    else:
        return [(None, None, None, '')]


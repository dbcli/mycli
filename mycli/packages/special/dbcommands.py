import logging
import os
import platform
from mycli import __version__
from mycli.packages.tabulate import tabulate
from mycli.packages.special import iocommands
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

def format_uptime(uptime_in_seconds):
    """Format number of seconds into human-readable string.

    :param uptime_in_seconds: The server uptime in seconds.
    :returns: A human-readable string representing the uptime.

    >>> uptime = format_uptime('56892')
    >>> print(uptime)
    15 hours 48 min 12 sec
    """

    m, s = divmod(int(uptime_in_seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)

    uptime_values = []

    for value, unit in ((d, 'days'), (h, 'hours'), (m, 'min'), (s, 'sec')):
        if value == 0 and not uptime_values:
            # Don't include a value/unit if the unit isn't applicable to
            # the uptime. E.g. don't do 0 days 0 hours 1 min 30 sec.
            continue
        elif value == 1 and unit.endswith('s'):
            # Remove the "s" if the unit is singular.
            unit = unit[:-1]
        uptime_values.append('{} {}'.format(value, unit))

    uptime = ' '.join(uptime_values)
    return uptime

@special_command('status', '\\s', 'Get status information from the server.',
                 arg_type=RAW_QUERY, case_sensitive=True)
def status(cur, **_):
    query = 'SHOW GLOBAL STATUS;'
    log.debug(query)
    cur.execute(query)
    status = dict(cur.fetchall())

    query = 'SHOW GLOBAL VARIABLES;'
    log.debug(query)
    cur.execute(query)
    variables = dict(cur.fetchall())

    print('--------------')

    # Output the mycli client information.
    implementation = platform.python_implementation()
    version = platform.python_version()
    header = []
    header.append('mycli {},'.format(__version__))
    header.append('running on {} {}'.format(implementation, version))
    print(' '.join(header) + '\n')

    # Build the output that will be displayed as a table.
    output = []

    output.append(('Connection id:', cur.connection.thread_id()))

    query = 'SELECT DATABASE(), USER();'
    log.debug(query)
    cur.execute(query)
    db, user = cur.fetchone()
    if db is None:
        db = ''

    output.append(('Current database:', db))
    output.append(('Current user:', user))

    if iocommands.is_pager_enabled():
        if 'PAGER' in os.environ:
            pager = os.environ['PAGER']
        else:
            pager = 'System default'
    else:
        pager = 'stdout'
    output.append(('Current pager:', pager))

    output.append(('Server version:', '{} {}'.format(
        variables['version'], variables['version_comment'])))
    output.append(('Protocol version:', variables['protocol_version']))

    if 'unix' in cur.connection.host_info.lower():
        host_info = cur.connection.host_info
    else:
        host_info = '{} via TCP/IP'.format(cur.connection.host)

    output.append(('Connection:', host_info))

    query = ('SELECT @@character_set_server, @@character_set_database, '
             '@@character_set_client, @@character_set_connection LIMIT 1;')
    log.debug(query)
    cur.execute(query)
    charset = cur.fetchone()
    output.append(('Server characterset:', charset[0]))
    output.append(('Db characterset:', charset[1]))
    output.append(('Client characterset:', charset[2]))
    output.append(('Conn. characterset:', charset[3]))

    if 'TCP/IP' in host_info:
        output.append(('TCP port:', cur.connection.port))
    else:
        output.append(('UNIX socket:', variables['socket']))

    output.append(('Uptime:', format_uptime(status['Uptime'])))

    # Print the buffered output in two columns.
    print(tabulate(output, tablefmt='plain')[0])

    # Print the current server statistics.
    stats = []
    stats.append('Connections: {}'.format(status['Threads_connected']))
    stats.append('Questions: {}'.format(status['Queries']))
    stats.append('Slow queries: {}'.format(status['Slow_queries']))
    stats.append('Opens: {}'.format(status['Opened_tables']))
    stats.append('Flush tables: {}'.format(status['Flush_commands']))
    stats.append('Open tables: {}'.format(status['Open_tables']))
    queries_per_second = int(status['Queries']) / int(status['Uptime'])
    stats.append('Queries per second avg: {:.3f}'.format(queries_per_second))
    stats = '  '.join(stats)
    print('\n' + stats)

    print('--------------')
    return [(None, None, None, '')]

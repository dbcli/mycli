import logging
import os
import platform
from mycli import __version__
from mycli.packages.special import iocommands
from mycli.packages.special.utils import format_uptime
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

@special_command('status', '\\s', 'Get status information from the server.',
                 arg_type=RAW_QUERY, aliases=('\\s', ), case_sensitive=True)
def status(cur, **_):
    query = 'SHOW GLOBAL STATUS;'
    log.debug(query)
    cur.execute(query)
    status = dict(cur.fetchall())

    query = 'SHOW GLOBAL VARIABLES;'
    log.debug(query)
    cur.execute(query)
    variables = dict(cur.fetchall())

    # Create output buffers.
    title = []
    output = []
    footer = []

    title.append('--------------')

    # Output the mycli client information.
    implementation = platform.python_implementation()
    version = platform.python_version()
    client_info = []
    client_info.append('mycli {0},'.format(__version__))
    client_info.append('running on {0} {1}'.format(implementation, version))
    title.append(' '.join(client_info) + '\n')

    # Build the output that will be displayed as a table.
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

    output.append(('Server version:', '{0} {1}'.format(
        variables['version'], variables['version_comment'])))
    output.append(('Protocol version:', variables['protocol_version']))

    if 'unix' in cur.connection.host_info.lower():
        host_info = cur.connection.host_info
    else:
        host_info = '{0} via TCP/IP'.format(cur.connection.host)

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

    # Print the current server statistics.
    stats = []
    stats.append('Connections: {0}'.format(status['Threads_connected']))
    stats.append('Queries: {0}'.format(status['Queries']))
    stats.append('Slow queries: {0}'.format(status['Slow_queries']))
    stats.append('Opens: {0}'.format(status['Opened_tables']))
    stats.append('Flush tables: {0}'.format(status['Flush_commands']))
    stats.append('Open tables: {0}'.format(status['Open_tables']))
    queries_per_second = int(status['Queries']) / int(status['Uptime'])
    stats.append('Queries per second avg: {:.3f}'.format(queries_per_second))
    stats = '  '.join(stats)
    footer.append('\n' + stats)

    footer.append('--------------')
    return [('\n'.join(title), output, '', '\n'.join(footer))]

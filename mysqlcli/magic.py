from .main import MysqlCli
import sql.parse
import sql.connection
import logging

_logger = logging.getLogger(__name__)

def load_ipython_extension(ipython):

    #This is called via the ipython command '%load_ext mysqlcli.magic'

    #first, load the sql magic if it isn't already loaded
    if not ipython.find_line_magic('sql'):
        ipython.run_line_magic('load_ext', 'sql')

    #register our own magic
    ipython.register_magic_function(mysqlcli_line_magic, 'line', 'mysqlcli')

def mysqlcli_line_magic(line):
    _logger.debug('mysqlcli magic called: %r', line)
    parsed = sql.parse.parse(line, {})
    conn = sql.connection.Connection.get(parsed['connection'])

    try:
        #A corresponding mysqlcli object already exists
        mysqlcli = conn._mysqlcli
        _logger.debug('Reusing existing mysqlcli')
    except AttributeError:
        #I can't figure out how to get the underylying psycopg2 connection
        #from the sqlalchemy connection, so just grab the url and make a
        #new connection
        mysqlcli = mysqlcli()
        u = conn.session.engine.url
        _logger.debug('New mysqlcli: %r', str(u))

        mysqlcli.connect(u.database, u.host, u.username, u.port, u.password)
        conn._mysqlcli = mysqlcli

    #For convenience, print the connection alias
    print('Connected: {}'.format(conn.name))

    try:
        mysqlcli.run_cli()
    except SystemExit:
        pass

    if not mysqlcli.query_history:
        return

    q = mysqlcli.query_history[-1]
    if q.mutating:
        _logger.debug('Mutating query detected -- ignoring')
        return

    if q.successful:
        ipython = get_ipython()
        return ipython.run_cell_magic('sql', line, q.query)


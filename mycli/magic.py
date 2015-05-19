from .main import MyCli
import sql.parse
import sql.connection
import logging

_logger = logging.getLogger(__name__)

def load_ipython_extension(ipython):

    # This is called via the ipython command '%load_ext mycli.magic'.

    # First, load the sql magic if it isn't already loaded.
    if not ipython.find_line_magic('sql'):
        ipython.run_line_magic('load_ext', 'sql')

    # Register our own magic.
    ipython.register_magic_function(mycli_line_magic, 'line', 'mycli')

def mycli_line_magic(line):
    _logger.debug('mycli magic called: %r', line)
    parsed = sql.parse.parse(line, {})
    conn = sql.connection.Connection.get(parsed['connection'])

    try:
        # A corresponding mycli object already exists
        mycli = conn._mycli
        _logger.debug('Reusing existing mycli')
    except AttributeError:
        mycli = MyCli()
        u = conn.session.engine.url
        _logger.debug('New mycli: %r', str(u))

        mycli.connect(u.database, u.host, u.username, u.port, u.password)
        conn._mycli = mycli

    # For convenience, print the connection alias
    print('Connected: {}'.format(conn.name))

    try:
        mycli.run_cli()
    except SystemExit:
        pass

    if not mycli.query_history:
        return

    q = mycli.query_history[-1]
    if q.mutating:
        _logger.debug('Mutating query detected -- ignoring')
        return

    if q.successful:
        ipython = get_ipython()
        return ipython.run_cell_magic('sql', line, q.query)

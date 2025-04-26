import logging

import sql.connection
import sql.parse

from mycli.main import MyCli

_logger = logging.getLogger(__name__)


def load_ipython_extension(ipython):
    # This is called via the ipython command '%load_ext mycli.magic'.

    # First, load the sql magic if it isn't already loaded.
    if not ipython.find_line_magic("sql"):
        ipython.run_line_magic("load_ext", "sql")

    # Register our own magic.
    ipython.register_magic_function(mycli_line_magic, "line", "mycli")


def mycli_line_magic(line):
    _logger.debug("mycli magic called: %r", line)
    parsed = sql.parse.parse(line, {})
    # "get" was renamed to "set" in ipython-sql:
    # https://github.com/catherinedevlin/ipython-sql/commit/f4283c65aaf68f961e84019e8b939e4a3c501d43
    if hasattr(sql.connection.Connection, "get"):
        conn = sql.connection.Connection.get(parsed["connection"])
    else:
        try:
            conn = sql.connection.Connection.set(parsed["connection"])
        # a new positional argument was added to Connection.set in version 0.4.0 of ipython-sql
        except TypeError:
            conn = sql.connection.Connection.set(parsed["connection"], False)
    try:
        # A corresponding mycli object already exists
        mycli = conn._mycli
        _logger.debug("Reusing existing mycli")
    except AttributeError:
        mycli = MyCli()
        u = conn.session.engine.url
        _logger.debug("New mycli: %r", str(u))

        mycli.connect(host=u.host, port=u.port, passwd=u.password, database=u.database, user=u.username, init_command=None)
        conn._mycli = mycli

    # For convenience, print the connection alias
    print("Connected: {}".format(conn.name))

    try:
        mycli.run_cli()
    except SystemExit:
        pass

    if not mycli.query_history:
        return

    q = mycli.query_history[-1]
    if q.mutating:
        _logger.debug("Mutating query detected -- ignoring")
        return

    if q.successful:
        ipython = get_ipython()  # noqa: F821
        return ipython.run_cell_magic("sql", line, q.query)

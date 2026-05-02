import logging
import os
import platform

from pymysql import ProgrammingError
from pymysql.cursors import Cursor

from mycli import __version__
from mycli.packages.special import iocommands
from mycli.packages.special.main import ArgType, SpecialCommandAlias, special_command
from mycli.packages.special.utils import (
    format_uptime,
    get_local_timezone,
    get_server_timezone,
    get_ssl_cipher,
    get_ssl_version,
)
from mycli.packages.sqlresult import SQLResult

logger = logging.getLogger(__name__)


@special_command(
    "\\dt",
    "\\dt[+] [table]",
    "List or describe tables.",
    arg_type=ArgType.PARSED_QUERY,
    case_sensitive=True,
)
def list_tables(
    cur: Cursor,
    arg: str | None = None,
    _arg_type: ArgType = ArgType.PARSED_QUERY,
    command_verbosity: bool = False,
) -> list[SQLResult]:
    if arg:
        query = f'SHOW FIELDS FROM {arg}'
    else:
        query = "SHOW TABLES"
    logger.debug(query)
    cur.execute(query)
    if cur.description:
        header = [x[0] for x in cur.description]
    else:
        return [SQLResult()]

    # Fetch results before potentially executing another query
    results = list(cur.fetchall()) if command_verbosity and arg else cur

    postamble = ''
    if command_verbosity and arg:
        query = f'SHOW CREATE TABLE {arg}'
        logger.debug(query)
        cur.execute(query)
        if one := cur.fetchone():
            postamble = one[1]

    # todo missing a status line because sqlexecute.get_result was not used
    return [SQLResult(header=header, rows=results, postamble=postamble)]


@special_command(
    "\\l",
    "\\l",
    "List databases.",
    arg_type=ArgType.RAW_QUERY,
    case_sensitive=True,
)
def list_databases(cur: Cursor, **_) -> list[SQLResult]:
    query = "SHOW DATABASES"
    logger.debug(query)
    cur.execute(query)
    if cur.description:
        header = [x[0] for x in cur.description]
        # todo missing a status line because sqlexecute.get_result was not used
        return [SQLResult(header=header, rows=cur)]
    else:
        return [SQLResult()]


@special_command(
    "status",
    "status",
    "Get status information from the server.",
    arg_type=ArgType.RAW_QUERY,
    case_sensitive=True,
    aliases=[SpecialCommandAlias("\\s", case_sensitive=True)],
)
def status(cur: Cursor, **_) -> list[SQLResult]:
    query = "SHOW GLOBAL STATUS;"
    logger.debug(query)
    try:
        cur.execute(query)
    except ProgrammingError:
        # Fallback in case query fails, as it does with Mysql 4
        query = "SHOW STATUS;"
        logger.debug(query)
        cur.execute(query)
    status = dict(cur.fetchall())

    query = "SHOW GLOBAL VARIABLES;"
    logger.debug(query)
    cur.execute(query)
    global_variables = dict(cur.fetchall())

    query = "SHOW SESSION VARIABLES;"
    logger.debug(query)
    cur.execute(query)
    session_variables = dict(cur.fetchall())

    # decode in case keys are bytes, as with Mysql 4
    if global_variables and isinstance(list(global_variables)[0], bytes):
        global_variables = {k.decode("utf-8"): v.decode("utf-8") for k, v in global_variables.items()}
    if session_variables and isinstance(list(session_variables)[0], bytes):
        session_variables = {k.decode("utf-8"): v.decode("utf-8") for k, v in session_variables.items()}
    if status and isinstance(list(status)[0], bytes):
        status = {k.decode("utf-8"): v.decode("utf-8") for k, v in status.items()}

    # Create output buffers.
    preamble = []
    header = ['Setting', 'Value']
    output = []
    footer = []

    preamble.append("--------------")

    # Output the mycli client information.
    implementation = platform.python_implementation()
    version = platform.python_version()
    client_info = []
    client_info.append(f'mycli {__version__}')
    client_info.append(f'running on {implementation} {version}')
    preamble.append(" ".join(client_info) + "\n")

    # Build the output that will be displayed as a table.
    output.append(("Connection id:", cur.connection.thread_id()))

    query = "SELECT DATABASE(), USER();"
    logger.debug(query)
    cur.execute(query)
    if one := cur.fetchone():
        db, user = one
    else:
        db = ""
        user = ""
    output.append(("Current database:", db))
    output.append(("Current user:", user))

    if iocommands.is_pager_enabled():
        if "PAGER" in os.environ:
            pager = os.environ["PAGER"]
        else:
            pager = "System default"
    else:
        pager = "stdout"
    output.append(("Current pager:", pager))

    output.append(("Using delimiter:", iocommands.get_current_delimiter()))
    output.append(("Using outfile:", iocommands.tee_file.name if iocommands.tee_file else ''))

    output.append(("Server version:", f'{global_variables["version"]} {global_variables["version_comment"]}'))
    output.append(("Protocol version:", global_variables["protocol_version"]))
    if cipher := get_ssl_cipher(cur):
        output.append(('SSL:', f'Cipher in use is {cipher}'))
    else:
        output.append(('SSL:', ''))
    output.append(('SSL/TLS version:', get_ssl_version(cur) or ''))

    if getattr(cur.connection, 'unix_socket', None):
        host_info = cur.connection.host_info
    else:
        host_info = f'{cur.connection.host} via TCP/IP'

    output.append(("Connection:", host_info))

    charset_spec = [
        {'name': 'Server characterset:', 'variable': 'character_set_server'},
        {'name': 'Db     characterset:', 'variable': 'character_set_database'},
        {'name': 'Client characterset:', 'variable': 'character_set_client'},
        {'name': 'Conn.  characterset:', 'variable': 'character_set_connection'},
        {'name': 'Result characterset:', 'variable': 'character_set_results'},
    ]
    for elt in charset_spec:
        if elt['variable'] in session_variables:
            value = session_variables[elt['variable']]
        else:
            value = ''
        output.append((elt['name'], value))

    if getattr(cur.connection, 'unix_socket', None):
        output.append(('UNIX socket:', global_variables['socket']))
    else:
        output.append(('TCP port:', cur.connection.port))

    output.append(('Server timezone:', get_server_timezone(global_variables)))
    output.append(('Local  timezone:', get_local_timezone()))

    if "Uptime" in status:
        output.append(("Uptime:", format_uptime(status["Uptime"])))

    if "Threads_connected" in status:
        # Print the current server statistics.
        stats = []
        stats.append(f'Connections: {status["Threads_connected"]}')
        if "Queries" in status:
            stats.append(f'Queries: {status["Queries"]}')
        stats.append(f'Slow queries: {status["Slow_queries"]}')
        stats.append(f'Opens: {status["Opened_tables"]}')
        if "Flush_commands" in status:
            stats.append(f'Flush tables: {status["Flush_commands"]}')
        stats.append(f'Open tables: {status["Open_tables"]}')
        if "Queries" in status:
            queries_per_second = int(status["Queries"]) / int(status["Uptime"])
            stats.append(f'Queries per second avg: {queries_per_second:.3f}')
        stats_str = "  ".join(stats)
        footer.append("\n" + stats_str)

    footer.append("--------------")

    return [SQLResult(preamble="\n".join(preamble), header=header, rows=output, postamble="\n".join(footer))]

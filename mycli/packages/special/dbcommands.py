from __future__ import annotations

import logging
import os
import platform

from pymysql import ProgrammingError
from pymysql.cursors import Cursor

from mycli import __version__
from mycli.packages.special import iocommands
from mycli.packages.special.main import ArgType, special_command
from mycli.packages.special.utils import format_uptime

logger = logging.getLogger(__name__)


@special_command("\\dt", "\\dt[+] [table]", "List or describe tables.", arg_type=ArgType.PARSED_QUERY, case_sensitive=True)
def list_tables(
    cur: Cursor,
    arg: str | None = None,
    _arg_type: ArgType = ArgType.PARSED_QUERY,
    verbose: bool = False,
) -> list[tuple]:
    if arg:
        query = f'SHOW FIELDS FROM {arg}'
    else:
        query = "SHOW TABLES"
    logger.debug(query)
    cur.execute(query)
    tables = cur.fetchall()
    status = ""
    if cur.description:
        headers = [x[0] for x in cur.description]
    else:
        return [(None, None, None, "")]

    if verbose and arg:
        query = f'SHOW CREATE TABLE {arg}'
        logger.debug(query)
        cur.execute(query)
        if one := cur.fetchone():
            status = one[1]

    return [(None, tables, headers, status)]


@special_command("\\l", "\\l", "List databases.", arg_type=ArgType.RAW_QUERY, case_sensitive=True)
def list_databases(cur: Cursor, **_) -> list[tuple]:
    query = "SHOW DATABASES"
    logger.debug(query)
    cur.execute(query)
    if cur.description:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, "")]
    else:
        return [(None, None, None, "")]


@special_command(
    "status", "\\s", "Get status information from the server.", arg_type=ArgType.RAW_QUERY, aliases=["\\s"], case_sensitive=True
)
def status(cur: Cursor, **_) -> list[tuple]:
    query = "SHOW GLOBAL STATUS;"
    logger.debug(query)
    try:
        cur.execute(query)
    except ProgrammingError:
        # Fallback in case query fail, as it does with Mysql 4
        query = "SHOW STATUS;"
        logger.debug(query)
        cur.execute(query)
    status = dict(cur.fetchall())

    query = "SHOW GLOBAL VARIABLES;"
    logger.debug(query)
    cur.execute(query)
    variables = dict(cur.fetchall())

    # prepare in case keys are bytes, as with Python 3 and Mysql 4
    if isinstance(list(variables)[0], bytes) and isinstance(list(status)[0], bytes):
        variables = {k.decode("utf-8"): v.decode("utf-8") for k, v in variables.items()}
        status = {k.decode("utf-8"): v.decode("utf-8") for k, v in status.items()}

    # Create output buffers.
    title = []
    output = []
    footer = []

    title.append("--------------")

    # Output the mycli client information.
    implementation = platform.python_implementation()
    version = platform.python_version()
    client_info = []
    client_info.append(f'mycli {__version__}')
    client_info.append(f'running on {implementation} {version}')
    title.append(" ".join(client_info) + "\n")

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

    output.append(("Server version:", f'{variables["version"]} {variables["version_comment"]}'))
    output.append(("Protocol version:", variables["protocol_version"]))

    if "unix" in cur.connection.host_info.lower():
        host_info = cur.connection.host_info
    else:
        host_info = f'{cur.connection.host} via TCP/IP'

    output.append(("Connection:", host_info))

    query = "SELECT @@character_set_server, @@character_set_database, @@character_set_client, @@character_set_connection LIMIT 1;"
    logger.debug(query)
    cur.execute(query)
    if one := cur.fetchone():
        charset = one
    else:
        charset = ("", "", "", "")
    output.append(("Server characterset:", charset[0]))
    output.append(("Db characterset:", charset[1]))
    output.append(("Client characterset:", charset[2]))
    output.append(("Conn. characterset:", charset[3]))

    if "TCP/IP" in host_info:
        output.append(("TCP port:", cur.connection.port))
    else:
        output.append(("UNIX socket:", variables["socket"]))

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
    return [("\n".join(title), output, "", "\n".join(footer))]

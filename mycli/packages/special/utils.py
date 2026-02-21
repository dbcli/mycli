import logging
import os
import shlex

import click
from pymysql.cursors import Cursor

from mycli.compat import WIN

logger = logging.getLogger(__name__)

CACHED_SSL_VERSION: dict[int, str | None] = {}


def handle_cd_command(arg: str) -> tuple[bool, str | None]:
    """Handles a `cd` shell command by calling python's os.chdir."""
    CD_CMD = "cd"
    tokens: list[str] = []
    try:
        tokens = shlex.split(arg, posix=not WIN)
    except ValueError:
        return False, 'Cannot parse cd command.'
    if not tokens:
        return False, 'Not a cd command.'
    if not tokens[0].lower() == CD_CMD:
        return False, 'Not a cd command.'
    if len(tokens) != 2:
        return False, 'Exactly one directory name must be provided.'
    directory = tokens[1]
    try:
        os.chdir(directory)
        click.echo(os.getcwd(), err=True)
        return True, None
    except OSError as e:
        return False, e.strerror


def format_uptime(uptime_in_seconds: str) -> str:
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

    uptime_values: list[str] = []

    for value, unit in ((d, "days"), (h, "hours"), (m, "min"), (s, "sec")):
        if value == 0 and not uptime_values:
            # Don't include a value/unit if the unit isn't applicable to
            # the uptime. E.g. don't do 0 days 0 hours 1 min 30 sec.
            continue
        if value == 1 and unit.endswith("s"):
            # Remove the "s" if the unit is singular.
            unit = unit[:-1]
        uptime_values.append(f'{value} {unit}')

    uptime = " ".join(uptime_values)
    return uptime


def get_ssl_version(cur: Cursor) -> str | None:
    if cur.connection.thread_id() in CACHED_SSL_VERSION:
        return CACHED_SSL_VERSION[cur.connection.thread_id()] or None

    query = 'SHOW STATUS LIKE "Ssl_version"'
    logger.debug(query)
    cur.execute(query)

    ssl_version = None
    if one := cur.fetchone():
        CACHED_SSL_VERSION[cur.connection.thread_id()] = one[1]
        ssl_version = one[1] or None
    else:
        CACHED_SSL_VERSION[cur.connection.thread_id()] = ''

    return ssl_version

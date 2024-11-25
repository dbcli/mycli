import os
import subprocess


def handle_cd_command(arg):
    """Handles a `cd` shell command by calling python's os.chdir."""
    CD_CMD = "cd"
    tokens = arg.split(CD_CMD + " ")
    directory = tokens[-1] if len(tokens) > 1 else None
    if not directory:
        return False, "No folder name was provided."
    try:
        os.chdir(directory)
        subprocess.call(["pwd"])
        return True, None
    except OSError as e:
        return False, e.strerror


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

    for value, unit in ((d, "days"), (h, "hours"), (m, "min"), (s, "sec")):
        if value == 0 and not uptime_values:
            # Don't include a value/unit if the unit isn't applicable to
            # the uptime. E.g. don't do 0 days 0 hours 1 min 30 sec.
            continue
        elif value == 1 and unit.endswith("s"):
            # Remove the "s" if the unit is singular.
            unit = unit[:-1]
        uptime_values.append("{0} {1}".format(value, unit))

    uptime = " ".join(uptime_values)
    return uptime

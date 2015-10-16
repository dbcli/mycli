import os

def handle_cd_command(arg):
    """Handles a `cd` shell command by calling python's os.chdir."""
    CD_CMD = 'cd'
    command = arg.strip()
    directory = ''

    if command == CD_CMD:
        # Treat `cd` as a change to the root directory.
        # os.path.expanduser does this in a cross platform manner.
        directory = os.path.expanduser('~')
    else:
        tokens = arg.split(CD_CMD + ' ')
        directory = tokens[-1]
    try:
        os.chdir(directory)
    except OSError, e:
        output = e.strerror

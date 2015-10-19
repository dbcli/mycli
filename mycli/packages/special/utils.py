import os
import subprocess

def handle_cd_command(arg):
    """Handles a `cd` shell command by calling python's os.chdir."""
    CD_CMD = 'cd'
    tokens = arg.split(CD_CMD + ' ')
    directory = tokens[-1] if len(tokens) > 1 else None
    if not directory:
        return False, "No folder name was provided."
    try:
        os.chdir(directory)
        subprocess.call(['pwd'])
        return True, None
    except OSError as e:
        return False, e.strerror

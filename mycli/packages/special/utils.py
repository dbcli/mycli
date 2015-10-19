import os
import subprocess

def handle_cd_command(arg):
    """Handles a `cd` shell command by calling python's os.chdir."""
    CD_CMD = 'cd'
    directory = ''
    error = False

    tokens = arg.split(CD_CMD + ' ')
    directory = tokens[-1]

    try:
        os.chdir(directory)
        output = subprocess.check_output('pwd', stderr=subprocess.STDOUT, shell=True)
    except OSError as e:
        return False, e.strerror

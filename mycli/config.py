import shutil
from os.path import expanduser, exists
try:
    from ConfigParser import SafeConfigParser as ConfigParser
except ImportError:
    from configparser import ConfigParser

def load_config(filename, default_filename=None):
    filename = expanduser(filename)
    parser = ConfigParser()

    # Read in the defaults from myclirc.
    if default_filename:
        parser.read(default_filename)

    # Read the actual config file from ~/.myclirc and overlay on top of the
    # defaults.
    parser.read(filename)
    return parser


def write_default_config(source, destination, overwrite=False):
    destination = expanduser(destination)
    if not overwrite and exists(destination):
        return

    shutil.copyfile(source, destination)

from mycli.packages.special.iocommands import execute_system_command

try:
    basestring
except NameError:
    basestring = str


def test_system_command():
    cmd = 'ls'
    response = execute_system_command(cmd)

    assert isinstance(response[0][3], basestring)

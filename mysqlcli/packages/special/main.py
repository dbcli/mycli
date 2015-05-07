from helpers import SpecialCommand, start, end, start_or_end
import iocommands
#import dbcommands

__all__ = ['show_help']

def show_help(*args):
    header = ['Command', 'Shortcut', 'Description']
    footer = None
    result = [(x.name, x.shortcut, x.help) for x in sorted(CASE_SENSITIVE_COMMANDS)]
    return [(result, header, footer)]


CASE_SENSITIVE_COMMANDS = {
        '?': SpecialCommand('?', '\\?', 'Display this help.', show_help, start),
        '\\?': SpecialCommand('\\?', '\\?', 'Display this help.', show_help, start),
        'help': SpecialCommand('help', '\\?', 'Display this help.', show_help, start),
        #'\\r': SpecialCommand('connect', '\\r', 'Reconnect to the server', dbcommands.reconnect, start),
        'ego': SpecialCommand('ego', '\\G', 'Display results vertically.', iocommands.expanded_output, end)
        }

if __name__ == '__main__':
    print show_help()

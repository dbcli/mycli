"""List of special commands supported by MySQL that doesn't touch the
database."""
use_expanded_output = False

def is_expanded_output():
    global use_expanded_output
    return use_expanded_output

def expanded_output(*args):
    global use_expanded_output
    use_expanded_output = not use_expanded_output
    message = u'Expanded display is '
    message += u'on.' if use_expanded_output else u'off.'
    return [(None, None, message)]

from . import export

TIMING_ENABLED = False
use_expanded_output = False

@export
def set_timing_enabled(val):
    global TIMING_ENABLED
    TIMING_ENABLED = val

def toggle_timing(*args):
    global TIMING_ENABLED
    TIMING_ENABLED = not TIMING_ENABLED
    message = "Timing is "
    message += "on." if TIMING_ENABLED else "off."
    return [(None, None, None, message)]

@export
def is_timing_enabled():
    return TIMING_ENABLED

@export
def set_expanded_output(val):
    global use_expanded_output
    use_expanded_output = val

@export
def is_expanded_output():
    return use_expanded_output

def quit(*args):
    raise NotImplementedError

def stub(*args):
    raise NotImplementedError

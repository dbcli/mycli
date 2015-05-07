def start(command, statement):
    return statement.startswith(command)

def end(command, statement):
    return statement.endswith(command)

def start_or_end(command, statement):
    return statement.startswith(command) or statement.endswith(command)

import shlex


def parse_cli_args_to_dict(cli_args: str):
    args_dict = {}
    for arg in shlex.split(cli_args):
        if "=" in arg:
            key, value = arg.split("=")
            args_dict[key] = value
        else:
            args_dict[arg] = None
    return args_dict

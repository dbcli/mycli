from __future__ import annotations

import sys

# Stash for a password extracted from argv before Click parsing.
# Click cannot handle passwords that start with a dash (e.g. --password -mypass)
# because it interprets them as option flags.  _normalize_password_args strips
# such values from argv and stores them here so click_entrypoint can pick them up.
_extracted_password: str | None = None


def filtered_sys_argv() -> list[str]:
    args = sys.argv[1:]
    if args == ['-h']:
        args = ['--help']
    return _normalize_password_args(args)


def _normalize_password_args(args: list[str]) -> list[str]:
    """Extract --password/--pass values that start with a dash before Click
    sees them.

    Click treats tokens starting with "-" as option flags, so
    "--password -mypass" fails. This function removes the password from the
    arg list and stashes it in "_extracted_password" for later retrieval.

    Also handles the "--password=-mypass" / "--pass=-mypass" form.
    """
    global _extracted_password
    _extracted_password = None

    result: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]

        for prefix in ('--password=', '--pass='):
            if arg.startswith(prefix):
                value = arg[len(prefix) :]
                if value.startswith('-'):
                    _extracted_password = value
                    break
        else:
            if arg in ('--password', '--pass') and i + 1 < len(args):
                next_arg = args[i + 1]
                if next_arg.startswith('-') and next_arg != '--':
                    _extracted_password = next_arg
                    i += 2
                    continue
            result.append(arg)
            i += 1
            continue
        i += 1

    return result


def is_valid_connection_scheme(text: str) -> tuple[bool, str | None]:
    # exit early if the text does not resemble a DSN URI
    if "://" not in text:
        return False, None
    scheme = text.split("://")[0]
    if scheme not in ("mysql", "mysqlx", "tcp", "socket", "ssh"):
        return False, scheme
    else:
        return True, None

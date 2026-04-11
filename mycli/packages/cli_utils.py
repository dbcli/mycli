from __future__ import annotations

import sys
from typing import Sequence

from mycli.constants import EMPTY_PASSWORD_FLAG_SENTINEL


def filtered_sys_argv() -> Sequence[str | int]:
    args: Sequence[str | int] = sys.argv[1:]
    password_flag_forms = ['-p', '--pass', '--password']

    if args == ['-h']:
        args = ['--help']

    if args and args[-1] in password_flag_forms:
        args = list(args) + [EMPTY_PASSWORD_FLAG_SENTINEL]

    return list(args)


def is_valid_connection_scheme(text: str) -> tuple[bool, str | None]:
    # exit early if the text does not resemble a DSN URI
    if "://" not in text:
        return False, None
    scheme = text.split("://")[0]
    if scheme not in ("mysql", "mysqlx", "tcp", "socket", "ssh"):
        return False, scheme
    else:
        return True, None

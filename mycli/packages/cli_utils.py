from __future__ import annotations

import sys


def filtered_sys_argv() -> list[str]:
    args = sys.argv[1:]
    if args == ['-h']:
        args = ['--help']
    return args


def is_valid_connection_scheme(text: str) -> tuple[bool, str | None]:
    # exit early if the text does not resemble a DSN URI
    if "://" not in text:
        return False, None
    scheme = text.split("://")[0]
    if scheme not in ("mysql", "mysqlx", "tcp", "socket", "ssh"):
        return False, scheme
    else:
        return True, None

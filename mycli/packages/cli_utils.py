from __future__ import annotations


def is_valid_connection_scheme(text: str) -> tuple[bool, str | None]:
    # exit early if the text does not resemble a DSN URI
    if "://" not in text:
        return False, None
    scheme = text.split("://")[0]
    if scheme not in ("mysql", "mysqlx", "tcp", "socket", "ssh"):
        return False, scheme
    else:
        return True, None

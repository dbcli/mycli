def server_date(sqlexecute, quoted: bool = False) -> str:
    server_date_str = sqlexecute.now().strftime('%Y-%m-%d')
    if quoted:
        return f"'{server_date_str}'"
    else:
        return server_date_str


def server_datetime(sqlexecute, quoted: bool = False) -> str:
    server_datetime_str = sqlexecute.now().strftime('%Y-%m-%d %H:%M:%S')
    if quoted:
        return f"'{server_datetime_str}'"
    else:
        return server_datetime_str

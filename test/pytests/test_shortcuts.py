import datetime
from typing import Any, cast

from mycli.packages import shortcuts


class FakeSQLExecute:
    def __init__(self, now_value: datetime.datetime) -> None:
        self.now_value = now_value

    def now(self) -> datetime.datetime:
        return self.now_value


def test_server_date_returns_quoted_and_unquoted_values() -> None:
    sqlexecute = FakeSQLExecute(datetime.datetime(2026, 4, 3, 14, 5, 6))

    assert shortcuts.server_date(cast(Any, sqlexecute)) == '2026-04-03'
    assert shortcuts.server_date(cast(Any, sqlexecute), quoted=True) == "'2026-04-03'"


def test_server_datetime_returns_quoted_and_unquoted_values() -> None:
    sqlexecute = FakeSQLExecute(datetime.datetime(2026, 4, 3, 14, 5, 6))

    assert shortcuts.server_datetime(cast(Any, sqlexecute)) == '2026-04-03 14:05:06'
    assert shortcuts.server_datetime(cast(Any, sqlexecute), quoted=True) == "'2026-04-03 14:05:06'"

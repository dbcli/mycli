from dataclasses import dataclass

from pymysql.cursors import Cursor


@dataclass
class SQLResult:
    preamble: str | None = None
    header: list[str] | str | None = None
    rows: Cursor | list[tuple] | None = None
    postamble: str | None = None
    status: str | None = None
    command: dict[str, str | float] | None = None

    def __iter__(self):
        return self

    def __str__(self):
        return f"{self.preamble}, {self.header}, {self.rows}, {self.postamble}, {self.status}, {self.command}"

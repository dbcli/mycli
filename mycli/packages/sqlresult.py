from dataclasses import dataclass

from pymysql.cursors import Cursor


@dataclass
class SQLResult:
    title: str | None = None
    cursor: Cursor | list[tuple] | None = None
    headers: list[str] | str | None = None
    status: str | None = None

    def __iter__(self):
        return iter((self.title, self.cursor, self.headers, self.status))

    def __str__(self):
        return f"{self.title}, {self.cursor}, {self.headers}, {self.status}"

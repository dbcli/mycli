from dataclasses import dataclass

from pymysql.cursors import Cursor


@dataclass
class SQLResult:
    title: str | None = None
    results: Cursor | list[tuple] | None = None
    headers: list[str] | str | None = None
    status: str | None = None
    command: dict[str, str | float] | None = None

    def get_output(self):
        return self.title, self.results, self.headers, self.status

    def __iter__(self):
        return self

    def __str__(self):
        return f"{self.title}, {self.results}, {self.headers}, {self.status}, {self.command}"

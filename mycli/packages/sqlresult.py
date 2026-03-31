from dataclasses import dataclass
from functools import cached_property

from prompt_toolkit.formatted_text import FormattedText, to_plain_text
from pymysql.cursors import Cursor


@dataclass
class SQLResult:
    preamble: str | None = None
    header: list[str] | str | None = None
    rows: Cursor | list[tuple] | None = None
    postamble: str | None = None
    status: str | FormattedText | None = None
    command: dict[str, str | float] | None = None

    def __str__(self):
        return f"{self.preamble}, {self.header}, {self.rows}, {self.postamble}, {self.status}, {self.command}"

    @cached_property
    def status_plain(self):
        if self.status is None:
            return None
        return to_plain_text(self.status)

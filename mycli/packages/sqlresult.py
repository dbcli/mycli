from dataclasses import dataclass
from functools import cached_property

from prompt_toolkit.formatted_text import FormattedText, to_plain_text
from pymysql.cursors import Cursor

from mycli.types import ImageProtocol


@dataclass
class SQLResult:
    preamble: str | None = None
    header: list[str] | str | None = None
    rows: Cursor | list[tuple] | None = None
    postamble: str | None = None
    status: str | FormattedText | None = None
    command: dict[str, str | float] | None = None
    image: bytes | None = None
    image_protocol: ImageProtocol = 'none'

    def __str__(self):
        image = f'<{len(self.image)} bytes>' if self.image is not None else None
        return (
            f"{self.preamble}, {self.header}, {self.rows}, {self.postamble}, {self.status}, {self.command}, {image}, {self.image_protocol}"
        )

    @cached_property
    def status_plain(self):
        if self.status is None:
            return None
        return to_plain_text(self.status)

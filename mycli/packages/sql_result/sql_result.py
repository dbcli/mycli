from collections.abc import Callable
from dataclasses import dataclass, field
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
    is_error: bool = False
    _status_finalizer: Callable[[], FormattedText] | None = field(default=None, repr=False, compare=False)

    def finalize_status(self) -> None:
        if self._status_finalizer is not None:
            self.status = self._status_finalizer()
            self.__dict__.pop('status_plain', None)
            self._status_finalizer = None

    def __str__(self):
        image = f'<{len(self.image)} bytes>' if self.image is not None else None
        return (
            f"{self.preamble}, {self.header}, {self.rows}, {self.postamble}, {self.status}, {self.command}, "
            f"{image}, {self.image_protocol}, {self.is_error}"
        )

    @cached_property
    def status_plain(self):
        if self.status is None:
            return None
        return to_plain_text(self.status)

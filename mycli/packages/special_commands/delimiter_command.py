from __future__ import annotations

import re
from typing import Generator

import sqlparse

from mycli.packages.sql_result.sql_result import SQLResult

sqlparse.engine.grouping.MAX_GROUPING_DEPTH = None  # type: ignore[assignment]
sqlparse.engine.grouping.MAX_GROUPING_TOKENS = None  # type: ignore[assignment]

DELIMITER_COMMAND_RE = re.compile(r'''\s*/?delimiter\s+((['"]).*?\2|\S+)''', re.IGNORECASE)


class DelimiterCommand:
    def __init__(self) -> None:
        self._delimiter = ";"

    def _split(self, sql: str) -> list[str]:
        """Temporary workaround until sqlparse.split() learns about custom
        delimiters."""

        placeholder = "\ufffc"  # unicode object replacement character
        delimiter_placeholder = "\ufffb"  # interlinear annotation terminator

        if self._delimiter == ";":
            return sqlparse.split(sql)

        # We must find strings that original sql does not contain.
        # Most likely, our placeholders are enough, but if not, keep looking
        while placeholder in sql:
            placeholder += placeholder[0]
        while delimiter_placeholder in sql:
            delimiter_placeholder += delimiter_placeholder[0]
        # Replace the delimiter first, since it may contain a semicolon, e.g. ";;".
        sql = sql.replace(self._delimiter, delimiter_placeholder)
        sql = sql.replace(";", placeholder)
        sql = sql.replace(delimiter_placeholder, ";")

        split = sqlparse.split(sql)

        return [stmt.replace(";", self._delimiter).replace(placeholder, ";") for stmt in split]

    def queries_iter(self, input_str: str) -> Generator[str, None, None]:
        """Iterate over queries in the input string."""

        # Splitting would cut short a new delimiter containing the current
        # one, such as ";;", so yield a leading DELIMITER command whole.
        command = DELIMITER_COMMAND_RE.match(input_str)
        if command and self._delimiter in command.group(1):
            yield command.group(0).strip()
            input_str = input_str[command.end() :]
            if not input_str.strip():
                return

        queries = self._split(input_str)
        while queries:
            for sql in queries:
                delimiter = self._delimiter
                sql = queries.pop(0)
                if sql.endswith(delimiter):
                    trailing_delimiter = True
                    sql = sql[: -len(delimiter)]
                else:
                    trailing_delimiter = False

                yield sql

                # if the delimiter was changed by the last command,
                # re-split everything, and if we previously stripped
                # the delimiter, append it to the end
                if self._delimiter != delimiter:
                    combined_statement = " ".join([sql] + queries)
                    if trailing_delimiter:
                        combined_statement += delimiter
                    queries = self._split(combined_statement)[1:]

    def set(self, arg: str, **_) -> list[SQLResult]:
        """Change delimiter.

        Since `arg` is everything that follows the DELIMITER token
        after sqlparse (it may include other statements separated by
        the new delimiter), we want to set the delimiter to the first
        word of it.

        """
        # A quoted delimiter, such as ";;", is taken without its quotes.
        match = arg and re.match(r"""\s*(?:(['"])(.*?)\1|(\S+))""", arg)
        delimiter = match and (match.group(2) if match.group(1) else match.group(3))
        if not delimiter:
            message = "Missing required argument, delimiter"
            return [SQLResult(status=message)]

        if delimiter.lower() == "delimiter":
            return [SQLResult(status='Invalid delimiter "delimiter"')]

        self._delimiter = delimiter
        return [SQLResult(status=f'Changed delimiter to {delimiter}')]

    @property
    def current(self) -> str:
        return self._delimiter

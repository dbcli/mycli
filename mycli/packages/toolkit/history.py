import os
from typing import Union

from prompt_toolkit.history import FileHistory

_StrOrBytesPath = Union[str, bytes, os.PathLike]


class FileHistoryWithTimestamp(FileHistory):
    """
    :class:`.FileHistory` class that stores all strings in a file with timestamp.
    """

    def __init__(self, filename: _StrOrBytesPath) -> None:
        self.filename = filename
        super().__init__(filename)

    def load_history_with_timestamp(self) -> list[tuple[str, str]]:
        """
        Load history entries along with their timestamps.

        Returns:
            list[tuple[str, str]]: A list of tuples where each tuple contains
                                   a history entry and its corresponding timestamp.
        """
        history_with_timestamp: list[tuple[str, str]] = []
        lines: list[str] = []
        timestamp: str = ""

        def add() -> None:
            if lines:
                # Join and drop trailing newline.
                string = "".join(lines)[:-1]
                history_with_timestamp.append((string, timestamp))

        if os.path.exists(self.filename):
            with open(self.filename, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("#"):
                        # Extract timestamp
                        timestamp = line[2:].strip()
                    elif line.startswith("+"):
                        lines.append(line[1:])
                    else:
                        add()
                        lines = []

                add()

        return list(reversed(history_with_timestamp))

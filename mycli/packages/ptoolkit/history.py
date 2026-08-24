from collections import defaultdict
from collections.abc import Iterable, Mapping
from functools import lru_cache
from itertools import islice
import logging
import os
import re
import threading

from prompt_toolkit.history import FileHistory
from sqlglot import Token, TokenType, tokenize
from sqlglot.errors import TokenError

from mycli.packages.sql_utils import is_password_change

logger = logging.getLogger(__name__)

_StrOrBytesPath = str | bytes | os.PathLike[str] | os.PathLike[bytes]
FRECENCY_HISTORY_ENTRIES = 1000
FRECENCY_REFRESH_INTERVAL = 50
_FRECENCY_LITERAL_TYPES = frozenset({
    TokenType.STRING,
    TokenType.NUMBER,
    TokenType.BIT_STRING,
    TokenType.HEX_STRING,
    TokenType.BYTE_STRING,
    TokenType.NATIONAL_STRING,
    TokenType.RAW_STRING,
    TokenType.HEREDOC_STRING,
    TokenType.UNICODE_STRING,
})
_FRECENCY_WORD_PATTERN = re.compile(r'^[^\W\d][\w$]*(?:\s+[^\W\d][\w$]*)*$')


def _normalize_frecency_token(token: Token) -> str | None:
    if token.token_type in _FRECENCY_LITERAL_TYPES:
        return None
    if token.token_type != TokenType.IDENTIFIER and not _FRECENCY_WORD_PATTERN.fullmatch(token.text):
        return None
    return token.text.casefold() or None


def _calculate_frecency(
    entries: Iterable[str],
    history_entries: int = FRECENCY_HISTORY_ENTRIES,
) -> dict[str, float]:
    frecency: defaultdict[str, float] = defaultdict(float)
    for position, entry in enumerate(islice(entries, max(0, history_entries))):
        weight = 1 / (position + 1)
        try:
            tokens = tokenize(entry, dialect='mysql')
        except TokenError:
            continue
        for token in tokens:
            if normalized := _normalize_frecency_token(token):
                frecency[normalized] += weight
    return dict(frecency)


@lru_cache(maxsize=8192)
def _frecency_tokens(text: str) -> tuple[str, ...]:
    """Tokenize a completion candidate. Cached: candidates repeat on every keystroke."""
    try:
        tokens = tokenize(text, dialect='mysql')
    except TokenError:
        return ()
    return tuple(normalized for token in tokens if (normalized := _normalize_frecency_token(token)))


def frecency_score(text: str, frecency: Mapping[str, float]) -> float:
    normalized_tokens = _frecency_tokens(text)
    if not normalized_tokens:
        return 0.0
    return sum(frecency.get(token, 0.0) for token in normalized_tokens) / len(normalized_tokens)


class FileHistoryWithTimestamp(FileHistory):
    """
    :class:`.FileHistory` class that stores all strings in a file with timestamp.
    """

    def __init__(
        self,
        filename: _StrOrBytesPath,
        frecency_history_entries: int = FRECENCY_HISTORY_ENTRIES,
        frecency_refresh_interval: int = FRECENCY_REFRESH_INTERVAL,
    ) -> None:
        self.filename = filename
        super().__init__(filename)
        self.frecency_history_entries = max(0, frecency_history_entries)
        self.frecency_refresh_interval = max(0, frecency_refresh_interval)
        self._frecency: dict[str, float] = {}
        self._frecency_lock = threading.Lock()
        self._frecency_generation = 0
        self._frecency_thread: threading.Thread | None = None
        self._frecency_entries_since_refresh = 0
        if self.frecency_history_entries:
            self._request_frecency_refresh()

    @property
    def frecency(self) -> dict[str, float]:
        with self._frecency_lock:
            return self._frecency

    def _request_frecency_refresh(self) -> None:
        with self._frecency_lock:
            self._frecency_generation += 1
            if self._frecency_thread is not None:
                return
            thread = threading.Thread(target=self._refresh_frecency, name='frecency_refresh', daemon=True)
            self._frecency_thread = thread

        try:
            thread.start()
        except Exception:
            with self._frecency_lock:
                if self._frecency_thread is thread:
                    self._frecency_thread = None
            logger.exception('Failed to start history frecency calculation.')

    def refresh_frecency(self) -> None:
        """Request an immediate background refresh of history frecency."""
        if not self.frecency_history_entries:
            return
        with self._frecency_lock:
            self._frecency_entries_since_refresh = 0
        self._request_frecency_refresh()

    def _refresh_frecency(self) -> None:
        while True:
            with self._frecency_lock:
                generation = self._frecency_generation

            try:
                frecency = _calculate_frecency(self.load_history_strings(), self.frecency_history_entries)
            except Exception:
                logger.exception('Failed to calculate history frecency.')
                with self._frecency_lock:
                    if self._frecency_generation != generation:
                        continue
                    self._frecency_thread = None
                return

            with self._frecency_lock:
                self._frecency = frecency
                if self._frecency_generation == generation:
                    self._frecency_thread = None
                    return

    def append_string(self, string: str) -> None:
        "Add string to the history."
        self._loaded_strings.insert(0, string)
        if is_password_change(string):
            return
        self.store_string(string)
        if not self.frecency_history_entries or not self.frecency_refresh_interval:
            return
        with self._frecency_lock:
            self._frecency_entries_since_refresh += 1
            refresh = self._frecency_entries_since_refresh >= self.frecency_refresh_interval
            if refresh:
                self._frecency_entries_since_refresh = 0
        if refresh:
            self._request_frecency_refresh()

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

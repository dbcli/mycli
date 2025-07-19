from __future__ import annotations

import re
from shutil import which

from prompt_toolkit import search
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from pyfzf import FzfPrompt

from mycli.packages.toolkit.history import FileHistoryWithTimestamp


class Fzf(FzfPrompt):
    def __init__(self):
        self.executable = which("fzf")
        if self.executable:
            super().__init__()

    def is_available(self) -> bool:
        return self.executable is not None


def search_history(event: KeyPressEvent, incremental: bool = False) -> None:
    buffer = event.current_buffer
    history = buffer.history

    fzf = Fzf()

    if incremental or not fzf.is_available() or not isinstance(history, FileHistoryWithTimestamp):
        # Fallback to default reverse incremental search
        search.start_search(direction=search.SearchDirection.BACKWARD)
        return

    history_items_with_timestamp = history.load_history_with_timestamp()

    formatted_history_items = []
    original_history_items = []
    seen = {}
    for item, timestamp in history_items_with_timestamp:
        formatted_item = re.sub(r'\s+', ' ', item)
        timestamp = timestamp.split(".")[0] if "." in timestamp else timestamp
        if formatted_item in seen:
            continue
        seen[formatted_item] = True
        formatted_history_items.append(f"{timestamp}  {formatted_item}")
        original_history_items.append(item)

    result = fzf.prompt(
        formatted_history_items,
        fzf_options="--scheme=history --tiebreak=index --bind ctrl-r:up,alt-r:up --preview-window=down:wrap --preview=\"printf '%s' {}\"",
    )

    if result:
        selected_index = formatted_history_items.index(result[0])
        buffer.text = original_history_items[selected_index]
        buffer.cursor_position = len(buffer.text)

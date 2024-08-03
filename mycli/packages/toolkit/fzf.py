from shutil import which

from pyfzf import FzfPrompt
from prompt_toolkit import search
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

from .history import FileHistoryWithTimestamp


class Fzf(FzfPrompt):
    def __init__(self):
        self.executable = which("fzf")
        if self.executable:
            super().__init__()

    def is_available(self) -> bool:
        return self.executable is not None


def search_history(event: KeyPressEvent):
    buffer = event.current_buffer
    history = buffer.history

    fzf = Fzf()

    if fzf.is_available() and isinstance(history, FileHistoryWithTimestamp):
        history_items_with_timestamp = history.load_history_with_timestamp()

        formatted_history_items = []
        original_history_items = []
        for item, timestamp in history_items_with_timestamp:
            formatted_item = item.replace('\n', ' ')
            timestamp = timestamp.split(".")[0] if "." in timestamp else timestamp
            formatted_history_items.append(f"{timestamp}  {formatted_item}")
            original_history_items.append(item)

        result = fzf.prompt(formatted_history_items, fzf_options="--tiebreak=index")

        if result:
            selected_index = formatted_history_items.index(result[0])
            buffer.text = original_history_items[selected_index]
            buffer.cursor_position = len(buffer.text)
    else:
        # Fallback to default reverse incremental search
        search.start_search(direction=search.SearchDirection.BACKWARD)

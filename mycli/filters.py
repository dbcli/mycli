from prompt_toolkit.filters import Condition
from prompt_toolkit.application import get_app


@Condition
def has_selected_completion():
    """Enable when the current buffer has a selected completion."""

    complete_state = get_app().current_buffer.complete_state
    return (complete_state is not None and
             complete_state.current_completion is not None)

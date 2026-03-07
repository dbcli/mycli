import re

from cli_helpers.utils import strip_ansi


def sanitize_terminal_title(title: str) -> str:
    sanitized = strip_ansi(title)
    sanitized = sanitized.replace('\n', ' ')
    sanitized = re.sub('[\x00-\x1f\x7f]', '', sanitized)
    return sanitized

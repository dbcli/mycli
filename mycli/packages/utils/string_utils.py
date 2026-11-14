import ipaddress
import re

from cli_helpers.utils import strip_ansi
from prompt_toolkit.formatted_text import (
    FormattedText,
    to_plain_text,
)


def sanitize_terminal_title(title: FormattedText) -> str:
    sanitized = to_plain_text(title)
    sanitized = strip_ansi(sanitized)
    sanitized = sanitized.replace('\n', ' ')
    sanitized = re.sub('[\x00-\x1f\x7f]', '', sanitized)
    return sanitized


def bracket_ipv6_literal(host: str) -> str:
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(ip_obj, ipaddress.IPv6Address) and not host.startswith('['):
        return f'[{host}]'
    return host

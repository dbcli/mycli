"""Platform and Python version compatibility support."""

from importlib import import_module
import sys

WIN: bool = sys.platform in ("win32", "cygwin")


def _is_win32() -> bool:
    return sys.platform == 'win32'


def is_windows_console(output: object | None) -> bool:
    """Return whether output uses a native Windows console backend."""
    if not _is_win32() or output is None:
        return False

    output_types = tuple(
        getattr(import_module(module_name), class_name)
        for module_name, class_name in (
            ('prompt_toolkit.output.conemu', 'ConEmuOutput'),
            ('prompt_toolkit.output.win32', 'Win32Output'),
            ('prompt_toolkit.output.windows10', 'Windows10_Output'),
        )
    )

    return isinstance(output, output_types)

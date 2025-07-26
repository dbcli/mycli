from __future__ import annotations

from typing import Callable

__all__: list[str] = []


def export(defn: Callable):
    """Decorator to explicitly mark functions that are exposed in a lib."""
    globals()[defn.__name__] = defn
    __all__.append(defn.__name__)
    return defn


from mycli.packages.special import (
    dbcommands,  # noqa: E402 F401
    iocommands,  # noqa: E402 F401
)

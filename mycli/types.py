from collections import namedtuple
from typing import Literal

# Query tuples are used for maintaining history
Query = namedtuple("Query", ["query", "successful", "mutating"])

OutputMode = Literal[
    'explorer',
    'expanded',
    'tabular',
]

ImageProtocol = Literal[
    'none',
    'iterm2',
    'kitty',
]

from __future__ import annotations

from importlib import resources

import mycli as mycli_package

COMPLETION_PATHS = {
    'bash': ('resources', 'completions', 'bash', 'mycli'),
    'zsh': ('resources', 'completions', 'zsh', '_mycli'),
    'fish': ('resources', 'completions', 'fish', 'mycli.fish'),
}


def main_completions(shell: str) -> None:
    completion_path = resources.files(mycli_package).joinpath(*COMPLETION_PATHS[shell])
    print(completion_path.read_text(), end='')

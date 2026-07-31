from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

ZSH = shutil.which('zsh')
COMPLETION_SCRIPT = Path(__file__).parents[2] / 'mycli' / 'resources' / 'completions' / 'zsh' / '_mycli'


@pytest.mark.skipif(ZSH is None, reason='zsh is not installed')
def test_zsh_completion_lists_dsn_aliases_in_supported_contexts(tmp_path: Path) -> None:
    assert ZSH is not None
    executable = tmp_path / 'mycli'
    executable.write_text(
        '''#!/bin/sh
if [ "${_MYCLI_COMPLETE:-}" = 'zsh_complete' ]; then
    printf 'click\\n' >> "$MYCLI_LOG"
    exit 0
fi
if [ "$1" = '--list-dsn' ]; then
    printf 'list-dsn\\n' >> "$MYCLI_LOG"
    printf 'prod\\nstaging\\n'
fi
''',
        encoding='utf-8',
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    log_path = tmp_path / 'calls.log'
    environment = {
        **os.environ,
        'COMPLETION_SCRIPT': str(COMPLETION_SCRIPT),
        'MYCLI_LOG': str(log_path),
        'PATH': f'{tmp_path}{os.pathsep}{os.environ["PATH"]}',
    }

    result = subprocess.run(
        [ZSH, '-fc', ZSH_COMPLETION_HARNESS],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.stdout.splitlines() == [
        'prod,staging||0',
        'prod||0',
        'prod,staging||0',
        'prod,staging||0',
        '-dprod|-P -d|0',
        '--dsn=prod|-P --dsn=|0',
        '||0',
        '||0',
    ]
    assert log_path.read_text(encoding='utf-8').splitlines().count('list-dsn') == 6


ZSH_COMPLETION_HARNESS = r'''
compdef() { :; }
_describe() { :; }
_path_files() { :; }

typeset -a captured compset_calls
typeset PREFIX IPREFIX used_unambiguous
compadd() {
    local array_name=''
    local candidate

    while (( $# )); do
        case "$1" in
            -U)
                used_unambiguous=1
                ;;
            -a)
                array_name="$2"
                shift
                ;;
        esac
        shift
    done

    for candidate in "${(@P)array_name}"; do
        [[ "$candidate" == "$PREFIX"* ]] && captured+=("$IPREFIX$candidate")
    done
}
compset() {
    compset_calls+=("$*")
    IPREFIX="$2"
    PREFIX="${PREFIX#$IPREFIX}"
}

source "$COMPLETION_SCRIPT"

run_completion() {
    captured=()
    compset_calls=()
    words=("$@")
    CURRENT=$#
    PREFIX="${words[CURRENT]}"
    IPREFIX=''
    used_unambiguous=0
    _mycli_completion
    print -r -- "${(j:,:)captured}|${(j:,:)compset_calls}|$used_unambiguous"
}

run_completion mycli ''
run_completion mycli pro
run_completion mycli -d ''
run_completion mycli --dsn ''
run_completion mycli -dpro
run_completion mycli --dsn=pro
run_completion mycli --host ''
run_completion mycli --host
'''

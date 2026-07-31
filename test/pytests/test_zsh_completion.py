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
    if [ "$COMP_WORDS" = 'mycli --completions ba' ]; then
        printf 'plain\\nbash\\n_\\n'
    fi
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
        'prod,staging||0|',
        'prod||0|',
        'bash||1|',
        'prod,staging||0|',
        'prod,staging||0|',
        '-dprod|-P -d|0|',
        '--dsn=prod|-P --dsn=|0|',
        '||0|',
        '||0|',
        '||0|-f',
        '||0|-f',
        '|-P --socket=|0|-f',
        '|-P -S|0|-f',
        'prod,staging||0|',
        'prod,staging||0|',
        '-Dprod|-P -D|0|',
        '--database=prod|-P --database=|0|',
        'prod||0|',
        'staging||0|',
        'prod||0|',
        '||0|',
        '||0|',
        'prod||0|',
        '||0|',
    ]
    assert log_path.read_text(encoding='utf-8').splitlines().count('list-dsn') == 14


ZSH_COMPLETION_HARNESS = r'''
compdef() { :; }
_describe() { :; }
_path_files() {
    path_file_calls+=("$*")
}

typeset -a captured compset_calls path_file_calls
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
    path_file_calls=()
    words=("$@")
    CURRENT=$#
    PREFIX="${words[CURRENT]}"
    IPREFIX=''
    used_unambiguous=0
    _mycli_completion
    print -r -- "${(j:,:)captured}|${(j:,:)compset_calls}|$used_unambiguous|${(j:,:)path_file_calls}"
}

run_completion mycli ''
run_completion mycli pro
run_completion mycli --completions ba
run_completion mycli -d ''
run_completion mycli --dsn ''
run_completion mycli -dpro
run_completion mycli --dsn=pro
run_completion mycli --host ''
run_completion mycli --host
run_completion mycli --socket ''
run_completion mycli -S ''
run_completion mycli --socket=/tmp/mysql
run_completion mycli -S/tmp/mysql
run_completion mycli -D ''
run_completion mycli --database ''
run_completion mycli -Dpro
run_completion mycli --database=pro
run_completion mycli --host db pro
run_completion mycli --ssl-mode auto sta
run_completion mycli -- prod
run_completion mycli --host pro
run_completion mycli --ssl-mode sta
run_completion mycli -vP 3306 pro
run_completion mycli prod --host db other
'''

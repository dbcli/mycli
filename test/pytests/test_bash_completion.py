from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest


def find_supported_bash() -> str | None:
    candidates = [
        os.environ.get('MYCLI_TEST_BASH'),
        '/opt/homebrew/bin/bash',
        '/opt/local/bin/bash',
        '/usr/local/bin/bash',
        shutil.which('bash5'),
        shutil.which('bash4'),
        shutil.which('bash'),
    ]
    for candidate in dict.fromkeys(candidates):
        if candidate is None or not Path(candidate).is_file():
            continue
        version_check = subprocess.run(
            # completions mostly work with bash 3 but some tests would fail to match
            [candidate, '-c', '(( BASH_VERSINFO[0] > 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 4) ))'],
            check=False,
        )
        if version_check.returncode == 0:
            return candidate
    return None


BASH = find_supported_bash()
COMPLETION_SCRIPT = Path(__file__).parents[2] / 'mycli' / 'resources' / 'completions' / 'bash' / 'mycli'


@pytest.mark.skipif(BASH is None, reason='Bash 4.4 or newer is not installed')
def test_bash_completion_matches_mycli_completion_behavior(tmp_path: Path) -> None:
    assert BASH is not None
    executable = tmp_path / 'mycli'
    executable.write_text(
        '''#!/bin/sh
if [ "${_MYCLI_COMPLETE:-}" = 'bash_complete' ]; then
    printf 'click\\n' >> "$MYCLI_LOG"
    if [ "$COMP_WORDS" = 'mycli --s' ]; then
        printf 'plain,--socket\\nplain,--ssl-mode\\n'
    elif [ "$COMP_WORDS" = 'mycli --completions ba' ]; then
        printf 'plain,bash\\n'
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
    (tmp_path / 'mysql.sock').touch()
    (tmp_path / 'space socket.sock').touch()
    (tmp_path / 'batch.sql').touch()
    log_path = tmp_path / 'calls.log'
    environment = {
        **os.environ,
        'COMPLETION_SCRIPT': str(COMPLETION_SCRIPT),
        'MYCLI_LOG': str(log_path),
        'PATH': f'{tmp_path}{os.pathsep}{os.environ.get("PATH", "")}',
    }

    result = subprocess.run(
        [BASH, '--noprofile', '--norc', '-c', BASH_COMPLETION_HARNESS],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
    )

    assert result.stdout.splitlines() == [
        'complete -F _mycli_completion mycli',
        'generic|reply<--socket><--ssl-mode>|compopt',
        'completions|reply<bash>|compopt',
        'bare|reply<prod>|compopt',
        'dsn-separate|reply<prod><staging>|compopt',
        'dsn-attached|reply<-dprod>|compopt',
        'database-separate|reply<staging>|compopt',
        'database-attached|reply<--database=prod>|compopt',
        'after-host|reply<prod>|compopt',
        'host-value|reply|compopt',
        'after-double-dash|reply<staging>|compopt',
        'after-positional|reply|compopt',
        'clustered-option|reply<prod>|compopt',
        'socket-separate|reply<mysql.sock>|compopt<-o filenames>',
        'socket-attached|reply<--socket=space socket.sock>|compopt<-o filenames>',
        'socket-short-attached|reply<-Smysql.sock>|compopt<-o filenames>',
        'checkpoint-separate|reply<batch.sql>|compopt<-o filenames>',
        'batch-attached|reply<--batch=batch.sql>|compopt<-o filenames>',
    ]
    assert log_path.read_text(encoding='utf-8').splitlines().count('list-dsn') == 8


BASH_COMPLETION_HARNESS = r'''
compopt() {
    compopt_calls+=("$*")
}

source "$COMPLETION_SCRIPT"
complete -p mycli

run_completion() {
    local label="$1"
    local reply
    local call
    shift
    COMP_WORDS=("$@")
    COMP_CWORD=$((${#COMP_WORDS[@]} - 1))
    compopt_calls=()
    _mycli_completion

    printf '%s|reply' "$label"
    for reply in "${COMPREPLY[@]}"; do
        printf '<%s>' "$reply"
    done
    printf '|compopt'
    for call in "${compopt_calls[@]}"; do
        printf '<%s>' "$call"
    done
    printf '\n'
}

run_completion generic mycli --s
run_completion completions mycli --completions ba
run_completion bare mycli pro
run_completion dsn-separate mycli -d ''
run_completion dsn-attached mycli -dpro
run_completion database-separate mycli --database sta
run_completion database-attached mycli --database=pro
run_completion after-host mycli --host db pro
run_completion host-value mycli --host pro
run_completion after-double-dash mycli -- sta
run_completion after-positional mycli prod --host db other
run_completion clustered-option mycli -vP 3306 pro
run_completion socket-separate mycli --socket mysql
run_completion socket-attached mycli '--socket=space'
run_completion socket-short-attached mycli -Smysql
run_completion checkpoint-separate mycli --checkpoint batch
run_completion batch-attached mycli --batch=bat
'''

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

FISH = shutil.which('fish')
COMPLETION_SCRIPT = Path(__file__).parents[2] / 'mycli' / 'resources' / 'completions' / 'fish' / 'mycli.fish'


@pytest.mark.skipif(FISH is None, reason='Fish is not installed')
def test_fish_completion_matches_mycli_completion_behavior(tmp_path: Path) -> None:
    assert FISH is not None
    executable = tmp_path / 'mycli'
    executable.write_text(
        '''#!/bin/sh
if [ "${_MYCLI_COMPLETE:-}" = 'fish_complete' ]; then
    printf 'click\n' >> "$MYCLI_LOG"
    if [ "$COMP_CWORD" = '--s' ]; then
        printf 'plain,--socket\tSocket file\nplain,--ssl-mode\tTLS mode\n'
    elif [ "$COMP_CWORD" = 'ba' ]; then
        printf 'plain,bash\n'
    fi
    exit 0
fi
if [ "$1" = '--list-dsn' ]; then
    printf 'list-dsn\n' >> "$MYCLI_LOG"
    printf 'prod\nstaging\n'
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
        [FISH, '--no-config', '-c', FISH_COMPLETION_HARNESS],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
    )

    assert result.stdout.splitlines() == [
        'generic|--socket\tSocket file|--ssl-mode\tTLS mode',
        'completions|bash',
        'bare|prod',
        'dsn-separate|prod|staging',
        'dsn-long-separate|prod',
        'dsn-attached|-dprod',
        'dsn-long-attached|--dsn=prod',
        'database-separate|staging',
        'database-short-separate|staging',
        'database-short-attached|-Dprod',
        'database-attached|--database=prod',
        'after-host|prod',
        'host-value',
        'after-double-dash|staging',
        'after-positional',
        'clustered-option|prod',
        'socket-separate|mysql.sock',
        'socket-attached|--socket=space socket.sock',
        'socket-short-separate|space socket.sock',
        'socket-short-attached|-Smysql.sock',
        'checkpoint-separate|batch.sql',
        'checkpoint-attached|--checkpoint=batch.sql',
        'batch-separate|batch.sql',
        'batch-attached|--batch=batch.sql',
    ]
    assert log_path.read_text(encoding='utf-8').splitlines().count('list-dsn') == 12


FISH_COMPLETION_HARNESS = r'''
complete --erase --command mycli
source "$COMPLETION_SCRIPT"

function run_completion --argument-names label command
    printf '%s' "$label"
    for candidate in (complete -C "$command")
        printf '|%s' "$candidate"
    end
    printf '\n'
end

run_completion generic 'mycli --s'
run_completion completions 'mycli --completions ba'
run_completion bare 'mycli pro'
run_completion dsn-separate 'mycli -d '
run_completion dsn-long-separate 'mycli --dsn pro'
run_completion dsn-attached 'mycli -dpro'
run_completion dsn-long-attached 'mycli --dsn=pro'
run_completion database-separate 'mycli --database sta'
run_completion database-short-separate 'mycli -D sta'
run_completion database-short-attached 'mycli -Dpro'
run_completion database-attached 'mycli --database=pro'
run_completion after-host 'mycli --host db pro'
run_completion host-value 'mycli --host pro'
run_completion after-double-dash 'mycli -- sta'
run_completion after-positional 'mycli prod --host db other'
run_completion clustered-option 'mycli -vP 3306 pro'
run_completion socket-separate 'mycli --socket mysql'
run_completion socket-attached 'mycli --socket=space'
run_completion socket-short-separate 'mycli -S space'
run_completion socket-short-attached 'mycli -Smysql'
run_completion checkpoint-separate 'mycli --checkpoint batch'
run_completion checkpoint-attached 'mycli --checkpoint=bat'
run_completion batch-separate 'mycli --batch batch'
run_completion batch-attached 'mycli --batch=bat'
'''

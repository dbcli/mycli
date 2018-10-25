# -*- coding: utf-8
from __future__ import unicode_literals

import re
import pexpect
import sys
import textwrap

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


def expect_exact(context, expected, timeout):
    timedout = False
    try:
        context.cli.expect_exact(expected, timeout=timeout)
    except pexpect.exceptions.TIMEOUT:
        timedout = True
    if timedout:
        # Strip color codes out of the output.
        actual = re.sub(r'\x1b\[([0-9A-Za-z;?])+[m|K]?',
                        '', context.cli.before)
        raise Exception(
            textwrap.dedent('''\
                Expected:
                ---
                {0!r}
                ---
                Actual:
                ---
                {1!r}
                ---
                Full log:
                ---
                {2!r}
                ---
            ''').format(
                expected,
                actual,
                context.logfile.getvalue()
            )
        )


def expect_pager(context, expected, timeout):
    expect_exact(context, "{0}\r\n{1}{0}\r\n".format(
        context.conf['pager_boundary'], expected), timeout=timeout)


def run_cli(context, run_args=None):
    """Run the process using pexpect."""
    run_args = run_args or []
    if context.conf.get('host', None):
        run_args.extend(('-h', context.conf['host']))
    if context.conf.get('user', None):
        run_args.extend(('-u', context.conf['user']))
    if context.conf.get('pass', None):
        run_args.extend(('-p', context.conf['pass']))
    if context.conf.get('dbname', None):
        run_args.extend(('-D', context.conf['dbname']))
    if context.conf.get('defaults-file', None):
        run_args.extend(('--defaults-file', context.conf['defaults-file']))
    if context.conf.get('myclirc', None):
        run_args.extend(('--myclirc', context.conf['myclirc']))
    try:
        cli_cmd = context.conf['cli_command']
    except KeyError:
        cli_cmd = (
            '{0!s} -c "'
            'import coverage ; '
            'coverage.process_startup(); '
            'import mycli.main; '
            'mycli.main.cli()'
            '"'
        ).format(sys.executable)

    cmd_parts = [cli_cmd] + run_args
    cmd = ' '.join(cmd_parts)
    context.cli = pexpect.spawnu(cmd, cwd=context.package_root)
    context.logfile = StringIO()
    context.cli.logfile = context.logfile
    context.exit_sent = False
    context.currentdb = context.conf['dbname']


def wait_prompt(context):
    """Make sure prompt is displayed."""
    user = context.conf['user']
    host = context.conf['host']
    dbname = context.currentdb
    expect_exact(context, '{0}@{1}:{2}> '.format(
        user, host, dbname), timeout=5)
    context.atprompt = True

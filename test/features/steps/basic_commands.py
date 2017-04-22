# -*- coding: utf-8
"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""
from __future__ import unicode_literals

import pexpect

from behave import when
import wrappers


@when('we run dbcli')
def step_run_cli(context):
    """Run the process using pexpect."""
    run_args = []
    if context.conf.get('host', None):
        run_args.extend(('-h', context.conf['host']))
    if context.conf.get('user', None):
        run_args.extend(('-u', context.conf['user']))
    if context.conf.get('pass', None):
        run_args.extend(('-p', context.conf['pass']))
    if context.conf.get('dbname', None):
        run_args.extend(('-D', context.conf['dbname']))
    cli_cmd = context.conf.get('cli_command', None) or sys.executable + \
        ' -c "import coverage ; coverage.process_startup(); import mycli.main; mycli.main.cli()"'

    cmd_parts = [cli_cmd] + run_args
    cmd = ' '.join(cmd_parts)
    context.cli = pexpect.spawnu(cmd, cwd='..')
    context.exit_sent = False


@when('we wait for prompt')
def step_wait_prompt(context):
    """Make sure prompt is displayed."""
    user = context.conf['user']
    host = context.conf['host']
    dbname = context.conf['dbname']
    wrappers.expect_exact(context, 'mysql {0}@{1}:{2}> '.format(
        user, host, dbname), timeout=5)


@when('we send "ctrl + d"')
def step_ctrl_d(context):
    """Send Ctrl + D to hopefully exit."""
    context.cli.sendcontrol('d')
    context.exit_sent = True


@when('we send "\?" command')
def step_send_help(context):
    """Send \?

    to see help.

    """
    context.cli.sendline('\\?')

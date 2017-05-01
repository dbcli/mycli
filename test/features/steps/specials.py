# -*- coding: utf-8
"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""
from __future__ import unicode_literals

import wrappers
from behave import when, then


@when('we refresh completions')
def step_refresh_completions(context):
    """Send refresh command."""
    context.cli.sendline('rehash')


@then('we see completions refresh started')
def step_see_refresh_started(context):
    """Wait to see refresh output."""
    wrappers.expect_exact(
        context, context.conf['pager_boundary'] + '\r\n', timeout=5, ignore_before=True)
    wrappers.expect_exact(
        context, 'Auto-completion refresh started in the background.\r\n', timeout=2)
    wrappers.expect_exact(
        context, context.conf['pager_boundary'] + '\r\n', timeout=5)

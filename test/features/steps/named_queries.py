# -*- coding: utf-8
"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""
from __future__ import unicode_literals

import wrappers
from behave import when, then


@when('we save a named query')
def step_save_named_query(context):
    """Send \ns command."""
    context.cli.sendline('\\fs foo SELECT 12345')


@when('we use a named query')
def step_use_named_query(context):
    """Send \n command."""
    context.cli.sendline('\\f foo')


@when('we delete a named query')
def step_delete_named_query(context):
    """Send \nd command."""
    context.cli.sendline('\\fd foo')


@then('we see the named query saved')
def step_see_named_query_saved(context):
    """Wait to see query saved."""
    wrappers.expect_pager(context, 'Saved.\r\n', timeout=1)


@then('we see the named query executed')
def step_see_named_query_executed(context):
    """Wait to see select output."""
    wrappers.expect_exact(context, '12345', timeout=1)
    wrappers.expect_exact(context, 'SELECT 1', timeout=1)


@then('we see the named query deleted')
def step_see_named_query_deleted(context):
    """Wait to see query deleted."""
    wrappers.expect_pager(context, 'foo: Deleted\r\n', timeout=1)

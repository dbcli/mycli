"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""

from behave import when
from textwrap import dedent
import tempfile
import wrappers


@when('we run dbcli')
def step_run_cli(context):
    wrappers.run_cli(context)


@when('we wait for prompt')
def step_wait_prompt(context):
    wrappers.wait_prompt(context)


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
    wrappers.expect_exact(
        context, context.conf['pager_boundary'] + '\r\n', timeout=5)


@when(u'we send source command')
def step_send_source_command(context):
    with tempfile.NamedTemporaryFile() as f:
        f.write(b'\?')
        f.flush()
        context.cli.sendline('\. {0}'.format(f.name))
        wrappers.expect_exact(
            context, context.conf['pager_boundary'] + '\r\n', timeout=5)


@when(u'we run query to check application_name')
def step_check_application_name(context):
    context.cli.sendline(
        "SELECT 'found' FROM performance_schema.session_connect_attrs WHERE attr_name = 'program_name' AND attr_value = 'mycli'"
    )


@then(u'we see found')
def step_see_found(context):
    wrappers.expect_exact(
        context,
        context.conf['pager_boundary'] + '\r' + dedent('''
            +-------+\r
            | found |\r
            +-------+\r
            | found |\r
            +-------+\r
            \r
        ''') + context.conf['pager_boundary'],
        timeout=5
    )


@then(u'we confirm the destructive warning')
def step_confirm_destructive_command(context):
    """Confirm destructive command."""
    wrappers.expect_exact(
        context, 'You\'re about to run a destructive command.\r\nDo you want to proceed? (y/n):', timeout=2)
    context.cli.sendline('y')


@when(u'we answer the destructive warning with "{confirmation}"')
def step_confirm_destructive_command(context, confirmation):
    """Confirm destructive command."""
    wrappers.expect_exact(
        context, 'You\'re about to run a destructive command.\r\nDo you want to proceed? (y/n):', timeout=2)
    context.cli.sendline(confirmation)


@then(u'we answer the destructive warning with invalid "{confirmation}" and see text "{text}"')
def step_confirm_destructive_command(context, confirmation, text):
    """Confirm destructive command."""
    wrappers.expect_exact(
        context, 'You\'re about to run a destructive command.\r\nDo you want to proceed? (y/n):', timeout=2)
    context.cli.sendline(confirmation)
    wrappers.expect_exact(context, text, timeout=2)
    # we must exit the Click loop, or the feature will hang
    context.cli.sendline('n')

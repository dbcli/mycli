"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""

import datetime
import tempfile
from textwrap import dedent

from behave import then, when
import wrappers


@when("we run dbcli")
def step_run_cli(context):
    wrappers.run_cli(context)


@when("we wait for prompt")
def step_wait_prompt(context):
    wrappers.wait_prompt(context)


@when('we send "ctrl + d"')
def step_ctrl_d(context):
    """Send Ctrl + D to hopefully exit."""
    context.cli.sendcontrol("d")
    context.exit_sent = True


@when('we send "ctrl + o, ctrl + d"')
def step_ctrl_o_ctrl_d(context):
    """Send ctrl + o, ctrl + d to insert the quoted date."""
    context.cli.send("SELECT ")
    context.cli.sendcontrol("o")
    context.cli.sendcontrol("d")
    context.cli.send(" AS dt")
    context.cli.sendline("")


@when(r'we send "\?" command')
def step_send_help(context):
    r"""Send \?

    to see help.

    """
    context.cli.sendline("\\?")
    wrappers.expect_exact(context, context.conf["pager_boundary"] + "\r\n", timeout=5)


@when("we send source command")
def step_send_source_command(context):
    with tempfile.NamedTemporaryFile() as f:
        f.write(b"\\?")
        f.flush()
        context.cli.sendline("\\. {0}".format(f.name))
        wrappers.expect_exact(context, context.conf["pager_boundary"] + "\r\n", timeout=5)


@when("we run query to check application_name")
def step_check_application_name(context):
    context.cli.sendline(
        "SELECT 'found' FROM performance_schema.session_connect_attrs WHERE attr_name = 'program_name' AND attr_value = 'mycli'"
    )


@then("we see found")
def step_see_found(context):
    wrappers.expect_exact(
        context,
        context.conf["pager_boundary"]
        + "\r"
        + dedent("""
            +-------+\r
            | found |\r
            +-------+\r
            | found |\r
            +-------+\r
            \r
        """)
        + context.conf["pager_boundary"],
        timeout=5,
    )


@then("we see the date")
def step_see_date(context):
    # There are some edge cases in which this test could fail,
    # such as running near midnight when the test database has
    # a different TZ setting than the system.
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    wrappers.expect_exact(
        context,
        context.conf["pager_boundary"]
        + "\r"
        + dedent(f"""
            +------------+\r
            | dt         |\r
            +------------+\r
            | {date_str} |\r
            +------------+\r
            \r
        """)
        + context.conf["pager_boundary"],
        timeout=5,
    )


@then("we confirm the destructive warning")
def step_confirm_destructive_command(context):  # noqa
    """Confirm destructive command."""
    wrappers.expect_exact(context, "You're about to run a destructive command.\r\nDo you want to proceed? (y/n):", timeout=2)
    context.cli.sendline("y")


@when('we answer the destructive warning with "{confirmation}"')
def step_confirm_destructive_command(context, confirmation):  # noqa
    """Confirm destructive command."""
    wrappers.expect_exact(context, "You're about to run a destructive command.\r\nDo you want to proceed? (y/n):", timeout=2)
    context.cli.sendline(confirmation)


@then('we answer the destructive warning with invalid "{confirmation}" and see text "{text}"')
def step_confirm_destructive_command(context, confirmation, text):  # noqa
    """Confirm destructive command."""
    wrappers.expect_exact(context, "You're about to run a destructive command.\r\nDo you want to proceed? (y/n):", timeout=2)
    context.cli.sendline(confirmation)
    wrappers.expect_exact(context, text, timeout=2)
    # we must exit the Click loop, or the feature will hang
    context.cli.sendline("n")

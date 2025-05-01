"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""

from behave import then, when
import wrappers


@when("we refresh completions")
def step_refresh_completions(context):
    """Send refresh command."""
    context.cli.sendline("rehash")


@then('we see text "{text}"')
def step_see_text(context, text):
    """Wait to see given text message."""
    wrappers.expect_exact(context, text, timeout=2)


@then("we see completions refresh started")
def step_see_refresh_started(context):
    """Wait to see refresh output."""
    wrappers.expect_exact(context, "Auto-completion refresh started in the background.", timeout=2)

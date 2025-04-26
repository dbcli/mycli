"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""

from behave import then, when
import wrappers


@when("we save a named query")
def step_save_named_query(context):
    """Send \fs command."""
    context.cli.sendline("\\fs foo SELECT 12345")


@when("we use a named query")
def step_use_named_query(context):
    """Send \f command."""
    context.cli.sendline("\\f foo")


@when("we delete a named query")
def step_delete_named_query(context):
    """Send \fd command."""
    context.cli.sendline("\\fd foo")


@then("we see the named query saved")
def step_see_named_query_saved(context):
    """Wait to see query saved."""
    wrappers.expect_exact(context, "Saved.", timeout=2)


@then("we see the named query executed")
def step_see_named_query_executed(context):
    """Wait to see select output."""
    wrappers.expect_exact(context, "SELECT 12345", timeout=2)


@then("we see the named query deleted")
def step_see_named_query_deleted(context):
    """Wait to see query deleted."""
    wrappers.expect_exact(context, "foo: Deleted", timeout=2)


@when("we save a named query with parameters")
def step_save_named_query_with_parameters(context):
    """Send \fs command for query with parameters."""
    context.cli.sendline('\\fs foo_args SELECT $1, "$2", "$3"')


@when("we use named query with parameters")
def step_use_named_query_with_parameters(context):
    """Send \f command with parameters."""
    context.cli.sendline('\\f foo_args 101 second "third value"')


@then("we see the named query with parameters executed")
def step_see_named_query_with_parameters_executed(context):
    """Wait to see select output."""
    wrappers.expect_exact(context, 'SELECT 101, "second", "third value"', timeout=2)


@when("we use named query with too few parameters")
def step_use_named_query_with_too_few_parameters(context):
    """Send \f command with missing parameters."""
    context.cli.sendline("\\f foo_args 101")


@then("we see the named query with parameters fail with missing parameters")
def step_see_named_query_with_parameters_fail_with_missing_parameters(context):
    """Wait to see select output."""
    wrappers.expect_exact(context, "missing substitution for $2 in query:", timeout=2)


@when("we use named query with too many parameters")
def step_use_named_query_with_too_many_parameters(context):
    """Send \f command with extra parameters."""
    context.cli.sendline("\\f foo_args 101 102 103 104")


@then("we see the named query with parameters fail with extra parameters")
def step_see_named_query_with_parameters_fail_with_extra_parameters(context):
    """Wait to see select output."""
    wrappers.expect_exact(context, "query does not have substitution parameter $4:", timeout=2)

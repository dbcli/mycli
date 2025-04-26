"""Steps for behavioral style tests are defined in this module.

Each step is defined by the string decorating it. This string is used
to call the step in "*.feature" file.

"""

from behave import then, when
import pexpect
import wrappers


@when("we create database")
def step_db_create(context):
    """Send create database."""
    context.cli.sendline("create database {0};".format(context.conf["dbname_tmp"]))

    context.response = {"database_name": context.conf["dbname_tmp"]}


@when("we drop database")
def step_db_drop(context):
    """Send drop database."""
    context.cli.sendline("drop database {0};".format(context.conf["dbname_tmp"]))


@when("we connect to test database")
def step_db_connect_test(context):
    """Send connect to database."""
    db_name = context.conf["dbname"]
    context.currentdb = db_name
    context.cli.sendline("use {0};".format(db_name))


@when("we connect to quoted test database")
def step_db_connect_quoted_tmp(context):
    """Send connect to database."""
    db_name = context.conf["dbname"]
    context.currentdb = db_name
    context.cli.sendline("use `{0}`;".format(db_name))


@when("we connect to tmp database")
def step_db_connect_tmp(context):
    """Send connect to database."""
    db_name = context.conf["dbname_tmp"]
    context.currentdb = db_name
    context.cli.sendline("use {0}".format(db_name))


@when("we connect to dbserver")
def step_db_connect_dbserver(context):
    """Send connect to database."""
    context.currentdb = "mysql"
    context.cli.sendline("use mysql")


@then("dbcli exits")
def step_wait_exit(context):
    """Make sure the cli exits."""
    wrappers.expect_exact(context, pexpect.EOF, timeout=5)


@then("we see dbcli prompt")
def step_see_prompt(context):
    """Wait to see the prompt."""
    user = context.conf["user"]
    host = context.conf["host"]
    dbname = context.currentdb
    wrappers.wait_prompt(context, "{0}@{1}:{2}> ".format(user, host, dbname))


@then("we see help output")
def step_see_help(context):
    for expected_line in context.fixture_data["help_commands.txt"]:
        wrappers.expect_exact(context, expected_line, timeout=1)


@then("we see database created")
def step_see_db_created(context):
    """Wait to see create database output."""
    wrappers.expect_exact(context, "Query OK, 1 row affected", timeout=2)


@then("we see database dropped")
def step_see_db_dropped(context):
    """Wait to see drop database output."""
    wrappers.expect_exact(context, "Query OK, 0 rows affected", timeout=2)


@then("we see database dropped and no default database")
def step_see_db_dropped_no_default(context):
    """Wait to see drop database output."""
    user = context.conf["user"]
    host = context.conf["host"]
    database = "(none)"
    context.currentdb = None

    wrappers.expect_exact(context, "Query OK, 0 rows affected", timeout=2)
    wrappers.wait_prompt(context, "{0}@{1}:{2}>".format(user, host, database))


@then("we see database connected")
def step_see_db_connected(context):
    """Wait to see drop database output."""
    wrappers.expect_exact(context, 'You are now connected to database "', timeout=2)
    wrappers.expect_exact(context, '"', timeout=2)
    wrappers.expect_exact(context, ' as user "{0}"'.format(context.conf["user"]), timeout=2)

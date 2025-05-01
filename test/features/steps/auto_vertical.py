from textwrap import dedent

from behave import then, when
from utils import parse_cli_args_to_dict
import wrappers


@when("we run dbcli with {arg}")
def step_run_cli_with_arg(context, arg):
    wrappers.run_cli(context, run_args=parse_cli_args_to_dict(arg))


@when("we execute a small query")
def step_execute_small_query(context):
    context.cli.sendline("select 1")


@when("we execute a large query")
def step_execute_large_query(context):
    context.cli.sendline("select {}".format(",".join([str(n) for n in range(1, 50)])))


@then("we see small results in horizontal format")
def step_see_small_results(context):
    wrappers.expect_pager(
        context,
        dedent("""\
        +---+\r
        | 1 |\r
        +---+\r
        | 1 |\r
        +---+\r
        \r
        """),
        timeout=5,
    )
    wrappers.expect_exact(context, "1 row in set", timeout=2)


@then("we see large results in vertical format")
def step_see_large_results(context):
    rows = ["{n:3}| {n}".format(n=str(n)) for n in range(1, 50)]
    expected = "***************************[ 1. row ]***************************\r\n" + "{}\r\n".format("\r\n".join(rows) + "\r\n")

    wrappers.expect_pager(context, expected, timeout=10)
    wrappers.expect_exact(context, "1 row in set", timeout=2)

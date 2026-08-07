# type: ignore

from behave import then, when
import wrappers

from test.features.environment import get_db_name_from_context
from test.features.steps.utils import parse_cli_args_to_dict

TEST_LOGIN_PATH = "test_login_path"


@when('we run mycli with arguments "{exact_args}" without arguments "{excluded_args}"')
@when('we run mycli without arguments "{excluded_args}"')
def step_run_cli_without_args(context, excluded_args, exact_args=""):
    wrappers.run_cli(context, run_args=parse_cli_args_to_dict(exact_args), exclude_args=parse_cli_args_to_dict(excluded_args).keys())


@then('status is socket or tcpip')
def status_is_socket_or_tcp_ip(context):
    # The mycli connection can fall back to TCP/IP when a socket is
    # unavailable, independently of the fixture's setup connection.
    wrappers.expect_exact(context, ('via UNIX socket', 'via TCP/IP'), timeout=5)

    # Normally, the shutdown after scenario waits for the prompt. But we may
    # have changed the prompt, depending on parameters, so wait for its last
    # character.
    context.cli.expect_exact(">")
    context.atprompt = True


@then("we are logged in")
def we_are_logged_in(context):
    db_name = get_db_name_from_context(context)
    context.cli.expect_exact(f"{db_name}>", timeout=5)
    context.atprompt = True

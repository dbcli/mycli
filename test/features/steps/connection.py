import io
import os

from behave import then, when
import wrappers

from mycli.config import encrypt_mylogin_cnf
from test.features.environment import MY_CNF_PATH, MYLOGIN_CNF_PATH, get_db_name_from_context
from test.features.steps.utils import parse_cli_args_to_dict
from test.utils import HOST, PASSWORD, PORT, USER

TEST_LOGIN_PATH = "test_login_path"


@when('we run mycli with arguments "{exact_args}" without arguments "{excluded_args}"')
@when('we run mycli without arguments "{excluded_args}"')
def step_run_cli_without_args(context, excluded_args, exact_args=""):
    wrappers.run_cli(context, run_args=parse_cli_args_to_dict(exact_args), exclude_args=parse_cli_args_to_dict(excluded_args).keys())


@then('status contains "{expression}"')
def status_contains(context, expression):
    wrappers.expect_exact(context, f"{expression}", timeout=5)

    # Normally, the shutdown after scenario waits for the prompt.
    # But we may have changed the prompt, depending on parameters,
    # so let's wait for its last character
    context.cli.expect_exact(">")
    context.atprompt = True


@when("we create my.cnf file")
def step_create_my_cnf_file(context):
    my_cnf = f"[client]\nhost = {HOST}\nport = {PORT}\nuser = {USER}\npassword = {PASSWORD}\n"
    with open(MY_CNF_PATH, "w") as f:
        f.write(my_cnf)


@when("we create mylogin.cnf file")
def step_create_mylogin_cnf_file(context):
    os.environ.pop("MYSQL_TEST_LOGIN_FILE", None)
    mylogin_cnf = f"[{TEST_LOGIN_PATH}]\nhost = {HOST}\nport = {PORT}\nuser = {USER}\npassword = {PASSWORD}\n"
    with open(MYLOGIN_CNF_PATH, "wb") as f:
        input_file = io.StringIO(mylogin_cnf)
        f.write(encrypt_mylogin_cnf(input_file).read())


@then("we are logged in")
def we_are_logged_in(context):
    db_name = get_db_name_from_context(context)
    context.cli.expect_exact(f"{db_name}>", timeout=5)
    context.atprompt = True

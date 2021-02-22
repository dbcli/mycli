import shlex
from behave import when, then

import wrappers
from test.features.steps.utils import parse_cli_args_to_dict


@when('we run mycli with arguments "{exact_args}" without arguments "{excluded_args}"')
@when('we run mycli without arguments "{excluded_args}"')
def step_run_cli_without_args(context, excluded_args, exact_args=''):
    wrappers.run_cli(
        context,
        run_args=parse_cli_args_to_dict(exact_args),
        exclude_args=parse_cli_args_to_dict(excluded_args).keys()
    )


@then('status contains "{expression}"')
def status_contains(context, expression):
    wrappers.expect_exact(context, f'{expression}', timeout=5)

    # Normally, the shutdown after scenario waits for the prompt.
    # But we may have changed the prompt, depending on parameters,
    # so let's wait for its last character
    context.cli.expect_exact('>')
    context.atprompt = True


# type: ignore

import os
from textwrap import dedent

from behave import then, when
import wrappers


@when("we start external editor providing a file name")
def step_edit_file(context):
    """Edit file with external editor."""
    context.editor_file_name = os.path.join(context.package_root, f"test_file_{context.conf['vi']}.sql")
    if os.path.exists(context.editor_file_name):
        os.remove(context.editor_file_name)
    context.cli.sendline(f"\\e {os.path.basename(context.editor_file_name)}")
    wrappers.expect_exact(context, 'Entering Ex mode.  Type "visual" to go to Normal mode.', timeout=4)
    wrappers.expect_exact(context, "\r\n:", timeout=4)


@when('we type "{query}" in the editor')
def step_edit_type_sql(context, query):
    context.cli.sendline("i")
    context.cli.sendline(query)
    context.cli.sendline(".")
    wrappers.expect_exact(context, "\r\n:", timeout=4)


@when("we exit the editor")
def step_edit_quit(context):
    context.cli.sendline("x")
    wrappers.expect_exact(context, "written", timeout=4)


@then('we see "{query}" in prompt')
def step_edit_done_sql(context, query):
    for match in query.split(" "):
        wrappers.expect_exact(context, match, timeout=5)
    # Cleanup the command line.
    context.cli.sendcontrol("c")
    # Cleanup the edited file.
    if context.editor_file_name and os.path.exists(context.editor_file_name):
        os.remove(context.editor_file_name)


@when("we tee output")
def step_tee_ouptut(context):
    context.tee_file_name = os.path.join(context.package_root, f"tee_file_{context.conf['vi']}.sql")
    if os.path.exists(context.tee_file_name):
        os.remove(context.tee_file_name)
    context.cli.sendline(f"tee {os.path.basename(context.tee_file_name)}")


@when('we select "select {param}"')
def step_query_select_number(context, param):
    context.cli.sendline(f"select {param}")
    expected = (
        dedent(
            f"""
            +{'-' * (len(param) + 2)}+\r
            | {param} |\r
            +{'-' * (len(param) + 2)}+\r
            | {param} |\r
            +{'-' * (len(param) + 2)}+
            """
        ).strip()
        + '\r\n\r\n'
    )

    wrappers.expect_pager(
        context,
        expected,
        timeout=5,
    )
    wrappers.expect_exact(context, "1 row in set", timeout=2)


@then('we see tabular result "{result}"')
def step_see_tabular_result(context, result):
    wrappers.expect_exact(context, f'| {result} |', timeout=2)


@then('we see csv result "{result}"')
def step_see_csv_result(context, result):
    wrappers.expect_exact(context, f'"{result}"', timeout=2)


@when('we query "{query}"')
def step_query(context, query):
    context.cli.sendline(query)


@when("we notee output")
def step_notee_output(context):
    context.cli.sendline("notee")


@then("we see 123456 in tee output")
def step_see_123456_in_ouput(context):
    with open(context.tee_file_name) as f:
        assert "123456" in f.read()
    if os.path.exists(context.tee_file_name):
        os.remove(context.tee_file_name)


@then('we see csv {result} in file output')
def step_see_csv_result_in_redirected_ouput(context, result):
    wrappers.expect_exact(context, f'"{result}"', timeout=2)
    temp_filename = "/tmp/output1.csv"
    if os.path.exists(temp_filename):
        os.remove(temp_filename)


@then('we see text {result} in file output')
def step_see_text_result_in_redirected_ouput(context, result):
    wrappers.expect_exact(context, f' {result}', timeout=2)
    temp_filename = "/tmp/output1.txt"
    if os.path.exists(temp_filename):
        os.remove(temp_filename)


@then("we see space 12 in command output")
def step_see_space_12_in_command_ouput(context):
    wrappers.expect_exact(context, ' 12', timeout=2)


@then("we see space 6 in command output")
def step_see_space_6_in_command_ouput(context):
    wrappers.expect_exact(context, ' 6', timeout=2)


@then('delimiter is set to "{delimiter}"')
def delimiter_is_set(context, delimiter):
    wrappers.expect_exact(context, f"Changed delimiter to {delimiter}", timeout=2)

import re
import sys
import textwrap

import pexpect

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO


def expect_exact(context, expected, timeout):
    timedout = False
    try:
        context.cli.expect_exact(expected, timeout=timeout)
    except pexpect.TIMEOUT:
        timedout = True
    if timedout:
        # Strip color codes out of the output.
        actual = re.sub(r"\x1b\[([0-9A-Za-z;?])+[m|K]?", "", context.cli.before)
        raise Exception(
            textwrap.dedent("""\
                Expected:
                ---
                {0!r}
                ---
                Actual:
                ---
                {1!r}
                ---
                Full log:
                ---
                {2!r}
                ---
            """).format(expected, actual, context.logfile.getvalue())
        )


def expect_pager(context, expected, timeout):
    expect_exact(context, "{0}\r\n{1}{0}\r\n".format(context.conf["pager_boundary"], expected), timeout=timeout)


def run_cli(context, run_args=None, exclude_args=None):
    """Run the process using pexpect."""
    run_args = run_args or {}
    rendered_args = []
    exclude_args = set(exclude_args) if exclude_args else set()

    conf = dict(**context.conf)
    conf.update(run_args)

    def add_arg(name, key, value):
        if name not in exclude_args:
            if value is not None:
                rendered_args.extend((key, value))
            else:
                rendered_args.append(key)

    if conf.get("host", None):
        add_arg("host", "-h", conf["host"])
    if conf.get("user", None):
        add_arg("user", "-u", conf["user"])
    if conf.get("pass", None):
        add_arg("pass", "-p", conf["pass"])
    if conf.get("port", None):
        add_arg("port", "-P", str(conf["port"]))
    if conf.get("dbname", None):
        add_arg("dbname", "-D", conf["dbname"])
    if conf.get("defaults-file", None):
        add_arg("defaults_file", "--defaults-file", conf["defaults-file"])
    if conf.get("myclirc", None):
        add_arg("myclirc", "--myclirc", conf["myclirc"])
    if conf.get("login_path"):
        add_arg("login_path", "--login-path", conf["login_path"])

    for arg_name, arg_value in conf.items():
        if arg_name.startswith("-"):
            add_arg(arg_name, arg_name, arg_value)

    try:
        cli_cmd = context.conf["cli_command"]
    except KeyError:
        cli_cmd = ('{0!s} -c "import coverage ; coverage.process_startup(); import mycli.main; mycli.main.cli()"').format(sys.executable)

    cmd_parts = [cli_cmd] + rendered_args
    cmd = " ".join(cmd_parts)
    context.cli = pexpect.spawnu(cmd, cwd=context.package_root)
    context.logfile = StringIO()
    context.cli.logfile = context.logfile
    context.exit_sent = False
    context.currentdb = context.conf["dbname"]


def wait_prompt(context, prompt=None):
    """Make sure prompt is displayed."""
    if prompt is None:
        user = context.conf["user"]
        host = context.conf["host"]
        dbname = context.currentdb
        prompt = ("{0}@{1}:{2}>".format(user, host, dbname),)
    expect_exact(context, prompt, timeout=5)
    context.atprompt = True

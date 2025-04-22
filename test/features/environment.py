import os
import shutil
import sys
from tempfile import mkstemp

import db_utils as dbutils
import fixture_utils as fixutils
import pexpect

from steps.wrappers import run_cli, wait_prompt

test_log_file = os.path.join(os.environ["HOME"], ".mycli.test.log")


SELF_CONNECTING_FEATURES = ("test/features/connection.feature",)


MY_CNF_PATH = os.path.expanduser("~/.my.cnf")
MY_CNF_BACKUP_PATH = f"{MY_CNF_PATH}.backup"
MYLOGIN_CNF_PATH = os.path.expanduser("~/.mylogin.cnf")
MYLOGIN_CNF_BACKUP_PATH = f"{MYLOGIN_CNF_PATH}.backup"


def get_db_name_from_context(context):
    return context.config.userdata.get("my_test_db", None) or "mycli_behave_tests"


def before_all(context):
    """Set env parameters."""
    os.environ["LINES"] = "100"
    os.environ["COLUMNS"] = "100"
    os.environ["EDITOR"] = "ex"
    os.environ["LC_ALL"] = "en_US.UTF-8"
    os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
    os.environ["MYCLI_HISTFILE"] = os.devnull

    # test_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    # login_path_file = os.path.join(test_dir, "mylogin.cnf")
    #    os.environ['MYSQL_TEST_LOGIN_FILE'] = login_path_file

    context.package_root = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    os.environ["COVERAGE_PROCESS_START"] = os.path.join(context.package_root, ".coveragerc")

    context.exit_sent = False

    vi = "_".join([str(x) for x in sys.version_info[:3]])
    db_name = get_db_name_from_context(context)
    db_name_full = "{0}_{1}".format(db_name, vi)

    # Store get params from config/environment variables
    context.conf = {
        "host": context.config.userdata.get("my_test_host", os.getenv("PYTEST_HOST", "localhost")),
        "port": context.config.userdata.get("my_test_port", int(os.getenv("PYTEST_PORT", "3306"))),
        "user": context.config.userdata.get("my_test_user", os.getenv("PYTEST_USER", "root")),
        "pass": context.config.userdata.get("my_test_pass", os.getenv("PYTEST_PASSWORD", None)),
        "cli_command": context.config.userdata.get("my_cli_command", None)
        or sys.executable + ' -c "import coverage ; coverage.process_startup(); import mycli.main; mycli.main.cli()"',
        "dbname": db_name,
        "dbname_tmp": db_name_full + "_tmp",
        "vi": vi,
        "pager_boundary": "---boundary---",
    }

    _, my_cnf = mkstemp()
    with open(my_cnf, "w") as f:
        f.write(
            "[client]\npager={0} {1} {2}\n".format(
                sys.executable, os.path.join(context.package_root, "test/features/wrappager.py"), context.conf["pager_boundary"]
            )
        )
    context.conf["defaults-file"] = my_cnf
    context.conf["myclirc"] = os.path.join(context.package_root, "test", "myclirc")

    context.cn = dbutils.create_db(
        context.conf["host"], context.conf["port"], context.conf["user"], context.conf["pass"], context.conf["dbname"]
    )

    context.fixture_data = fixutils.read_fixture_files()


def after_all(context):
    """Unset env parameters."""
    dbutils.close_cn(context.cn)
    dbutils.drop_db(context.conf["host"], context.conf["port"], context.conf["user"], context.conf["pass"], context.conf["dbname"])

    # Restore env vars.
    # for k, v in context.pgenv.items():
    #    if k in os.environ and v is None:
    #        del os.environ[k]
    #    elif v:
    #        os.environ[k] = v


def before_step(context, _):
    context.atprompt = False


def before_scenario(context, arg):
    with open(test_log_file, "w") as f:
        f.write("")
    if arg.location.filename not in SELF_CONNECTING_FEATURES:
        run_cli(context)
        wait_prompt(context)

    if os.path.exists(MY_CNF_PATH):
        shutil.move(MY_CNF_PATH, MY_CNF_BACKUP_PATH)

    if os.path.exists(MYLOGIN_CNF_PATH):
        shutil.move(MYLOGIN_CNF_PATH, MYLOGIN_CNF_BACKUP_PATH)


def after_scenario(context, _):
    """Cleans up after each test complete."""
    with open(test_log_file) as f:
        for line in f:
            if "error" in line.lower():
                raise RuntimeError(f"Error in log file: {line}")

    if hasattr(context, "cli") and not context.exit_sent:
        # Quit nicely.
        if not context.atprompt:
            user = context.conf["user"]
            host = context.conf["host"]
            dbname = context.currentdb
            context.cli.expect_exact("{0}@{1}:{2}>".format(user, host, dbname), timeout=5)
        context.cli.sendcontrol("c")
        context.cli.sendcontrol("d")
        context.cli.expect_exact(pexpect.EOF, timeout=5)

    if os.path.exists(MY_CNF_BACKUP_PATH):
        shutil.move(MY_CNF_BACKUP_PATH, MY_CNF_PATH)

    if os.path.exists(MYLOGIN_CNF_BACKUP_PATH):
        shutil.move(MYLOGIN_CNF_BACKUP_PATH, MYLOGIN_CNF_PATH)
    elif os.path.exists(MYLOGIN_CNF_PATH):
        # This file was moved in `before_scenario`.
        # If it exists now, it has been created during a test
        os.remove(MYLOGIN_CNF_PATH)


# TODO: uncomment to debug a failure
# def after_step(context, step):
#     if step.status == "failed":
#         import ipdb; ipdb.set_trace()

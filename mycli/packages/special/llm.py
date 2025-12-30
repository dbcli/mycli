import contextlib
import functools
import io
import logging
import os
import re
from runpy import run_module
import shlex
import sys
from time import time
from typing import Any

import click

try:
    if not os.environ.get('MYCLI_LLM_OFF'):
        import llm

        LLM_IMPORTED = True
    else:
        LLM_IMPORTED = False
except ImportError:
    LLM_IMPORTED = False
try:
    if not os.environ.get('MYCLI_LLM_OFF'):
        from llm.cli import cli

        LLM_CLI_IMPORTED = True
    else:
        LLM_CLI_IMPORTED = False
except ImportError:
    LLM_CLI_IMPORTED = False
from pymysql.cursors import Cursor

from mycli.packages.special.main import Verbosity, parse_special_command

log = logging.getLogger(__name__)

LLM_TEMPLATE_NAME = "mycli-llm-template"


def run_external_cmd(
    cmd: str,
    *args,
    capture_output=False,
    restart_cli=False,
    raise_exception=True,
) -> tuple[int, str]:
    original_exe = sys.executable
    original_args = sys.argv
    try:
        sys.argv = [cmd] + list(args)
        code = 0
        if capture_output:
            buffer = io.StringIO()
            redirect: contextlib.ExitStack[bool | None] | contextlib.nullcontext[None] = contextlib.ExitStack()
            assert isinstance(redirect, contextlib.ExitStack)
            redirect.enter_context(contextlib.redirect_stdout(buffer))
            redirect.enter_context(contextlib.redirect_stderr(buffer))
        else:
            redirect = contextlib.nullcontext()
        with redirect:
            try:
                run_module(cmd, run_name="__main__")
            except SystemExit as e:
                code = int(e.code or 0)
                if code != 0 and raise_exception:
                    if capture_output:
                        raise RuntimeError(buffer.getvalue()) from e
                    raise RuntimeError(f"Command {cmd} failed with exit code {code}.") from e
            except Exception as e:
                code = 1
                if raise_exception:
                    if capture_output:
                        raise RuntimeError(buffer.getvalue()) from e
                    raise RuntimeError(f"Command {cmd} failed: {e}") from e
        if restart_cli and code == 0:
            os.execv(original_exe, [original_exe] + original_args)
        if capture_output:
            return code, buffer.getvalue()
        else:
            return code, ""
    finally:
        sys.argv = original_args


def _build_command_tree(cmd) -> dict[str, Any] | None:
    tree: dict[str, Any] | None = {}
    assert isinstance(tree, dict)
    if isinstance(cmd, click.Group):
        for name, subcmd in cmd.commands.items():
            if cmd.name == "models" and name == "default":
                tree[name] = {x.model_id: None for x in llm.get_models()}
            else:
                tree[name] = _build_command_tree(subcmd)
    else:
        tree = None
    return tree


def build_command_tree(cmd) -> dict[str, Any]:
    return _build_command_tree(cmd) or {}


# Generate the command tree for autocompletion
COMMAND_TREE = build_command_tree(cli) if LLM_CLI_IMPORTED is True else {}


def get_completions(
    tokens: list[str],
    tree: dict[str, Any] | None = None,
) -> list[str]:
    tree = tree or COMMAND_TREE
    for token in tokens:
        if token.startswith("-"):
            continue
        if tree and token in tree:
            tree = tree[token]
        else:
            return []
    return list(tree.keys()) if tree else []


class FinishIteration(Exception):
    def __init__(self, results=None):
        self.results = results


USAGE = """
Use an LLM to create SQL queries to answer questions from your database.
Examples:

# Ask a question.
> \\llm 'Most visited urls?'

# List available models
> \\llm models
> gpt-4o
> gpt-3.5-turbo

# Change default model
> \\llm models default llama3

# Set api key (not required for local models)
> \\llm keys set openai

# Install a model plugin
> \\llm install llm-ollama
> llm-ollama installed.

# Plugins directory
# https://llm.datasette.io/en/stable/plugins/directory.html
"""

NEED_DEPENDENCIES = """
To enable LLM features you need to install mycli with LLM support:

    pip install 'mycli[llm]'

or

    pip install 'mycli[all]'

or install LLM libraries separately

   pip install llm

This is required to use the \\llm command.
"""

_SQL_CODE_FENCE = r"```sql\n(.*?)\n```"

PROMPT = """
You are a helpful assistant who is a MySQL expert. You are embedded in a mysql
cli tool called mycli.

Answer this question:

$question

Use the following context if it is relevant to answering the question. If the
question is not about the current database then ignore the context.

You are connected to a MySQL database with the following schema:

$db_schema

Here is a sample row of data from each table:

$sample_data

If the answer can be found using a SQL query, include a sql query in a code
fence such as this one:

```sql
SELECT count(*) FROM table_name;
```
Keep your explanation concise and focused on the question asked.
"""


def ensure_mycli_template(replace: bool = False) -> None:
    if not replace:
        code, _ = run_external_cmd("llm", "templates", "show", LLM_TEMPLATE_NAME, capture_output=True, raise_exception=False)
        if code == 0:
            return
    run_external_cmd("llm", PROMPT, "--save", LLM_TEMPLATE_NAME)


@functools.cache
def cli_commands() -> list[str]:
    return list(cli.commands.keys())


def handle_llm(text: str, cur: Cursor) -> tuple[str, str | None, float]:
    _, verbosity, arg = parse_special_command(text)
    if not LLM_IMPORTED:
        output = [(None, None, None, NEED_DEPENDENCIES)]
        raise FinishIteration(output)
    if not arg.strip():
        output = [(None, None, None, USAGE)]
        raise FinishIteration(output)
    parts = shlex.split(arg)
    restart = False
    if "-c" in parts:
        capture_output = True
        use_context = False
    elif "prompt" in parts:
        capture_output = True
        use_context = True
    elif "install" in parts or "uninstall" in parts:
        capture_output = False
        use_context = False
        restart = True
    elif parts and parts[0] in cli_commands():
        capture_output = False
        use_context = False
    elif parts and parts[0] == "--help":
        capture_output = False
        use_context = False
    else:
        capture_output = True
        use_context = True
    if not use_context:
        args = parts
        if capture_output:
            click.echo("Calling llm command")
            start = time()
            _, result = run_external_cmd("llm", *args, capture_output=capture_output)
            end = time()
            match = re.search(_SQL_CODE_FENCE, result, re.DOTALL)
            if match:
                sql = match.group(1).strip()
            else:
                output = [(None, None, None, result)]
                raise FinishIteration(output)
            return (result if verbosity == Verbosity.SUCCINCT else "", sql, end - start)
        else:
            run_external_cmd("llm", *args, restart_cli=restart)
            raise FinishIteration(None)
    try:
        ensure_mycli_template()
        start = time()
        context, sql = sql_using_llm(cur=cur, question=arg)
        end = time()
        if verbosity == Verbosity.SUCCINCT:
            context = ""
        return (context, sql, end - start)
    except Exception as e:
        raise RuntimeError(e) from e


def is_llm_command(command: str) -> bool:
    cmd, _, _ = parse_special_command(command)
    return cmd in ("\\llm", "\\ai")


def sql_using_llm(
    cur: Cursor | None,
    question: str | None = None,
) -> tuple[str, str | None]:
    if cur is None:
        raise RuntimeError("Connect to a database and try again.")
    schema_query = """
        SELECT CONCAT(table_name, '(', GROUP_CONCAT(column_name, ' ', COLUMN_TYPE SEPARATOR ', '),')')
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        GROUP BY table_name
        ORDER BY table_name
    """
    tables_query = "SHOW TABLES"
    sample_row_query = "SELECT * FROM `{table}` LIMIT 1"
    click.echo("Preparing schema information to feed the llm")
    cur.execute(schema_query)
    db_schema = "\n".join([row[0] for (row,) in cur.fetchall()])
    cur.execute(tables_query)
    sample_data = {}
    for (table_name,) in cur.fetchall():
        try:
            cur.execute(sample_row_query.format(table=table_name))
        except Exception:
            continue
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
        if row is None:
            continue
        sample_data[table_name] = list(zip(cols, row, strict=True))
    args = [
        "--template",
        LLM_TEMPLATE_NAME,
        "--param",
        "db_schema",
        db_schema,
        "--param",
        "sample_data",
        sample_data,
        "--param",
        "question",
        question,
        " ",
    ]
    click.echo("Invoking llm command with schema information")
    _, result = run_external_cmd("llm", *args, capture_output=True)
    click.echo("Received response from the llm command")
    match = re.search(_SQL_CODE_FENCE, result, re.DOTALL)
    if match:
        sql = match.group(1).strip()
    else:
        sql = ""
    return (result, sql)

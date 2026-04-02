import builtins
import importlib
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import click
import pytest

from mycli.packages.special import llm as llm_module
from mycli.packages.special.llm import (
    NEED_DEPENDENCIES,
    USAGE,
    _build_command_tree,
    build_command_tree,
    ensure_mycli_template,
    get_completions,
    get_sample_data,
    get_schema,
    handle_llm,
    is_llm_command,
    run_external_cmd,
    sql_using_llm,
    truncate_list_elements,
    truncate_table_lines,
)
from mycli.packages.special.main import COMMANDS
from mycli.packages.sqlresult import SQLResult


# Override executor fixture to avoid real DB connections during llm tests
@pytest.fixture
def executor():
    """Dummy executor fixture"""
    return None


def test_reload_llm_module_handles_disabled_and_import_error_paths(monkeypatch) -> None:
    with monkeypatch.context() as m:
        m.setenv("MYCLI_LLM_OFF", "1")
        importlib.reload(llm_module)
        assert llm_module.LLM_IMPORTED is False
        assert llm_module.LLM_CLI_IMPORTED is False

    importlib.reload(llm_module)

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "llm" or name == "llm.cli":
            raise ImportError("no llm")
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as m:
        m.delenv("MYCLI_LLM_OFF", raising=False)
        m.setattr(builtins, "__import__", fake_import)
        importlib.reload(llm_module)
        assert llm_module.LLM_IMPORTED is False
        assert llm_module.LLM_CLI_IMPORTED is False

    importlib.reload(llm_module)


def test_reload_llm_module_handles_cli_import_error(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "llm.cli":
            raise ImportError("no llm cli")
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as m:
        m.delenv("MYCLI_LLM_OFF", raising=False)
        m.setattr(builtins, "__import__", fake_import)
        importlib.reload(llm_module)
        assert llm_module.LLM_IMPORTED is True
        assert llm_module.LLM_CLI_IMPORTED is False

    importlib.reload(llm_module)


def test_build_command_tree_handles_groups_models_and_leaf(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_module,
        "llm",
        SimpleNamespace(get_models=lambda: [SimpleNamespace(model_id="gpt-4o"), SimpleNamespace(model_id="llama3")]),
        raising=False,
    )

    models_group = click.Group("models")
    models_group.add_command(click.Command("default"))
    root = click.Group("root")
    root.add_command(click.Command("prompt"))
    root.add_command(models_group)

    assert _build_command_tree(root) == {
        "prompt": None,
        "models": {"default": {"gpt-4o": None, "llama3": None}},
    }
    assert build_command_tree(click.Command("leaf")) == {}


def test_get_completions_walks_tree_and_skips_flags() -> None:
    tree = {
        "models": {"default": {"gpt-4o": None}},
        "prompt": None,
    }

    assert get_completions([], tree) == ["models", "prompt"]
    assert get_completions(["models"], tree) == ["default"]
    assert get_completions(["models", "--help"], tree) == ["default"]
    assert get_completions(["models", "default"], tree) == ["gpt-4o"]
    assert get_completions(["missing"], tree) == []
    assert get_completions(["prompt"], tree) == []


def test_cli_commands_is_cached(monkeypatch) -> None:
    llm_module.cli_commands.cache_clear()
    monkeypatch.setattr(llm_module, "cli", SimpleNamespace(commands={"models": object(), "prompt": object()}))

    assert llm_module.cli_commands() == ["models", "prompt"]

    monkeypatch.setattr(llm_module, "cli", SimpleNamespace(commands={"install": object()}))
    assert llm_module.cli_commands() == ["models", "prompt"]
    llm_module.cli_commands.cache_clear()


def test_run_external_cmd_capture_output_and_restore_argv(monkeypatch, capsys) -> None:
    original_argv = list(llm_module.sys.argv)

    def fake_run_module(cmd: str, run_name: str) -> None:
        assert cmd == "llm"
        assert run_name == "__main__"
        print("stdout text")
        llm_module.sys.stderr.write("stderr text")

    monkeypatch.setattr(llm_module, "run_module", fake_run_module)

    code, output = run_external_cmd("llm", "models", capture_output=True)

    assert code == 0
    assert "stdout text" in output
    assert "stderr text" in output
    assert llm_module.sys.argv == original_argv
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_run_external_cmd_nonzero_exit_raises_with_output(monkeypatch) -> None:
    def fake_run_module(cmd: str, run_name: str) -> None:
        print("failed output")
        raise SystemExit(2)

    monkeypatch.setattr(llm_module, "run_module", fake_run_module)

    with pytest.raises(RuntimeError, match="failed output"):
        run_external_cmd("llm", capture_output=True)


def test_run_external_cmd_nonzero_exit_raises_without_output(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "run_module", lambda cmd, run_name: (_ for _ in ()).throw(SystemExit(3)))

    with pytest.raises(RuntimeError, match=r"Command llm failed with exit code 3\."):
        run_external_cmd("llm")


def test_run_external_cmd_exception_paths_and_restart(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "run_module", lambda cmd, run_name: (_ for _ in ()).throw(ValueError("boom")))

    with pytest.raises(RuntimeError, match=r"Command llm failed: boom"):
        run_external_cmd("llm")

    def fake_run_module_capture(cmd: str, run_name: str) -> None:
        print("capture boom")
        raise ValueError("boom")

    monkeypatch.setattr(llm_module, "run_module", fake_run_module_capture)
    with pytest.raises(RuntimeError, match="capture boom"):
        run_external_cmd("llm", capture_output=True)

    execv_calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(llm_module, "run_module", lambda cmd, run_name: (_ for _ in ()).throw(SystemExit(0)))
    monkeypatch.setattr(llm_module.os, "execv", lambda exe, args: execv_calls.append((exe, args)))

    code, output = run_external_cmd("llm", "install", restart_cli=True)

    assert code == 0
    assert output == ""
    assert execv_calls == [(llm_module.sys.executable, [llm_module.sys.executable] + llm_module.sys.argv)]


def test_ensure_mycli_template_returns_early_or_replaces(monkeypatch) -> None:
    calls: list[tuple] = []

    def fake_run_external_cmd(*args, **kwargs):
        calls.append((args, kwargs))
        return (0, "")

    monkeypatch.setattr(llm_module, "run_external_cmd", fake_run_external_cmd)
    ensure_mycli_template()

    assert calls == [
        (("llm", "templates", "show", llm_module.LLM_TEMPLATE_NAME), {"capture_output": True, "raise_exception": False}),
    ]

    calls.clear()

    def fake_run_external_cmd_missing(*args, **kwargs):
        calls.append((args, kwargs))
        return (1, "") if len(calls) == 1 else (0, "")

    monkeypatch.setattr(llm_module, "run_external_cmd", fake_run_external_cmd_missing)
    ensure_mycli_template()

    assert calls == [
        (("llm", "templates", "show", llm_module.LLM_TEMPLATE_NAME), {"capture_output": True, "raise_exception": False}),
        (("llm", llm_module.PROMPT, "--save", llm_module.LLM_TEMPLATE_NAME), {}),
    ]

    calls.clear()
    monkeypatch.setattr(llm_module, "run_external_cmd", fake_run_external_cmd)
    ensure_mycli_template(replace=True)

    assert calls == [
        (("llm", llm_module.PROMPT, "--save", llm_module.LLM_TEMPLATE_NAME), {}),
    ]


@patch("mycli.packages.special.llm.llm")
def test_llm_command_without_args(mock_llm, executor):
    r"""
    Invoking \llm without any arguments should print the usage and raise FinishIteration.
    """
    assert mock_llm is not None
    test_text = r"\llm"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    # Should return usage message when no args provided
    assert exc_info.value.results == [SQLResult(preamble=USAGE)]


@patch("mycli.packages.special.llm.llm")
def test_llm_command_with_help_subcommand(mock_llm, executor):
    r"""
    Invoking \llm with "help" should print the usage and raise FinishIteration.
    """
    assert mock_llm is not None
    test_text = r"\llm help"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    # Should return usage message when "help" subcommand or variant is provided
    assert exc_info.value.results == [SQLResult(preamble=USAGE)]


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_c_flag(mock_run_cmd, mock_llm, executor):
    string = "Hello, no SQL today."
    # Suppose the LLM returns some text without fenced SQL
    mock_run_cmd.return_value = (0, string)
    test_text = r"\llm -c 'Something?'"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    # Expect raw output when no SQL fence found
    assert exc_info.value.results == [SQLResult(preamble=string)]


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_c_flag_and_fenced_sql(mock_run_cmd, mock_llm, executor):
    # Return text containing a fenced SQL block
    sql_text = "SELECT * FROM users;"
    fenced = f"Here you go:\n```sql\n{sql_text}\n```"
    mock_run_cmd.return_value = (0, fenced)
    test_text = r"\llm -c 'Rewrite SQL'"
    result, sql, duration = handle_llm(test_text, executor, 'mysql', 0, 0)
    # Without verbose, result is empty, sql extracted
    assert sql == sql_text
    assert result == ""
    assert isinstance(duration, float)


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_known_subcommand(mock_run_cmd, mock_llm, executor):
    # 'models' is a known subcommand
    test_text = r"\llm models"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    mock_run_cmd.assert_called_once_with("llm", "models", restart_cli=False)
    assert exc_info.value.results is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_help_flag(mock_run_cmd, mock_llm, executor):
    test_text = r"\llm --help"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    mock_run_cmd.assert_called_once_with("llm", "--help", restart_cli=False)
    assert exc_info.value.results is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_install_flag(mock_run_cmd, mock_llm, executor):
    test_text = r"\llm install openai"
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(test_text, executor, 'mysql', 0, 0)
    mock_run_cmd.assert_called_once_with("llm", "install", "openai", restart_cli=True)
    assert exc_info.value.results is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.ensure_mycli_template")
@patch("mycli.packages.special.llm.sql_using_llm")
def test_llm_command_with_prompt(mock_sql_using_llm, mock_ensure_template, mock_llm, executor):
    r"""
    \llm prompt 'question' should use template and call sql_using_llm
    """
    mock_sql_using_llm.return_value = ("CTX", "SELECT 1;")
    test_text = r"\llm prompt 'Test?'"
    context, sql, duration = handle_llm(test_text, executor, 'mysql', 0, 0)
    mock_ensure_template.assert_called_once()
    mock_sql_using_llm.assert_called()
    assert context == "CTX"
    assert sql == "SELECT 1;"
    assert isinstance(duration, float)


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.ensure_mycli_template")
@patch("mycli.packages.special.llm.sql_using_llm")
def test_llm_command_question_with_context(mock_sql_using_llm, mock_ensure_template, mock_llm, executor):
    r"""
    \llm 'question' treats as prompt and returns SQL
    """
    mock_sql_using_llm.return_value = ("CTX2", "SELECT 2;")
    test_text = r"\llm 'Top 10?'"
    context, sql, duration = handle_llm(test_text, executor, 'mysql', 0, 0)
    mock_ensure_template.assert_called_once()
    mock_sql_using_llm.assert_called()
    assert context == "CTX2"
    assert sql == "SELECT 2;"
    assert isinstance(duration, float)


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.ensure_mycli_template")
@patch("mycli.packages.special.llm.sql_using_llm")
def test_llm_command_question_verbose(mock_sql_using_llm, mock_ensure_template, mock_llm, executor):
    r"""
    \llm+ returns verbose context and SQL
    """
    mock_sql_using_llm.return_value = ("NO_CTX", "SELECT 42;")
    test_text = r"\llm- 'Succinct?'"
    context, sql, duration = handle_llm(test_text, executor, 'mysql', 0, 0)
    assert context == ""
    assert sql == "SELECT 42;"
    assert isinstance(duration, float)


def test_handle_llm_without_dependencies(executor, monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "LLM_IMPORTED", False)

    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(r"\llm anything", executor, "mysql", 0, 0)

    assert exc_info.value.results == [SQLResult(preamble=NEED_DEPENDENCIES)]


@patch("mycli.packages.special.llm.llm")
def test_handle_llm_wraps_context_errors(mock_llm, executor, monkeypatch) -> None:
    assert mock_llm is not None
    monkeypatch.setattr(llm_module, "ensure_mycli_template", lambda: (_ for _ in ()).throw(ValueError("bad template")))

    with pytest.raises(RuntimeError, match="bad template"):
        handle_llm(r"\llm 'Top 10?'", executor, "mysql", 0, 0)


def test_is_llm_command():
    # Valid llm command variants
    for cmd in ["\\llm", "\\ai"]:
        assert is_llm_command(cmd + " 'x'")
    # Invalid commands
    assert not is_llm_command("select * from table;")


def test_sql_using_llm_no_connection():
    # Should error if no database cursor provided
    with pytest.raises(RuntimeError) as exc_info:
        sql_using_llm(None, question="test")
    assert "Connect to a database" in str(exc_info.value)


def test_truncate_list_elements_and_table_lines(monkeypatch) -> None:
    monkeypatch.setattr(llm_module.sys, "getsizeof", lambda value: len(value) if isinstance(value, (str, bytes)) else 8)

    row = ["a" * 250, b"b" * 250, 1]
    truncated = truncate_list_elements(row, prompt_field_truncate=250, prompt_section_truncate=300)
    assert truncated == ["a" * 50, b"b" * 50, 1]
    assert truncate_list_elements(row, prompt_field_truncate=0, prompt_section_truncate=0) is row
    assert truncate_list_elements(["abcdef"], prompt_field_truncate=3, prompt_section_truncate=0) == ["abc"]

    table = ["a" * 100, "b" * 100, "c" * 100]
    assert truncate_table_lines(table.copy(), prompt_section_truncate=0) == table
    assert truncate_table_lines(table.copy(), prompt_section_truncate=210) == ["a" * 100, "b" * 100]
    assert truncate_table_lines(table.copy(), prompt_section_truncate=150) == ["a" * 100]
    assert truncate_table_lines(["a" * 100], prompt_section_truncate=50) == []


def test_get_schema_and_sample_data_use_cache_and_skip_bad_rows(monkeypatch) -> None:
    llm_module.SCHEMA_DATA_CACHE.clear()
    llm_module.SAMPLE_DATA_CACHE.clear()
    monkeypatch.setattr(llm_module.click, "echo", lambda message: None)
    monkeypatch.setattr(llm_module.sys, "getsizeof", lambda value: len(value) if isinstance(value, (str, bytes)) else 8)

    class DummyCursor:
        def __init__(self) -> None:
            self.executed: list[str] = []
            self.description: list[tuple[str, None]] = []
            self._rows: list[tuple[str]] = []
            self._row: tuple[int, str] | None = None

        def execute(self, query: str) -> None:
            self.executed.append(query)
            if "information_schema.columns" in query:
                self._rows = [("orders(id int)",), ("users(name text)",)]
                return
            if query == "SHOW TABLES":
                self._rows = [("orders",), ("broken",), ("empty",)]
                return
            if "`orders`" in query:
                self.description = [("id", None), ("name", None)]
                self._row = (1, "alice")
                return
            if "`broken`" in query:
                raise RuntimeError("bad table")
            if "`empty`" in query:
                self.description = [("id", None)]
                self._row = None
                return
            raise AssertionError(f"unexpected query: {query}")

        def fetchall(self) -> list[tuple[str]]:
            return self._rows

        def fetchone(self) -> tuple[int, str] | None:
            return self._row

    cursor = DummyCursor()

    assert get_schema(cast(Any, cursor), "mysql", 0) == "orders(id int)\nusers(name text)"
    assert get_schema(cast(Any, cursor), "mysql", 0) == "orders(id int)\nusers(name text)"
    sample_data = get_sample_data(cast(Any, cursor), "mysql", 10, 100)
    assert sample_data == {"orders": [("id", 1), ("name", "alice")]}
    assert get_sample_data(cast(Any, cursor), "mysql", 10, 100) == sample_data
    assert cursor.executed.count("SHOW TABLES") == 1
    assert sum(1 for query in cursor.executed if "information_schema.columns" in query) == 1


# Test sql_using_llm with dummy cursor and fenced SQL output
@patch("mycli.packages.special.llm.run_external_cmd")
def test_sql_using_llm_success(mock_run_cmd):
    llm_module.SCHEMA_DATA_CACHE.clear()
    llm_module.SAMPLE_DATA_CACHE.clear()

    # Dummy cursor simulating database schema and sample data
    class DummyCursor:
        def __init__(self):
            self._last = []
            self.executed = []

        def execute(self, query):
            self.executed.append(query)
            if "information_schema.columns" in query:
                self._last = [("table1(col1 int,col2 text)",), ("table2(colA varchar(20))",)]
            elif query.strip().upper().startswith("SHOW TABLES"):
                self._last = [("table1",), ("table2",)]
            elif query.strip().upper().startswith("SELECT * FROM"):
                self.description = [("col1", None), ("col2", None)]
                self._row = (1, "abc")

        def fetchall(self):
            return getattr(self, "_last", [])

        def fetchone(self):
            return getattr(self, "_row", None)

    dummy_cur = DummyCursor()
    # Simulate llm CLI returning a fenced SQL result
    sql_text = "SELECT 1, 'abc';"
    fenced = f"Note\n```sql\n{sql_text}\n```"
    mock_run_cmd.return_value = (0, fenced)
    result, sql = sql_using_llm(dummy_cur, question="dummy", dbname='mysql')

    assert any("information_schema.columns" in query for query in dummy_cur.executed)
    assert "SHOW TABLES" in dummy_cur.executed
    assert any(query.strip().upper().startswith("SELECT * FROM") for query in dummy_cur.executed)
    mock_run_cmd.assert_called_once_with(
        "llm",
        "--template",
        llm_module.LLM_TEMPLATE_NAME,
        "--param",
        "db_schema",
        "table1(col1 int,col2 text)\ntable2(colA varchar(20))",
        "--param",
        "sample_data",
        {"table1": [("col1", 1), ("col2", "abc")], "table2": [("col1", 1), ("col2", "abc")]},
        "--param",
        "question",
        "dummy",
        " ",
        capture_output=True,
    )
    assert result == fenced
    assert sql == sql_text


def test_sql_using_llm_requires_schema_and_allows_missing_sql(monkeypatch) -> None:
    class DummyCursor:
        pass

    with pytest.raises(RuntimeError, match="Choose a schema and try again."):
        sql_using_llm(cast(Any, DummyCursor()), question="test", dbname="")

    monkeypatch.setattr(llm_module, "get_schema", lambda cur, dbname, truncate: "schema")
    monkeypatch.setattr(llm_module, "get_sample_data", lambda cur, dbname, field_truncate, section_truncate: {"t": [("c", 1)]})
    monkeypatch.setattr(llm_module.click, "echo", lambda message: None)
    monkeypatch.setattr(llm_module, "run_external_cmd", lambda *args, **kwargs: (0, "No fenced SQL here."))

    result, sql = sql_using_llm(cast(Any, DummyCursor()), question="test", dbname="mysql")

    assert result == "No fenced SQL here."
    assert sql == ""


# Test handle_llm supports registered command names without args
@pytest.mark.parametrize("prefix", [r"\llm", r"\ai"])
def test_handle_llm_registered_aliases_without_args(prefix, executor, monkeypatch):
    assert prefix in COMMANDS
    assert COMMANDS[prefix].handler is COMMANDS[r"\llm"].handler
    assert COMMANDS[prefix].command == r"\llm"
    monkeypatch.setattr(llm_module, "llm", object())
    with pytest.raises(llm_module.FinishIteration) as exc_info:
        handle_llm(prefix, executor, 'mysql', 0, 0)
    assert exc_info.value.results == [SQLResult(preamble=USAGE)]

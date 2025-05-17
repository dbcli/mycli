from unittest.mock import patch

import pytest

from mycli.packages.special.llm import (
    USAGE,
    FinishIteration,
    handle_llm,
    is_llm_command,
    sql_using_llm,
)


# Override executor fixture to avoid real DB connections during llm tests
@pytest.fixture
def executor():
    """Dummy executor fixture"""
    return None


@patch("mycli.packages.special.llm.llm")
def test_llm_command_without_args(mock_llm, executor):
    r"""
    Invoking \llm without any arguments should print the usage and raise FinishIteration.
    """
    assert mock_llm is not None
    test_text = r"\llm"
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(test_text, executor)
    # Should return usage message when no args provided
    assert exc_info.value.args[0] == [(None, None, None, USAGE)]


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_c_flag(mock_run_cmd, mock_llm, executor):
    # Suppose the LLM returns some text without fenced SQL
    mock_run_cmd.return_value = (0, "Hello, no SQL today.")
    test_text = r"\llm -c 'Something?'"
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(test_text, executor)
    # Expect raw output when no SQL fence found
    assert exc_info.value.args[0] == [(None, None, None, "Hello, no SQL today.")]


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_c_flag_and_fenced_sql(mock_run_cmd, mock_llm, executor):
    # Return text containing a fenced SQL block
    sql_text = "SELECT * FROM users;"
    fenced = f"Here you go:\n```sql\n{sql_text}\n```"
    mock_run_cmd.return_value = (0, fenced)
    test_text = r"\llm -c 'Rewrite SQL'"
    result, sql, duration = handle_llm(test_text, executor)
    # Without verbose, result is empty, sql extracted
    assert sql == sql_text
    assert result == ""
    assert isinstance(duration, float)


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_known_subcommand(mock_run_cmd, mock_llm, executor):
    # 'models' is a known subcommand
    test_text = r"\llm models"
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(test_text, executor)
    mock_run_cmd.assert_called_once_with("llm", "models", restart_cli=False)
    assert exc_info.value.args[0] is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_help_flag(mock_run_cmd, mock_llm, executor):
    test_text = r"\llm --help"
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(test_text, executor)
    mock_run_cmd.assert_called_once_with("llm", "--help", restart_cli=False)
    assert exc_info.value.args[0] is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.run_external_cmd")
def test_llm_command_with_install_flag(mock_run_cmd, mock_llm, executor):
    test_text = r"\llm install openai"
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(test_text, executor)
    mock_run_cmd.assert_called_once_with("llm", "install", "openai", restart_cli=True)
    assert exc_info.value.args[0] is None


@patch("mycli.packages.special.llm.llm")
@patch("mycli.packages.special.llm.ensure_mycli_template")
@patch("mycli.packages.special.llm.sql_using_llm")
def test_llm_command_with_prompt(mock_sql_using_llm, mock_ensure_template, mock_llm, executor):
    r"""
    \llm prompt 'question' should use template and call sql_using_llm
    """
    mock_sql_using_llm.return_value = ("CTX", "SELECT 1;")
    test_text = r"\llm prompt 'Test?'"
    context, sql, duration = handle_llm(test_text, executor)
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
    context, sql, duration = handle_llm(test_text, executor)
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
    context, sql, duration = handle_llm(test_text, executor)
    assert context == ""
    assert sql == "SELECT 42;"
    assert isinstance(duration, float)


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


# Test sql_using_llm with dummy cursor and fenced SQL output
@patch("mycli.packages.special.llm.run_external_cmd")
def test_sql_using_llm_success(mock_run_cmd):
    # Dummy cursor simulating database schema and sample data
    class DummyCursor:
        def __init__(self):
            self._last = []

        def execute(self, query):
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
    result, sql = sql_using_llm(dummy_cur, question="dummy")
    assert result == fenced
    assert sql == sql_text


# Test handle_llm supports alias prefixes without args
@pytest.mark.parametrize("prefix", [r"\\llm", r".llm", r"\\ai", r".ai"])
def test_handle_llm_aliases_without_args(prefix, executor, monkeypatch):
    # Ensure llm is available
    from mycli.packages.special import llm as llm_module

    monkeypatch.setattr(llm_module, "llm", object())
    with pytest.raises(FinishIteration) as exc_info:
        handle_llm(prefix, executor)
    assert exc_info.value.args[0] == [(None, None, None, USAGE)]

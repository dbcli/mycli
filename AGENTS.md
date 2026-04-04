# MyCli

A command line client for MySQL with auto-completion and syntax highlighting.

## Project Structure

/                                         # repository root
├── .github/                              # GitHub Actions and configuration
├── pyproject.toml                        # project configuration
├── doc/                                  # documentation
├── mycli/                                # application source
├── mycli/__init__.py                     # provides version number
├── mycli/clibuffer.py                    # prompt_toolkit buffer utilities
├── mycli/clistyle.py                     # prompt_toolkit style utilities
├── mycli/clitoolbar.py                   # prompt_toolkit toolbar utilities
├── mycli/compat.py                       # OS compatibility helpers
├── mycli/completion_refresher.py         # populates a `SQLCompleter` object in a background thread
├── mycli/config.py                       # configuration file readers and utilities
├── mycli/constants.py                    # shared constants
├── mycli/key_bindings.py                 # prompt_toolkit key binding utilities
├── mycli/lexer.py                        # extends `MySqlLexer` from Pygments
├── mycli/magic.py                        # Jupyter notebook magics
├── mycli/main.py                         # CLI main, configuration processing, and REPL
├── mycli/main_modes/                     # main execution paths
├── mycli/main_modes/batch.py             # batch mode execution path
├── mycli/myclirc                         # project-level configuration file
├── mycli/packages/                       # application packages
├── mycli/packages/batch_utils.py         # utilities for `--batch` mode
├── mycli/packages/checkup.py             # implementation of `--checkup` mode
├── mycli/packages/cli_utils.py           # utilities for parsing CLI arguments
├── mycli/packages/completion_engine.py   # implementation of completion suggestions
├── mycli/packages/filepaths.py           # utilities for files, including completion suggestions
├── mycli/packages/hybrid_redirection.py  # implementation of shell-style redirects
├── mycli/packages/paramiko_stub/         # stub in case the Paramiko library is not installed
├── mycli/packages/sql_utils.py           # utilities for parsing SQL statements
├── mycli/packages/prompt_utils.py        # utilities for confirming on destructive statements
├── mycli/packages/ptoolkit/              # extends prompt_toolkit
├── mycli/packages/shortcuts.py           # utilities for keyboard shortcuts
├── mycli/packages/special/               # implementation of mycli special commands
├── mycli/packages/sqlresult.py           # the `SQLResult` dataclass for holding responses
├── mycli/packages/string_utils.py        # generic string utilities
├── mycli/packages/tabular_output/        # extends cli_helper with additional output formats
├── mycli/sqlcompleter.py                 # offers SQL completions
├── mycli/sqlexecute.py                   # runs SQL queries
├── test/conftest.py                      # pytest configuration
├── test/features/                        # behave tests
├── test/myclirc                          # mycli configuration used for tests
├── test/mylogin.cnf                      # `mylogin.cnf` example used for tests
├── test/pytests/                         # pytest tests
└── test/utils.py                         # shared utilities for tests

## Development

### Python

#### Python Dependency Management

This repo uses `uv` for dependency management. **Always** prefix Python
commands with `uv run`.  Example:

```bash
uv run -- python script.py
```

#### Python Typing

This repo uses type annotations which are checked by `mypy`.  **Always** add
type annotations, and always check new code with `uv run -- mypy --install-types --non-interactive script.py`.

Use lower-case type annotations such as `tuple`, not upper-case type
annotations such as `Tuple`.

Use `Type | None` instead of `Optional[Type]`.

#### Python Testing

Tests are coordinated by `tox`, and include both `pytest` and `behave` tests.
To run the full test suite, execute `uv run -- tox`.

#### Python Compatibility

Use Python features available from Python 3.10 through Python 3.14.
Compatibility with Python 3.9 is not needed.

#### Python Style

Import style: prefer `from package import name` over `import package.name as name`.

Quoting style: prefer single quotes for new code, but do not remove double quotes
from existing code.

#### Python Environment

 * Package manager: `uv` (not pip)
 * Formatter: `uv run -- ruff format`
 * Linter: `uv run -- ruff check`
 * Type checker: `uv run -- mypy --install-types --non-interactive`

### Git Workflows

#### Git Commit Messages

 * Use the present tense.
 * Keep the first line under 50 characters in length.
 * Keep the second line blank.
 * Keep all other lines under 72 characters in length.
 * Reference issue numbers when available.

#### Generating PRs

When generating a PR, follow the instructions in `.github/PULL_REQUEST_TEMPLATE.md`:

 * Add new author names to `mycli/AUTHORS`.
 * Add a new entry to `changelog.md`.

### Code Comments

Keep comments concise and direct.  Use full sentences, ending with a period.

### See Also

See also the file `CONTRIBUTING.md`.

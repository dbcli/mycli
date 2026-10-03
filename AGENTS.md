# Mycli

Rich MySQL terminal client with auto-completion, syntax highlighting, and dataframes.

## Project Structure

    /                                                     # repository root
    ├── .github/                                          # GitHub Actions and configuration
    ├── pyproject.toml                                    # project configuration
    ├── doc/                                              # documentation
    ├── doc/cookbook.md                                   # recipes for how to configure and use mycli
    ├── doc/key_bindings.md                               # documentation of key binding behaviors
    ├── doc/known_bugs.md                                 # documentation of known bugs and limitations
    ├── doc/llm.md                                        # documentation on how to use LLM features
    ├── doc/transforms.md                                 # documentation on how to use dataframe transform/plot features
    ├── doc/screenshots/                                  # screenshots for documentation
    ├── mycli/                                            # application source
    ├── mycli/__init__.py                                 # provides version number
    ├── mycli/app_state.py                                # `AppStateMixin` application state mixin and related functions
    ├── mycli/cli_runner.py                               # connects and dispatches main modes based on CLI arguments
    ├── mycli/client_commands.py                          # special commands which must be registered separately
    ├── mycli/client_connection.py                        # `ClientConnectionMixin` mixin for establishing the database connection
    ├── mycli/client_query.py                             # `ClientQueryMixin` mixin for running queries and refreshing completions
    ├── mycli/client.py                                   # the `MyCli` "god class"
    ├── mycli/compat.py                                   # OS compatibility helpers
    ├── mycli/config.py                                   # configuration file readers and utilities
    ├── mycli/constants.py                                # shared constants
    ├── mycli/main.py                                     # processes CLI arguments
    ├── mycli/main_modes/                                 # main execution paths
    ├── mycli/main_modes/batch.py                         # `--batch` mode
    ├── mycli/main_modes/checkup.py                       # `--checkup` mode
    ├── mycli/main_modes/completions.py                   # `--completions` mode
    ├── mycli/main_modes/execute.py                       # `--execute` mode
    ├── mycli/main_modes/list_dsn.py                      # `--list-dsn` mode
    ├── mycli/main_modes/repl.py                          # interactive REPL mode
    ├── mycli/myclirc                                     # project-level configuration file
    ├── mycli/output.py                                   # `OutputMixin` mixin for feedback and output of query results
    ├── mycli/packages/                                   # application packages
    ├── mycli/packages/completion/completion_engine.py    # implementation of completion suggestions
    ├── mycli/packages/completion/completion_refresher.py # populates a `SQLCompleter` object in a background thread
    ├── mycli/packages/completion/schema_prefetcher.py    # background prefetcher for multi-schema auto-completion
    ├── mycli/packages/completion/sql_completer.py        # finds SQL completion candidates
    ├── mycli/packages/credentials/password_sources.py    # password sources and precedence
    ├── mycli/packages/dataframes/completion.py           # completions for `.|` transforms
    ├── mycli/packages/dataframes/transform.py            # implements `.|` transforms
    ├── mycli/packages/execution/background_runner.py     # run queries in the background, with query state and timing updates
    ├── mycli/packages/execution/sql_execute.py           # `SQLExecute` class and friends
    ├── mycli/packages/integrations/                      # integrations with fzf, Boundary, Kubernetes, macOS, OpenSSH, and Vault
    ├── mycli/packages/prompt_toolkit/fzf_history.py      # uses fzf integration to serach the prompt_toolkit history
    ├── mycli/packages/prompt_toolkit/history.py          # extends the prompt_toolkit history class
    ├── mycli/packages/prompt_toolkit/key_bindings.py     # prompt_toolkit key bindings
    ├── mycli/packages/prompt_toolkit/multiline.py        # prompt_toolkit multiline input
    ├── mycli/packages/prompt_toolkit/style.py            # prompt_toolkit (and Pygments) styles
    ├── mycli/packages/prompt_toolkit/toolbar.py          # prompt_toolkit bottom toolbar
    ├── mycli/packages/prompt_toolkit/utils.py            # general utility functions for prompt_toolkit
    ├── mycli/packages/pygments/mycli_lexer.py            # extends `MySqlLexer` from Pygments
    ├── mycli/packages/redirection/                       # implementation of shell-style redirects
    ├── mycli/packages/special_commands/                  # implementation of mycli special commands
    ├── mycli/packages/sql_result/sql_result.py           # the `SQLResult` dataclass for holding responses
    ├── mycli/packages/tabular_output/                    # extends cli_helper with additional output formats
    ├── mycli/packages/utils/batch_utils.py               # utilities for `--batch` mode
    ├── mycli/packages/utils/cli_utils.py                 # utilities for parsing CLI arguments
    ├── mycli/packages/utils/interactive_utils.py         # utilities for confirming on destructive statements
    ├── mycli/packages/utils/key_binding_utils.py         # handlers for key bindings and related special commands
    ├── mycli/packages/utils/keyring_utils.py             # saved credential utilities
    ├── mycli/packages/utils/path_utils.py                # utilities for files, including completion suggestions
    ├── mycli/packages/utils/sql_utils.py                 # utilities for parsing SQL statements
    ├── mycli/packages/utils/string_utils.py              # generic string utilities
    ├── mycli/resources/completions/                      # shell completions for CLI interface
    ├── mycli/types.py                                    # shared types
    ├── mycli_test/features/                              # behave tests
    ├── mycli_test/myclirc                                # mycli configuration used for tests
    ├── mycli_test/mylogin.cnf                            # `mylogin.cnf` example used for tests
    ├── mycli_test/pytests/                               # pytest tests
    ├── mycli_test/pytests/conftest.py                    # pytest configuration
    └── mycli_test/utils.py                               # shared utilities for tests

## Development

### Python

#### Python Dependency Management

This repo uses `uv` for dependency management. **Always** prefix Python
commands with `uv run`.  Example:

```bash
env -u PYTHONPATH uv run -- python script.py
```

#### Python Typing

This repo uses type annotations which are checked by `mypy`.  **Always** add
type annotations, and always check new code with `env -u PYTHONPATH uv run -- mypy --install-types --non-interactive script.py`.

Use lower-case type annotations such as `tuple`, not upper-case type
annotations such as `Tuple`.

Use `Type | None` instead of `Optional[Type]`.

#### Python Testing

Tests are coordinated by `tox`, and include both `pytest` and `behave` tests.
To run the full test suite, execute `env -u PYTHONPATH uv run -- tox`.

#### Python Compatibility

Use Python features available from Python 3.11 through Python 3.14.
Compatibility with Python 3.9 is not needed.  Compatibility with Python
3.10 is not needed.

#### Python Style

Import style: prefer `from package import name` over `import package.name as name`.

Quoting style: prefer single quotes for new code, but do not remove double quotes
from existing code.

#### Python Environment

 * Package manager: `uv` (not pip)
 * Formatter: `env -u PYTHONPATH uv run -- ruff format`
 * Linter: `env -u PYTHONPATH uv run -- ruff check`
 * Type checker: `env -u PYTHONPATH uv run -- mypy --install-types --non-interactive`

### Git Workflows

#### Git Commit Messages

 * Use the present tense.
 * Keep the first line under 50 characters in length.
 * Keep the second line blank.
 * Keep all other lines under 72 characters in length.
 * Reference issue numbers when available.

#### Generating PRs

When generating a PR, follow the instructions in `.github/PULL_REQUEST_TEMPLATE.md`:

 * Add new author names to `mycli/AUTHORS.txt`.
 * Add a new entry to `changelog.md`.

### Code Comments

Keep comments concise and direct.  Use full sentences, ending with a period.

### See Also

See also the file `CONTRIBUTING.md`.

1.48.0 (2026/01/27)
==============

Features
--------
* Right-align numeric columns, and make the behavior configurable.
* Add completions for stored procedures.
* Escape database completions.
* Offer completions on `CREATE TABLE ... LIKE`.
* Use 0x-style hex literals for binaries in SQL output formats.


Bug Fixes
--------
* Better respect case when `keyword_casing` is `auto`.
* Fix error when selecting from an empty table.
* Let favorite queries contain special commands.
* Render binary values more consistently as hex literals.
* Offer format completions on special command `\Tr`/`redirectformat`.


1.47.0 (2026/01/24)
==============

Features
--------
* Add a `--checkpoint=` argument to log successful queries in batch mode.
* Add `--throttle` option for batch mode.


Bug Fixes
--------
* Fix timediff output when the result is a negative value (#1113).
* Don't offer completions for numeric text.


1.46.0 (2026/01/22)
==============

Features
--------
* Add `--unbuffered` mode which fetches rows as needed, to save memory.
* Default to standards-compliant `utf8mb4` character set.
* Stream input from STDIN to consume less memory, adding `--noninteractive` and `--format=` CLI arguments.
* Remove suggested quoting on completions for identifiers with uppercase.
* Allow table names to be completed with leading schema names.
* Soft deprecate the built-in SSH features.
* Add true fuzzy-match completions with rapidfuzz.


Bug Fixes
--------
* Fix CamelCase fuzzy matching.
* Place special commands first in the list of completion candidates, and remove duplicates.


1.45.0 (2026/01/20)
==============

Features
--------
* Make password options also function as flags. Reworked password logic to prompt user as early as possible (#341).
* More complete and up-to-date set of MySQL reserved words for completions.
* Place exact-leading completions first.
* Allow history file location to be configured.
* Make destructive-warning keywords configurable.
* Smarter fuzzy completion matches.


Bug Fixes
--------
* Respect `--logfile` when using `--execute` or standard input at the shell CLI.
* Gracefully catch Paramiko parsing errors on `--list-ssh-config`.
* Downgrade to Paramiko 3.5.1 to avoid crashing on DSA SSH keys.
* Offer schema name completions in `GRANT ... ON` forms.


1.44.2 (2026/01/13)
==============

Bug Fixes
--------
* Update watch query output to display the correct execution time on all iterations (#763).
* Use correct database (if applicable) when reconnecting after a connection loss (#1437).

Internal
--------
* Create new data class to handle SQL/command results to make further code improvements easier.


1.44.1 (2026/01/10)
==============

Bug Fixes
--------
* Let `sqlparse` accept arbitrarily-large queries.


1.44.0 (2026/01/08)
==============

Features
--------
* Add enum value completions for WHERE/HAVING clauses. (#790)
* Add `show_favorite_query` config option to control query printing when running favorite queries. (#1118)


1.43.1 (2026/01/03)
==============

Bug Fixes
--------
* Prompt for password within SSL-auto retry flow.


1.43.0 (2026/01/02)
==============

Features
--------
* Update query processing functions to allow automatic show_warnings to work for more code paths like DDL.
* Add new ssl_mode config / --ssl-mode CLI option to control SSL connection behavior. This setting will supercede the
  existing --ssl/--no-ssl CLI options, which are deprecated and will be removed in a future release.
* Rework reconnect logic to actually reconnect or create a new connection instead of simply changing the database (#746).
* Configurable string for missing values (NULLs) in outputs.


Bug Fixes
--------
* Update the prompt display logic to handle an edge case where a socket is used without
  a host being parsed from any other method (#707).


Internal
--------
* Refine documentation for Windows.
* Target Python 3.10 for linting.
* Use fully-qualified pymysql exception classes.


1.42.0 (2025/12/20)
==============

Features
--------
* Add support for the automatic displaying of warnings after a SQL statement is executed.
  May be set with the commands \W and \w, in the config file with show_warnings, or
  with --show-warnings/--no-show-warnings on the command line.


Internal
--------
* Improve robustness for flaky tests when publishing.
* Improve type annotations for latest mypy/type stubs.
* Set mypy version more strictly.


1.41.2 (2025/11/24)
==============

Bug Fixes
--------
* Close connection to server properly to avoid "Aborted connection" warnings in server logs.

Internal
--------
* Add ruff to developement dependencies.
* Update contributing guidelines to match GitHub pull request checklist.


1.41.1 (2025/11/15)
==============

Bug Fixes
--------
* Upgrade `click` to v8.3.1, resolving a longstanding pager bug.


Internal
--------
* Include LLM dependencies in tox configuration.


1.41.0 (2025/11/01)
==============

Features
--------
* Make LLM dependencies an optional extra.


Bug Fixes
--------
* Let LLM commands respect show-timing configuration.


Internal
--------
* Add mypy to Pull Request template.
* Enable flake8-bugbear lint rules.
* Fix flaky editor-command tests in CI.
* Require release format of `changelog.md` when making a release.
* Improve type annotations on LLM driver.


1.40.0 (2025/10/14)
==============

Features
--------
* Support reconnecting to mysql server when the server restarts.


Internal
--------
* Test on Python 3.14.
* Switch from pyaes to pycryptodomex as it seems to be more actively maintained.


1.39.1 (2025/10/06)
==============

Bug Fixes
--------
* Don't require `--ssl` argument when other SSL arguments are given.


1.39.0 (2025/09/30)
==============

Features
--------
* Support only Python 3.10+.


Bug Fixes
--------
* Fixes use of incorrect ssl config after retrying connection with prompted password.
* Fix ssl_context always created.


Internal
--------
Typing fix for `pymysql.connect()`.


1.38.4 (2025/09/06)
==============

Bug Fixes
--------
* Limit Alt-R bindings to Emacs mode.
* Fix timing being printed twice.


Internal
--------
* Only read "my" configuration files once, rather than once per call to read_my_cnf_files.


1.38.3 (2025/08/21)
==============

Bug Fixes
--------
* Fix the infinite looping when `\llm` is called without args.


1.38.2 (2025/08/19)
======================

Bug Fixes
--------
* Fix failure to save Favorite Queries.


1.38.1 (2025/08/19)
======================

Bug Fixes
--------
* Partially fix Favorite Query completion crash.


Internal
--------
* Improve CI workflow naming.


1.38.0 (2025/08/16)
======================

Features
--------
* Add LLM support.


Bug Fixes
--------
* Improve missing ssh-extras message.
* Fix repeated control-r in traditional reverse isearch.
* Fix spelling of `ssl-verify-server-cert` option.
* Improve handling of `ssl-verify-server-cert` False values.
* Guard against missing contributors file on startup.
* Friendlier errors on password-file failures.
* Better handle empty-string passwords.
* Permit empty-string passwords at the interactive prompt.


Internal
--------
* Improve pull request template lint commands.
* Complete typehinting the non-test codebase.
* Modernization: conversion to f-strings.
* Modernization: remove more Python 2 compatibility logic.


1.37.1 (2025/07/28)
======================

Internal
--------

* Align LICENSE with SPDX format.
* Fix deprecated `license` specification format in `pyproject.toml`.


1.37.0 (2025/07/28)
======================

Features
--------
* Show username in password prompt.
* Add `mysql` and `mysql_unicode` table formats.


Bug Fixes
--------
* Help Windows installations find a working default pager.


Internal
--------

* Support only Python 3.9+ in `pyproject.toml`.
* Add linting suggestion to pull request template.
* Make CI names and properties more consistent.
* Enable typechecking for most of the non-test codebase.
* CI: turn off fail-fast matrix strategy.
* Remove unused Python 2 compatibility code.
* Also run CI tests without installing SSH extra dependencies.
* Update `cli_helpers` dependency, and list of table formats.


1.36.0 (2025/07/19)
======================

Features
--------
* Make control-r reverse search style configurable.
* Make fzf search key bindings more compatible with traditional isearch.


Bug Fixes
--------

* Better reset after pipe command failures.


Internal
--------

* Add limited typechecking to CI.


1.35.0 (2025/07/18)
======================

Features
--------

* Support chained pipe operators such as `select first_name from users $| grep '^J' $| head -10`.
* Support trailing file redirects after pipe operators, such as `select 10 $| tail -1 $> ten.txt`.


1.34.4 (2025/07/15)
======================

Bug Fixes
--------

* Fix old-style `\pipe_once`.


1.34.3 (2025/07/14)
======================

Bug Fixes
--------

* Use only `communicate()` to communicate with subprocess.


1.34.2 (2025/07/12)
======================

Bug Fixes
--------

* Use plain `print()` to communicate with subprocess.


1.34.1 (2025/07/12)
======================

Internal
--------

* Bump cli_helpers dependency for corrected output formats.


1.34.0 (2025/07/11)
======================

Features
--------

* Post-save command hook for redirected output.

Internal
--------

* Documentation cleanup.
* Bump cli_helpers dependency for more output formats.


1.33.0 (2025/07/07)
======================

Features
--------

* Keybindings to insert current date/datetime.
* Improve feedback when running external commands.
* Independent format for redirected output.
* Trailing shell-style redirect syntax.


Internal
--------

* Remove `requirements-dev.txt` in favor of uv/`pyproject.toml`.


1.32.0 (2025/07/04)
======================

Features
--------

* Support SSL query parameters on DSNs.
* More information and care on KeyboardInterrupt.

Internal
--------

* Work on passing `ruff check` linting.
* Relax expectation for unreliable test.
* Bump sqlglot version to v26 and add rs extras.


1.31.2 (2025/05/01)
===================

Bug Fixes
---------

* Let table-name extraction work on multi-statement inputs.


Internal
--------

* Work on passing `ruff check` linting.
* Remove backward-compatibility hacks.
* Pin more GitHub Actions and add Dependabot support.
* Enable xpassing test.


1.31.1 (2025/04/25)
===================

Internal
--------

* skip style checks on Publish action


1.31.0 (NEVER RELEASED)
===================

Features
--------
* Added explicit error handle to get_password_from_file with EAFP.
* Use the "history" scheme for fzf searches.
* Deduplicate history in fzf searches.
* Add a preview window to fzf history searches.

Internal
--------

* New Project Lead: [Roland Walker](https://github.com/rolandwalker)
* Update sqlparse to <=0.6.0
* Typing/lint fixes.


1.30.0 (2025/04/19)
===================

Features
--------

* DSN specific init-command in myclirc. Fixes (#1195)
* Add `\\g` to force the horizontal output.


1.29.2 (2024/12/11)
===================

Internal
--------

* Exclude tests from the python package.

1.29.1 (2024/12/11)
===================

Internal
--------

* Fix the GH actions to publish a new version.

1.29.0 (NEVER RELEASED)
=======================

Bug Fixes
----------

* fix SSL through SSH jump host by using a true python socket for a tunnel
* Fix mycli crash when connecting to Vitess

Internal
---------

* Modernize to use PEP-621. Use `uv` instead of `pip` in GH actions.
* Remove Python 3.8 and add Python 3.13 in test matrix.

1.28.0 (2024/11/10)
======================

Features
---------

* Added fzf history search functionality. The feature can switch between the old implementation and the new one based on the presence of the fzf binary.

Bug Fixes
----------

* Fixes `Database connection failed: error('unpack requires a buffer of 4 bytes')`
* Only show keyword completions after *
* Enable fuzzy matching for keywords

1.27.2 (2024/04/03)
===================

Bug Fixes
----------

* Don't use default prompt when one is not supplied to the --prompt option.

1.27.1 (2024/03/28)
===================

Bug Fixes
----------

* Don't install tests.
* Do not ignore the socket passed with the -S option, even when no port is passed
* Fix unexpected exception when using dsn without username & password (Thanks: [Will Wang])
* Let the `--prompt` option act normally with its predefined default value

Internal
---------

* paramiko is newer than 2.11.0 now, remove version pinning `cryptography`.
* Drop support for Python 3.7

1.27.0 (2023/08/11)
===================

Features
---------

* Detect TiDB instance, show in the prompt, and use additional keywords.
* Fix the completion order to show more commonly-used keywords at the top.

Bug Fixes
----------

* Better handle empty statements in un/prettify
* Remove vi-mode bindings for prettify/unprettify.
* Honor `\G` when executing from commandline with `-e`.
* Correctly report the version of TiDB.
* Revised `botton` spelling mistakes with `bottom` in `mycli/clitoolbar.py`

1.26.1 (2022/09/01)
===================

Bug Fixes
----------

* Require Python 3.7 in `setup.py`

1.26.0 (2022/09/01)
===================

Features
---------

* Add `--ssl` flag to enable ssl/tls.
* Add `pager` option to `~/.myclirc`, for instance `pager = 'pspg --csv'` (Thanks: [BuonOmo])
* Add prettify/unprettify keybindings to format the current statement using `sqlglot`.

Features
---------

* Add `--tls-version` option to control the tls version used.

Internal
---------

* Pin `cryptography` to suppress `paramiko` warning, helping CI complete and presumably affecting some users.
* Upgrade some dev requirements
* Change tests to always use databases prefixed with 'mycli_' for better security

Bug Fixes
----------

* Support for some MySQL compatible databases, which may not implement connection_id().
* Fix the status command to work with missing 'Flush_commands' (mariadb)
* Ignore the user of the system [myslqd] config.

1.25.0 (2022/04/02)
===================

Features
---------

* Add `beep_after_seconds` option to `~/.myclirc`, to ring the terminal bell after long queries.

1.24.4 (2022/03/30)
===================

Internal
---------

* Upgrade Ubuntu VM for runners as Github has deprecated it

Bug Fixes
----------

* Change in main.py - Replace the `click.get_terminal_size()` with `shutil.get_terminal_size()`

1.24.3 (2022/01/20)
===================

Bug Fixes
----------

* Upgrade cli_helpers to workaround Pygments regression.

1.24.2 (2022/01/11)
===================

Bug Fixes
----------

* Fix autocompletion for more than one JOIN
* Fix the status command when connected to TiDB or other servers that don't implement 'Threads\_connected'
* Pin pygments version to avoid a breaking change

1.24.1
=======

Bug Fixes
---------

* Restore dependency on cryptography for the interactive password prompt

Internal
---------

* Deprecate Python mock

1.24.0
======

Bug Fixes
----------

* Allow `FileNotFound` exception for SSH config files.
* Fix startup error on MySQL < 5.0.22
* Check error code rather than message for Access Denied error
* Fix login with ~/.my.cnf files

Features
---------

* Add `-g` shortcut to option `--login-path`.
* Alt-Enter dispatches the command in multi-line mode.
* Allow to pass a file or FIFO path with --password-file when password is not specified or is failing (as suggested in this best-practice <https://www.netmeister.org/blog/passing-passwords.html>)

Internal
---------

* Remove unused function is_open_quote()
* Use importlib, instead of file links, to locate resources
* Test various host-port combinations in command line arguments
* Switched from Cryptography to pyaes for decrypting mylogin.cnf

1.23.2
======

Bug Fixes
----------

* Ensure `--port` is always an int.

1.23.1
======

Bug Fixes
----------

* Allow `--host` without `--port` to make a TCP connection.

1.23.0
======

Bug Fixes
----------

* Fix config file include logic

Features
---------

* Add an option `--init-command` to execute SQL after connecting (Thanks: [KITAGAWA Yasutaka]).
* Use InputMode.REPLACE_SINGLE
* Add support for ANSI escape sequences for coloring the prompt.
* Allow customization of Pygments SQL syntax-highlighting styles.
* Add a `\clip` special command to copy queries to the system clipboard.
* Add a special command `\pipe_once` to pipe output to a subprocess.
* Add an option `--charset` to set the default charset when connect database.

Bug Fixes
----------

* Fixed compatibility with sqlparse 0.4 (Thanks: [mtorromeo]).
* Fixed iPython magic (Thanks: [mwcm]).
* Send "Connecting to socket" message to the standard error.
* Respect empty string for prompt_continuation via `prompt_continuation = ''` in `.myclirc`
* Fix \once -o to overwrite output whole, instead of line-by-line.
* Dispatch lines ending with `\e` or `\clip` on return, even in multiline mode.
* Restore working local `--socket=<UDS>` (Thanks: [xeron]).
* Allow backtick quoting around the database argument to the `use` command.
* Avoid opening `/dev/tty` when `--no-warn` is given.
* Fixed some typo errors in `README.md`.

1.22.2
======

Bug Fixes
----------

* Make the `pwd` module optional.

1.22.1
======

Bug Fixes
----------

* Fix the breaking change introduced in PyMySQL 0.10.0. (Thanks: [Amjith]).

Features
---------

* Add an option `--ssh-config-host` to read ssh configuration from OpenSSH configuration file.
* Add an option `--list-ssh-config` to list ssh configurations.
* Add an option `--ssh-config-path` to choose ssh configuration path.

Bug Fixes
----------

* Fix specifying empty password with `--password=''` when config file has a password set (Thanks: [Zach DeCook]).

1.21.1
======

Bug Fixes
----------

* Fix broken auto-completion for favorite queries (Thanks: [Amjith]).
* Fix undefined variable exception when running with --no-warn (Thanks: [Georgy Frolov])
* Support setting color for null value (Thanks: [laixintao])

1.21.0
======

Features
---------

* Added DSN alias name as a format specifier to the prompt (Thanks: [Georgy Frolov]).
* Mark `update` without `where`-clause as destructive query (Thanks: [Klaus Wünschel]).
* Added DELIMITER command (Thanks: [Georgy Frolov])
* Added clearer error message when failing to connect to the default socket.
* Extend main.is_dropping_database check with create after delete statement.
* Search `${XDG_CONFIG_HOME}/mycli/myclirc` after `${HOME}/.myclirc` and before `/etc/myclirc` (Thanks: [Takeshi D. Itoh])

Bug Fixes
----------

* Allow \o command more than once per session (Thanks: [Georgy Frolov])
* Fixed crash when the query dropping the current database starts with a comment (Thanks: [Georgy Frolov])

Internal
---------

* deprecate python versions 2.7, 3.4, 3.5; support python 3.8

1.20.1
======

Bug Fixes
----------

* Fix an error when using login paths with an explicit database name (Thanks: [Thomas Roten]).

1.20.0
======

Features
----------

* Auto find alias dsn when `://` not in `database` (Thanks: [QiaoHou Peng]).
* Mention URL encoding as escaping technique for special characters in connection DSN (Thanks: [Aljosha Papsch]).
* Pressing Alt-Enter will introduce a line break. This is a way to break up the query into multiple lines without switching to multi-line mode. (Thanks: [Amjith Ramanujam]).
* Use a generator to stream the output to the pager (Thanks: [Dick Marinus]).

Bug Fixes
----------

* Fix the missing completion for special commands (Thanks: [Amjith Ramanujam]).
* Fix favorites queries being loaded/stored only from/in default config file and not --myclirc (Thanks: [Matheus Rosa])
* Fix automatic vertical output with native syntax style (Thanks: [Thomas Roten]).
* Update `cli_helpers` version, this will remove quotes from batch output like the official client (Thanks: [Dick Marinus])
* Update `setup.py` to no longer require `sqlparse` to be less than 0.3.0 as that just came out and there are no notable changes. ([VVelox])
* workaround for ConfigObj parsing strings containing "," as lists (Thanks: [Mike Palandra])

Internal
---------

* fix unhashable FormattedText from prompt toolkit in unit tests (Thanks: [Dick Marinus]).

1.19.0
======

Internal
---------

* Add Python 3.7 trove classifier (Thanks: [Thomas Roten]).
* Fix pytest in Fedora mock (Thanks: [Dick Marinus]).
* Require `prompt_toolkit>=2.0.6` (Thanks: [Dick Marinus]).

Features
---------

* Add Token.Prompt/Continuation (Thanks: [Dick Marinus]).
* Don't reconnect when switching databases using use (Thanks: [Angelo Lupo]).
* Handle MemoryErrors while trying to pipe in large files and exit gracefully with an error (Thanks: [Amjith Ramanujam])

Bug Fixes
----------

* Enable Ctrl-Z to suspend the app (Thanks: [Amjith Ramanujam]).

1.18.2
======

Bug Fixes
----------

* Fixes database reconnecting feature (Thanks: [Yang Zou]).

Internal
---------

* Update Twine version to 1.12.1 (Thanks: [Thomas Roten]).
* Fix warnings for running tests on Python 3.7 (Thanks: [Dick Marinus]).
* Clean up and add behave logging (Thanks: [Dick Marinus]).

1.18.1
======

Features
---------

* Add Keywords: TINYINT, SMALLINT, MEDIUMINT, INT, BIGINT (Thanks: [QiaoHou Peng]).

Internal
---------

* Update prompt toolkit (Thanks: [Jonathan Slenders], [Irina Truong], [Dick Marinus]).

1.18.0
======

Features
---------

* Display server version in welcome message (Thanks: [Irina Truong]).
* Set `program_name` connection attribute (Thanks: [Dick Marinus]).
* Use `return` to terminate a generator for better Python 3.7 support (Thanks: [Zhongyang Guan]).
* Add `SAVEPOINT` to SQLCompleter (Thanks: [Huachao Mao]).
* Connect using a SSH transport (Thanks: [Dick Marinus]).
* Add `FROM_UNIXTIME` and `UNIX_TIMESTAMP` to SQLCompleter (Thanks: [QiaoHou Peng])
* Search `${PWD}/.myclirc`, then `${HOME}/.myclirc`, lastly `/etc/myclirc` (Thanks: [QiaoHao Peng])

Bug Fixes
----------

* When DSN is used, allow overrides from mycli arguments (Thanks: [Dick Marinus]).
* A DSN without password should be allowed (Thanks: [Dick Marinus])

Bug Fixes
----------

* Convert `sql_format` to unicode strings for py27 compatibility (Thanks: [Dick Marinus]).
* Fixes mycli compatibility with pbr (Thanks: [Thomas Roten]).
* Don't align decimals for `sql_format` (Thanks: [Dick Marinus]).

Internal
---------

* Use fileinput (Thanks: [Dick Marinus]).
* Enable tests for Python 3.7 (Thanks: [Thomas Roten]).
* Remove `*.swp` from gitignore (Thanks: [Dick Marinus]).

1.17.0
=======

Features
----------

* Add `CONCAT` to SQLCompleter and remove unused code (Thanks: [caitinggui])
* Do not quit when aborting a confirmation prompt (Thanks: [Thomas Roten]).
* Add option list-dsn (Thanks: [Frederic Aoustin]).
* Add verbose option for list-dsn, add tests and clean up code (Thanks: [Dick Marinus]).

Bug Fixes
----------

* Add enable_pager to the config file (Thanks: [Frederic Aoustin]).
* Mark `test_sql_output` as a dbtest (Thanks: [Dick Marinus]).
* Don't crash if the log/history file directories don't exist (Thanks: [Thomas Roten]).
* Unquote dsn username and password (Thanks: [Dick Marinus]).
* Output `Password:` prompt to stderr (Thanks: [ushuz]).
* Mark `alter` as a destructive query (Thanks: [Dick Marinus]).
* Quote CSV fields (Thanks: [Thomas Roten]).
* Fix `thanks_picker` (Thanks: [Dick Marinus]).

Internal
---------

* Refactor Destructive Warning behave tests (Thanks: [Dick Marinus]).

1.16.0
=======

Features
---------

* Add DSN aliases to the config file (Thanks: [Frederic Aoustin]).

Bug Fixes
----------

* Do not try to connect to a unix socket on Windows (Thanks: [Thomas Roten]).

1.15.0
=======

Features
---------

* Add sql-update/insert output format. (Thanks: [Dick Marinus]).
* Also complete aliases in WHERE. (Thanks: [Dick Marinus]).

1.14.0
=======

Features
---------

* Add `watch [seconds] query` command to repeat a query every [seconds] seconds (by default 5). (Thanks: [David Caro](https://github.com/Terseus))
* Default to unix socket connection if host and port are unspecified. This simplifies authentication on some systems and matches mysql behaviour.
* Add support for positional parameters to favorite queries. (Thanks: [Scrappy Soft](https://github.com/scrappysoft))

Bug Fixes
----------

* Fix source command for script in current working directory. (Thanks: [Dick Marinus]).
* Fix issue where the `tee` command did not work on Python 2.7 (Thanks: [Thomas Roten]).

Internal Changes
-----------------

* Drop support for Python 3.3 (Thanks: [Thomas Roten]).

* Make tests more compatible between different build environments. (Thanks: [David Caro])
* Merge `_on_completions_refreshed` and `_swap_completer_objects` functions (Thanks: [Dick Marinus]).

1.13.1
=======

Bug Fixes
----------

* Fix keyword completion suggestion for `SHOW` (Thanks: [Thomas Roten]).
* Prevent mycli from crashing when failing to read login path file (Thanks: [Thomas Roten]).

Internal Changes
-----------------

* Make tests ignore user config files (Thanks: [Thomas Roten]).

1.13.0
=======

Features
---------

* Add file name completion for source command (issue #500). (Thanks: [Irina Truong]).

Bug Fixes
----------

* Fix UnicodeEncodeError when editing sql command in external editor (Thanks: Klaus Wünschel).
* Fix MySQL4 version comment retrieval (Thanks: [François Pietka])
* Fix error that occurred when outputting JSON and NULL data (Thanks: [Thomas Roten]).

1.12.1
=======

Bug Fixes
----------

* Prevent missing MySQL help database from causing errors in completions (Thanks: [Thomas Roten]).
* Fix mycli from crashing with small terminal windows under Python 2 (Thanks: [Thomas Roten]).
* Prevent an error from displaying when you drop the current database (Thanks: [Thomas Roten]).

Internal Changes
-----------------

* Use less memory when formatting results for display (Thanks: [Dick Marinus]).
* Preliminary work for a future change in outputting results that uses less memory (Thanks: [Dick Marinus]).

1.12.0
=======

Features
---------

* Add fish-style auto-suggestion from history. (Thanks: [Amjith Ramanujam])

1.11.0
=======

Features
---------

* Handle reserved space for completion menu better in small windows. (Thanks: [Thomas Roten]).
* Display current vi mode in toolbar. (Thanks: [Thomas Roten]).
* Opening an external editor will edit the last-run query. (Thanks: [Thomas Roten]).
* Output once special command. (Thanks: [Dick Marinus]).
* Add special command to show create table statement. (Thanks: [Ryan Smith])
* Display all result sets returned by stored procedures (Thanks: [Thomas Roten]).
* Add current time to prompt options (Thanks: [Thomas Roten]).
* Output status text in a more intuitive way (Thanks: [Thomas Roten]).
* Add colored/styled headers and odd/even rows (Thanks: [Thomas Roten]).
* Keyword completion casing (upper/lower/auto) (Thanks: [Irina Truong]).

Bug Fixes
----------

* Fixed incorrect timekeeping when running queries from a file. (Thanks: [Thomas Roten]).
* Do not display time and empty line for blank queries (Thanks: [Thomas Roten]).
* Fixed issue where quit command would sometimes not work (Thanks: [Thomas Roten]).
* Remove shebang from main.py (Thanks: [Dick Marinus]).
* Only use pager if output doesn't fit. (Thanks: [Dick Marinus]).
* Support tilde user directory for output file names (Thanks: [Thomas Roten]).
* Auto vertical output is a little bit better at its calculations (Thanks: [Thomas Roten]).

Internal Changes
-----------------

* Rename tests/ to test/. (Thanks: [Dick Marinus]).
* Move AUTHORS and SPONSORS to mycli directory. (Thanks: [Terje Røsten] []).
* Switch from pycryptodome to cryptography (Thanks: [Thomas Roten]).
* Add pager wrapper for behave tests (Thanks: [Dick Marinus]).
* Behave test source command (Thanks: [Dick Marinus]).
* Test using behave the tee command (Thanks: [Dick Marinus]).
* Behave fix clean up. (Thanks: [Dick Marinus]).
* Remove output formatter code in favor of CLI Helpers dependency (Thanks: [Thomas Roten]).
* Better handle common before/after scenarios in behave. (Thanks: [Dick Marinus])
* Added a regression test for sqlparse >= 0.2.3 (Thanks: [Dick Marinus]).
* Reverted removal of temporary hack for sqlparse (Thanks: [Dick Marinus]).
* Add setup.py commands to simplify development tasks (Thanks: [Thomas Roten]).
* Add behave tests to tox (Thanks: [Dick Marinus]).
* Add missing @dbtest to tests (Thanks: [Dick Marinus]).
* Standardizes punctuation/grammar for help strings (Thanks: [Thomas Roten]).

1.10.0
=======

Features
---------

* Add ability to specify alternative myclirc file. (Thanks: [Dick Marinus]).
* Add new display formats for pretty printing query results. (Thanks: [Amjith
  Ramanujam], [Dick Marinus], [Thomas Roten]).
* Add logic to shorten the default prompt if it becomes too long once generated. (Thanks: [John Sterling]).

Bug Fixes
----------

* Fix external editor bug (issue #377). (Thanks: [Irina Truong]).
* Fixed bug so that favorite queries can include unicode characters. (Thanks:
  [Thomas Roten]).
* Fix requirements and remove old compatibility code (Thanks: [Dick Marinus])
* Fix bug where mycli would not start due to the thanks/credit intro text.
  (Thanks: [Thomas Roten]).
* Use pymysql default conversions (issue #375). (Thanks: [Dick Marinus]).

Internal Changes
-----------------

* Upload mycli distributions in a safer manner (using twine). (Thanks: [Thomas
  Roten]).
* Test mycli using pexpect/python-behave (Thanks: [Dick Marinus]).
* Run pep8 checks in travis (Thanks: [Irina Truong]).
* Remove temporary hack for sqlparse (Thanks: [Dick Marinus]).

1.9.0
======

Features
---------

* Add tee/notee commands for outputing results to a file. (Thanks: [Dick Marinus]).
* Add date, port, and whitespace options to prompt configuration. (Thanks: [Matheus Rosa]).
* Allow user to specify LESS pager flags. (Thanks: [John Sterling]).
* Add support for auto-reconnect. (Thanks: [Jialong Liu]).
* Add CSV batch output. (Thanks: [Matheus Rosa]).
* Add `auto_vertical_output` config to myclirc. (Thanks: [Matheus Rosa]).
* Improve Fedora install instructions. (Thanks: [Dick Marinus]).

Bug Fixes
----------

* Fix crashes occuring from commands starting with #. (Thanks: [Zhidong]).
* Fix broken PyMySQL link in README. (Thanks: [Daniël van Eeden]).
* Add various missing keywords for highlighting and autocompletion. (Thanks: [zer09]).
* Add the missing REGEXP keyword for highlighting and autocompletion. (Thanks: [cxbig]).
* Fix duplicate username entries in completion list. (Thanks: [John Sterling]).
* Remove extra spaces in TSV table format output. (Thanks: [Dick Marinus]).
* Kill running query when interrupted via Ctrl-C. (Thanks: [chainkite]).
* Read the `smart_completion` config from myclirc. (Thanks: [Thomas Roten]).

Internal Changes
-----------------

* Improve handling of test database credentials. (Thanks: [Dick Marinus]).
* Add Python 3.6 to test environments and PyPI metadata. (Thanks: [Thomas Roten]).
* Drop Python 2.6 support. (Thanks: [Thomas Roten]).
* Swap pycrypto dependency for pycryptodome. (Thanks: [Michał Górny]).
* Bump sqlparse version so pgcli and mycli can be installed together. (Thanks: [darikg]).

1.8.1
======

Bug Fixes
----------

* Remove duplicate listing of DISTINCT keyword. (Thanks: [Amjith Ramanujam]).
* Add an try/except for AS keyword crash. (Thanks: [Amjith Ramanujam]).
* Support python-sqlparse 0.2. (Thanks: [Dick Marinus]).
* Fallback to the raw object for invalid time values. (Thanks: [Amjith Ramanujam]).
* Reset the show items when completion is refreshed. (Thanks: [Amjith Ramanujam]).

Internal Changes
-----------------

* Make the dependency of sqlparse slightly more liberal. (Thanks: [Amjith Ramanujam]).

1.8.0
======

Features
---------

* Add support for --execute/-e commandline arg. (Thanks: [Matheus Rosa]).
* Add `less_chatty` config option to skip the intro messages. (Thanks: [Scrappy Soft]).
* Support `MYCLI_HISTFILE` environment variable to specify where to write the history file. (Thanks: [Scrappy Soft]).
* Add `prompt_continuation` config option to allow configuring the continuation prompt for multi-line queries. (Thanks: [Scrappy Soft]).
* Display login-path instead of host in prompt. (Thanks: [Irina Truong]).

Bug Fixes
----------

* Pin sqlparse to version 0.1.19 since the new version is breaking completion. (Thanks: [Amjith Ramanujam]).
* Remove unsupported keywords. (Thanks: [Matheus Rosa]).
* Fix completion suggestion inside functions with operands. (Thanks: [Irina Truong]).

1.7.0
======

Features
---------

* Add stdin batch mode. (Thanks: [Thomas Roten]).
* Add warn/no-warn command-line options. (Thanks: [Thomas Roten]).
* Upgrade sqlparse dependency to 0.1.19. (Thanks: [Amjith Ramanujam]).
* Update features list in README.md. (Thanks: [Matheus Rosa]).
* Remove extra \n in features list in README.md. (Thanks: [Matheus Rosa]).

Bug Fixes
----------

* Enable history search via <C-r>. (Thanks: [Amjith Ramanujam]).

Internal Changes
-----------------

* Upgrade `prompt_toolkit` to 1.0.0. (Thanks: [Jonathan Slenders])

1.6.0
======

Features
---------

* Change continuation prompt for multi-line mode to match default mysql.
* Add `status` command to match mysql's `status` command. (Thanks: [Thomas Roten]).
* Add SSL support for `mycli`. (Thanks: [Artem Bezsmertnyi]).
* Add auto-completion and highlight support for OFFSET keyword. (Thanks: [Matheus Rosa]).
* Add support for `MYSQL_TEST_LOGIN_FILE` env variable to specify alternate login file. (Thanks: [Thomas Roten]).
* Add support for `--auto-vertical-output` to automatically switch to vertical output if the output doesn't fit in the table format.
* Add support for system-wide config. Now /etc/myclirc will be honored. (Thanks: [Thomas Roten]).
* Add support for `nopager` and `\n` to turn off the pager. (Thanks: [Thomas Roten]).
* Add support for `--local-infile` command-line option. (Thanks: [Thomas Roten]).

Bug Fixes
----------

* Remove -S from `less` option which was clobbering the scroll back in history. (Thanks: [Thomas Roten]).
* Make system command work with Python 3. (Thanks: [Thomas Roten]).
* Support \G terminator for \f queries. (Thanks: [Terseus]).

Internal Changes
-----------------

* Upgrade `prompt_toolkit` to 0.60.
* Add Python 3.5 to test environments. (Thanks: [Thomas Roten]).
* Remove license meta-data. (Thanks: [Thomas Roten]).
* Skip binary tests if PyMySQL version does not support it. (Thanks: [Thomas Roten]).
* Refactor pager handling. (Thanks: [Thomas Roten])
* Capture warnings to log file. (Thanks: [Mikhail Borisov]).
* Make `syntax_style` a tiny bit more intuitive. (Thanks: [Phil Cohen]).

1.5.2
======

Bug Fixes
----------

* Protect against port number being None when no port is specified in command line.

1.5.1
======

Bug Fixes
----------

* Cast the value of port read from my.cnf to int.

1.5.0
======

Features
---------

* Make a config option to enable `audit_log`. (Thanks: [Matheus Rosa]).
* Add support for reading .mylogin.cnf to get user credentials. (Thanks: [Thomas Roten]).
  This feature is only available when `pycrypto` package is installed.
* Register the special command `prompt` with the `\R` as alias. (Thanks: [Matheus Rosa]).
  Users can now change the mysql prompt at runtime using `prompt` command.
  eg:

  ```
  mycli> prompt \u@\h>
  Changed prompt format to \u@\h>
  Time: 0.001s
  amjith@localhost>
  ```

* Perform completion refresh in a background thread. Now mycli can handle
  databases with thousands of tables without blocking.
* Add support for `system` command. (Thanks: [Matheus Rosa]).
  Users can now run a system command from within mycli as follows:

  ```
  amjith@localhost:(none)>system cat tmp.sql
  select 1;
  select * from django_migrations;
  ```

* Caught and hexed binary fields in MySQL. (Thanks: [Daniel West]).
  Geometric fields stored in a database will be displayed as hexed strings.
* Treat enter key as tab when the suggestion menu is open. (Thanks: [Matheus Rosa])
* Add "delete" and "truncate" as destructive commands. (Thanks: [Martijn Engler]).
* Change \dt syntax to add an optional table name. (Thanks: [Shoma Suzuki]).
  `\dt [tablename]` will describe the columns in a table.
* Add TRANSACTION related keywords.
* Treat DESC and EXPLAIN as DESCRIBE. (Thanks: [spacewander]).

Bug Fixes
----------

* Fix the removal of whitespace from table output.
* Add ability to make suggestions for compound join clauses. (Thanks: [Matheus Rosa]).
* Fix the incorrect reporting of command time.
* Add type validation for port argument. (Thanks [Matheus Rosa])

Internal Changes
-----------------

* Make pycrypto optional and only install it in \*nix systems. (Thanks: [Irina Truong]).
* Add badge for PyPI version to README. (Thanks: [Shoma Suzuki]).
* Updated release script with a --dry-run and --confirm-steps option. (Thanks: [Irina Truong]).
* Adds support for PyMySQL 0.6.2 and above. This is useful for debian package builders. (Thanks: [Thomas Roten]).
* Disable click warning.

1.4.0
======

Features
---------

* Add `source` command. This allows running sql statement from a file.

  eg:

  ```
  mycli> source filename.sql
  ```

* Added a config option to make the warning before destructive commands optional. (Thanks: [Daniel West](https://github.com/danieljwest))

  In the config file ~/.myclirc set `destructive_warning = False` which will
  disable the warning before running `DROP` commands.

* Add completion support for CHANGE TO and other master/slave commands. This is
  still preliminary and it will be enhanced in the future.

* Add custom styles to color the menus and toolbars.

* Upgrade `prompt_toolkit` to 0.46. (Thanks: [Jonathan Slenders])

  Multi-line queries are automatically indented.

Bug Fixes
----------

* Fix keyword completion after the `WHERE` clause.
* Add `\g` and `\G` as valid query terminators. Previously in multi-line mode
  ending a query with a `\G` wouldn't run the query. This is now fixed.

1.3.0
======

Features
---------

* Add a new special command (\T) to change the table format on the fly. (Thanks: [Jonathan Bruno](https://github.com/brewneaux))
  eg:

  ```
  mycli> \T tsv
  ```

* Add `--defaults-group-suffix` to the command line. This lets the user specify
  a group to use in the my.cnf files. (Thanks: [Irina Truong](http://github.com/j-bennet))

  In the my.cnf file a user can specify credentials for different databases and
  invoke mycli with the group name to use the appropriate credentials.
  eg:

  ```
  # my.cnf
  [client]
  user   = 'root'
  socket = '/tmp/mysql.sock'
  pager = 'less -RXSF'
  database = 'account'

  [clientamjith]
  user     = 'amjith'
  database  = 'user_management'

  $ mycli --defaults-group-suffix=amjith   # uses the [clientamjith] section in my.cnf
  ```

* Add `--defaults-file` option to the command line. This allows specifying a
  `my.cnf` to use at launch. This also makes it play nice with mysql sandbox.

* Make `-p` and `--password` take the password in commandline. This makes mycli
  a drop in replacement for mysql.

1.2.0
======

Features
---------

* Add support for wider completion menus in the config file.

  Add `wider_completion_menu = True` in the config file (~/.myclirc) to enable this feature.

Bug Fixes
---------

* Prevent Ctrl-C from quitting mycli while the pager is active.
* Refresh auto-completions after the database is changed via a CONNECT command.

Internal Changes
-----------------

* Upgrade `prompt_toolkit` dependency version to 0.45.
* Added Travis CI to run the tests automatically.

1.1.1
======

Bug Fixes
----------

* Change dictonary comprehension used in mycnf reader to list comprehension to make it compatible with Python 2.6.

1.1.0
======

Features
---------

* Fuzzy completion is now case-insensitive. (Thanks: [bjarnagin](https://github.com/bjarnagin))
* Added new-line (`\n`) to the list of special characters to use in prompt. (Thanks: [brewneaux](https://github.com/brewneaux))
* Honor the `pager` setting in my.cnf files. (Thanks: [Irina Truong](http://github.com/j-bennet))

Bug Fixes
----------

* Fix a crashing bug in completion engine for cross joins.
* Make `<null>` value consistent between tabular and vertical output.

Internal Changes
-----------------

* Changed pymysql version to be greater than 0.6.6.
* Upgrade `prompt_toolkit` version to 0.42. (Thanks: [Yasuhiro Matsumoto](https://github.com/mattn))
* Removed the explicit dependency on six.

2015/06/10
===========

Features
---------

* Customizable prompt. (Thanks [Steve Robbins](https://github.com/steverobbins))
* Make `\G` formatting to behave more like mysql.

Bug Fixes
----------

* Formatting issue in \G for really long column values.

2015/06/07
===========

Features
---------

* Upgrade `prompt_toolkit` to 0.38. This improves the performance of pasting long queries.
* Add support for reading my.cnf files.
* Add editor command \e.
* Replace ConfigParser with ConfigObj.
* Add \dt to show all tables.
* Add fuzzy completion for table names and column names.
* Automatically reconnect when connection is lost to the database.

Bug Fixes
----------

* Fix a bug with reconnect failure.
* Fix the issue with `use` command not changing the prompt.
* Fix the issue where `\\r` shortcut was not recognized.

2015/05/24
==========

Features
---------

* Add support for connecting via socket.
* Add completion for SQL functions.
* Add completion support for SHOW statements.
* Made the timing of sql statements human friendly.
* Automatically prompt for a password if needed.

Bug Fixes
----------

* Fixed the installation issues with PyMySQL dependency on case-sensitive file systems.

[Amjith Ramanujam]: https://blog.amjith.com
[Artem Bezsmertnyi]: https://github.com/mrdeathless
[BuonOmo]: https://github.com/BuonOmo
[Daniel West]: http://github.com/danieljwest
[Dick Marinus]: https://github.com/meeuw
[François Pietka]: https://github.com/fpietka
[Frederic Aoustin]: https://github.com/fraoustin
[Georgy Frolov]: https://github.com/pasenor
[Irina Truong]: https://github.com/j-bennet
[Jonathan Slenders]: https://github.com/jonathanslenders
[laixintao]: https://github.com/laixintao
[Martijn Engler]: https://github.com/martijnengler
[Matheus Rosa]:  https://github.com/mdsrosa
[Mikhail Borisov]: https://github.com/borman
[mtorromeo]: https://github.com/mtorromeo
[mwcm]: https://github.com/mwcm
[Phil Cohen]: https://github.com/phlipper
[Scrappy Soft]: https://github.com/scrappysoft
[Shoma Suzuki]: https://github.com/shoma
[spacewander]: https://github.com/spacewander
[Terseus]: https://github.com/Terseus
[Thomas Roten]: https://github.com/tsroten
[xeron]: https://github.com/xeron
[Zach DeCook]: https://zachdecook.com
[Will Wang]: https://github.com/willww64

1.20.0
======

Features:
----------
* Auto find alias dsn when `://` not in `database` (Thanks: [QiaoHou Peng]).
* Mention URL encoding as escaping technique for special characters in connection DSN (Thanks: [Aljosha Papsch]).
* Pressing Alt-Enter will introduce a line break. This is a way to break up the query into multiple lines without switching to multi-line mode. (Thanks: [Amjith Ramanujam]).
* Use a generator to stream the output to the pager (Thanks: [Dick Marinus]).

Bug Fixes:
----------

* Fix the missing completion for special commands (Thanks: [Amjith Ramanujam]).
* Fix favorites queries being loaded/stored only from/in default config file and not --myclirc (Thanks: [Matheus Rosa])
* Fix automatic vertical output with native syntax style (Thanks: [Thomas Roten]).
* Update `cli_helpers` version, this will remove quotes from batch output like the official client (Thanks: [Dick Marinus])
* Update `setup.py` to no longer require `sqlparse` to be less than 0.3.0 as that just came out and there are no notable changes. ([VVelox])
* workaround for ConfigObj parsing strings containing "," as lists (Thanks: [Mike Palandra])

Internal:
---------
* fix unhashable FormattedText from prompt toolkit in unit tests (Thanks: [Dick Marinus]).

1.19.0
======

Internal:
---------

* Add Python 3.7 trove classifier (Thanks: [Thomas Roten]).
* Fix pytest in Fedora mock (Thanks: [Dick Marinus]).
* Require `prompt_toolkit>=2.0.6` (Thanks: [Dick Marinus]).

Features:
---------

* Add Token.Prompt/Continuation (Thanks: [Dick Marinus]).
* Don't reconnect when switching databases using use (Thanks: [Angelo Lupo]).
* Handle MemoryErrors while trying to pipe in large files and exit gracefully with an error (Thanks: [Amjith Ramanujam])

Bug Fixes:
----------

* Enable Ctrl-Z to suspend the app (Thanks: [Amjith Ramanujam]).

1.18.2
======

Bug Fixes:
----------

* Fixes database reconnecting feature (Thanks: [Yang Zou]).

Internal:
---------

* Update Twine version to 1.12.1 (Thanks: [Thomas Roten]).
* Fix warnings for running tests on Python 3.7 (Thanks: [Dick Marinus]).
* Clean up and add behave logging (Thanks: [Dick Marinus]).

1.18.1
======

Features:
---------

* Add Keywords: TINYINT, SMALLINT, MEDIUMINT, INT, BIGINT (Thanks: [QiaoHou Peng]).

Internal:
---------

* Update prompt toolkit (Thanks: [Jonathan Slenders], [Irina Truong], [Dick Marinus]).

1.18.0
======

Features:
---------

* Display server version in welcome message (Thanks: [Irina Truong]).
* Set `program_name` connection attribute (Thanks: [Dick Marinus]).
* Use `return` to terminate a generator for better Python 3.7 support (Thanks: [Zhongyang Guan]).
* Add `SAVEPOINT` to SQLCompleter (Thanks: [Huachao Mao]).
* Connect using a SSH transport (Thanks: [Dick Marinus]).
* Add `FROM_UNIXTIME` and `UNIX_TIMESTAMP` to SQLCompleter (Thanks: [QiaoHou Peng])
* Search `${PWD}/.myclirc`, then `${HOME}/.myclirc`, lastly `/etc/myclirc` (Thanks: [QiaoHao Peng])

Bug Fixes:
----------

* When DSN is used, allow overrides from mycli arguments (Thanks: [Dick Marinus]).
* A DSN without password should be allowed (Thanks: [Dick Marinus])

Bug Fixes:
----------

* Convert `sql_format` to unicode strings for py27 compatibility (Thanks: [Dick Marinus]).
* Fixes mycli compatibility with pbr (Thanks: [Thomas Roten]).
* Don't align decimals for `sql_format` (Thanks: [Dick Marinus]).

Internal:
---------

* Use fileinput (Thanks: [Dick Marinus]).
* Enable tests for Python 3.7 (Thanks: [Thomas Roten]).
* Remove `*.swp` from gitignore (Thanks: [Dick Marinus]).

1.17.0:
=======

Features:
----------

* Add `CONCAT` to SQLCompleter and remove unused code (Thanks: [caitinggui])
* Do not quit when aborting a confirmation prompt (Thanks: [Thomas Roten]).
* Add option list-dsn (Thanks: [Frederic Aoustin]).
* Add verbose option for list-dsn, add tests and clean up code (Thanks: [Dick Marinus]).

Bug Fixes:
----------

* Add enable_pager to the config file (Thanks: [Frederic Aoustin]).
* Mark `test_sql_output` as a dbtest (Thanks: [Dick Marinus]).
* Don't crash if the log/history file directories don't exist (Thanks: [Thomas Roten]).
* Unquote dsn username and password (Thanks: [Dick Marinus]).
* Output `Password:` prompt to stderr (Thanks: [ushuz]).
* Mark `alter` as a destructive query (Thanks: [Dick Marinus]).
* Quote CSV fields (Thanks: [Thomas Roten]).
* Fix `thanks_picker` (Thanks: [Dick Marinus]).

Internal:
---------

* Refactor Destructive Warning behave tests (Thanks: [Dick Marinus]).


1.16.0:
=======

Features:
---------

* Add DSN aliases to the config file (Thanks: [Frederic Aoustin]).

Bug Fixes:
----------

* Do not try to connect to a unix socket on Windows (Thanks: [Thomas Roten]).

1.15.0:
=======

Features:
---------

* Add sql-update/insert output format. (Thanks: [Dick Marinus]).
* Also complete aliases in WHERE. (Thanks: [Dick Marinus]).

1.14.0:
=======

Features:
---------

* Add `watch [seconds] query` command to repeat a query every [seconds] seconds (by default 5). (Thanks: [David Caro](https://github.com/Terseus))
* Default to unix socket connection if host and port are unspecified. This simplifies authentication on some systems and matches mysql behaviour.
* Add support for positional parameters to favorite queries. (Thanks: [Scrappy Soft](https://github.com/scrappysoft))

Bug Fixes:
----------

* Fix source command for script in current working directory. (Thanks: [Dick Marinus]).
* Fix issue where the `tee` command did not work on Python 2.7 (Thanks: [Thomas Roten]).

Internal Changes:
-----------------

* Drop support for Python 3.3 (Thanks: [Thomas Roten]).

* Make tests more compatible between different build environments. (Thanks: [David Caro])
* Merge `_on_completions_refreshed` and `_swap_completer_objects` functions (Thanks: [Dick Marinus]).

1.13.1:
=======

Bug Fixes:
----------

* Fix keyword completion suggestion for `SHOW` (Thanks: [Thomas Roten]).
* Prevent mycli from crashing when failing to read login path file (Thanks: [Thomas Roten]).

Internal Changes:
-----------------

* Make tests ignore user config files (Thanks: [Thomas Roten]).

1.13.0:
=======

Features:
---------

* Add file name completion for source command (issue #500). (Thanks: [Irina Truong]).

Bug Fixes:
----------

* Fix UnicodeEncodeError when editing sql command in external editor (Thanks: Klaus Wünschel).
* Fix MySQL4 version comment retrieval (Thanks: [François Pietka])
* Fix error that occurred when outputting JSON and NULL data (Thanks: [Thomas Roten]).

1.12.1:
=======

Bug Fixes:
----------

* Prevent missing MySQL help database from causing errors in completions (Thanks: [Thomas Roten]).
* Fix mycli from crashing with small terminal windows under Python 2 (Thanks: [Thomas Roten]).
* Prevent an error from displaying when you drop the current database (Thanks: [Thomas Roten]).

Internal Changes:
-----------------

* Use less memory when formatting results for display (Thanks: [Dick Marinus]).
* Preliminary work for a future change in outputting results that uses less memory (Thanks: [Dick Marinus]).

1.12.0:
=======

Features:
---------

* Add fish-style auto-suggestion from history. (Thanks: [Amjith Ramanujam])


1.11.0:
=======

Features:
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

Bug Fixes:
----------

* Fixed incorrect timekeeping when running queries from a file. (Thanks: [Thomas Roten]).
* Do not display time and empty line for blank queries (Thanks: [Thomas Roten]).
* Fixed issue where quit command would sometimes not work (Thanks: [Thomas Roten]).
* Remove shebang from main.py (Thanks: [Dick Marinus]).
* Only use pager if output doesn't fit. (Thanks: [Dick Marinus]).
* Support tilde user directory for output file names (Thanks: [Thomas Roten]).
* Auto vertical output is a little bit better at its calculations (Thanks: [Thomas Roten]).

Internal Changes:
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

1.10.0:
=======

Features:
---------

* Add ability to specify alternative myclirc file. (Thanks: [Dick Marinus]).
* Add new display formats for pretty printing query results. (Thanks: [Amjith
  Ramanujam], [Dick Marinus], [Thomas Roten]).
* Add logic to shorten the default prompt if it becomes too long once generated. (Thanks: [John Sterling]).

Bug Fixes:
----------

* Fix external editor bug (issue #377). (Thanks: [Irina Truong]).
* Fixed bug so that favorite queries can include unicode characters. (Thanks:
  [Thomas Roten]).
* Fix requirements and remove old compatibility code (Thanks: [Dick Marinus])
* Fix bug where mycli would not start due to the thanks/credit intro text.
  (Thanks: [Thomas Roten]).
* Use pymysql default conversions (issue #375). (Thanks: [Dick Marinus]).

Internal Changes:
-----------------

* Upload mycli distributions in a safer manner (using twine). (Thanks: [Thomas
  Roten]).
* Test mycli using pexpect/python-behave (Thanks: [Dick Marinus]).
* Run pep8 checks in travis (Thanks: [Irina Truong]).
* Remove temporary hack for sqlparse (Thanks: [Dick Marinus]).

1.9.0:
======

Features:
---------

* Add tee/notee commands for outputing results to a file. (Thanks: [Dick Marinus]).
* Add date, port, and whitespace options to prompt configuration. (Thanks: [Matheus Rosa]).
* Allow user to specify LESS pager flags. (Thanks: [John Sterling]).
* Add support for auto-reconnect. (Thanks: [Jialong Liu]).
* Add CSV batch output. (Thanks: [Matheus Rosa]).
* Add `auto_vertical_output` config to myclirc. (Thanks: [Matheus Rosa]).
* Improve Fedora install instructions. (Thanks: [Dick Marinus]).

Bug Fixes:
----------

* Fix crashes occuring from commands starting with #. (Thanks: [Zhidong]).
* Fix broken PyMySQL link in README. (Thanks: [Daniël van Eeden]).
* Add various missing keywords for highlighting and autocompletion. (Thanks: [zer09]).
* Add the missing REGEXP keyword for highlighting and autocompletion. (Thanks: [cxbig]).
* Fix duplicate username entries in completion list. (Thanks: [John Sterling]).
* Remove extra spaces in TSV table format output. (Thanks: [Dick Marinus]).
* Kill running query when interrupted via Ctrl-C. (Thanks: [chainkite]).
* Read the `smart_completion` config from myclirc. (Thanks: [Thomas Roten]).

Internal Changes:
-----------------

* Improve handling of test database credentials. (Thanks: [Dick Marinus]).
* Add Python 3.6 to test environments and PyPI metadata. (Thanks: [Thomas Roten]).
* Drop Python 2.6 support. (Thanks: [Thomas Roten]).
* Swap pycrypto dependency for pycryptodome. (Thanks: [Michał Górny]).
* Bump sqlparse version so pgcli and mycli can be installed together. (Thanks: [darikg]).

1.8.1:
======

Bug Fixes:
----------
* Remove duplicate listing of DISTINCT keyword. (Thanks: [Amjith Ramanujam]).
* Add an try/except for AS keyword crash. (Thanks: [Amjith Ramanujam]).
* Support python-sqlparse 0.2. (Thanks: [Dick Marinus]).
* Fallback to the raw object for invalid time values. (Thanks: [Amjith Ramanujam]).
* Reset the show items when completion is refreshed. (Thanks: [Amjith Ramanujam]).

Internal Changes:
-----------------
* Make the dependency of sqlparse slightly more liberal. (Thanks: [Amjith Ramanujam]).

1.8.0:
======

Features:
---------

* Add support for --execute/-e commandline arg. (Thanks: [Matheus Rosa]).
* Add `less_chatty` config option to skip the intro messages. (Thanks: [Scrappy Soft]).
* Support `MYCLI_HISTFILE` environment variable to specify where to write the history file. (Thanks: [Scrappy Soft]).
* Add `prompt_continuation` config option to allow configuring the continuation prompt for multi-line queries. (Thanks: [Scrappy Soft]).
* Display login-path instead of host in prompt. (Thanks: [Irina Truong]).

Bug Fixes:
----------

* Pin sqlparse to version 0.1.19 since the new version is breaking completion. (Thanks: [Amjith Ramanujam]).
* Remove unsupported keywords. (Thanks: [Matheus Rosa]).
* Fix completion suggestion inside functions with operands. (Thanks: [Irina Truong]).

1.7.0:
======

Features:
---------

* Add stdin batch mode. (Thanks: [Thomas Roten]).
* Add warn/no-warn command-line options. (Thanks: [Thomas Roten]).
* Upgrade sqlparse dependency to 0.1.19. (Thanks: [Amjith Ramanujam]).
* Update features list in README.md. (Thanks: [Matheus Rosa]).
* Remove extra \n in features list in README.md. (Thanks: [Matheus Rosa]).

Bug Fixes:
----------

* Enable history search via <C-r>. (Thanks: [Amjith Ramanujam]).

Internal Changes:
-----------------

* Upgrade `prompt_toolkit` to 1.0.0. (Thanks: [Jonathan Slenders])

1.6.0:
======

Features:
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

Bug Fixes:
----------

* Remove -S from `less` option which was clobbering the scroll back in history. (Thanks: [Thomas Roten]).
* Make system command work with Python 3. (Thanks: [Thomas Roten]).
* Support \G terminator for \f queries. (Thanks: [Terseus]).

Internal Changes:
-----------------

* Upgrade `prompt_toolkit` to 0.60.
* Add Python 3.5 to test environments. (Thanks: [Thomas Roten]).
* Remove license meta-data. (Thanks: [Thomas Roten]).
* Skip binary tests if PyMySQL version does not support it. (Thanks: [Thomas Roten]).
* Refactor pager handling. (Thanks: [Thomas Roten])
* Capture warnings to log file. (Thanks: [Mikhail Borisov]).
* Make `syntax_style` a tiny bit more intuitive. (Thanks: [Phil Cohen]).

1.5.2:
======

Bug Fixes:
----------

* Protect against port number being None when no port is specified in command line.

1.5.1:
======

Bug Fixes:
----------

* Cast the value of port read from my.cnf to int.

1.5.0:
======

Features:
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

Bug Fixes:
----------

* Fix the removal of whitespace from table output.
* Add ability to make suggestions for compound join clauses. (Thanks: [Matheus Rosa]).
* Fix the incorrect reporting of command time.
* Add type validation for port argument. (Thanks [Matheus Rosa])

Internal Changes:
-----------------
* Make pycrypto optional and only install it in \*nix systems. (Thanks: [Irina Truong]).
* Add badge for PyPI version to README. (Thanks: [Shoma Suzuki]).
* Updated release script with a --dry-run and --confirm-steps option. (Thanks: [Irina Truong]).
* Adds support for PyMySQL 0.6.2 and above. This is useful for debian package builders. (Thanks: [Thomas Roten]).
* Disable click warning.

1.4.0:
======

Features:
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

Bug Fixes:
----------

* Fix keyword completion after the `WHERE` clause.
* Add `\g` and `\G` as valid query terminators. Previously in multi-line mode
  ending a query with a `\G` wouldn't run the query. This is now fixed.

1.3.0:
======

Features:
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

1.2.0:
======

Features:
---------

* Add support for wider completion menus in the config file.

  Add `wider_completion_menu = True` in the config file (~/.myclirc) to enable this feature.

Bug Fixes:
---------

* Prevent Ctrl-C from quitting mycli while the pager is active.
* Refresh auto-completions after the database is changed via a CONNECT command.

Internal Changes:
-----------------

* Upgrade `prompt_toolkit` dependency version to 0.45.
* Added Travis CI to run the tests automatically.

1.1.1:
======

Bug Fixes:
----------

* Change dictonary comprehension used in mycnf reader to list comprehension to make it compatible with Python 2.6.


1.1.0:
======

Features:
---------

* Fuzzy completion is now case-insensitive. (Thanks: [bjarnagin](https://github.com/bjarnagin))
* Added new-line (`\n`) to the list of special characters to use in prompt. (Thanks: [brewneaux](https://github.com/brewneaux))
* Honor the `pager` setting in my.cnf files. (Thanks: [Irina Truong](http://github.com/j-bennet))

Bug Fixes:
----------

* Fix a crashing bug in completion engine for cross joins.
* Make `<null>` value consistent between tabular and vertical output.

Internal Changes:
-----------------

* Changed pymysql version to be greater than 0.6.6.
* Upgrade `prompt_toolkit` version to 0.42. (Thanks: [Yasuhiro Matsumoto](https://github.com/mattn))
* Removed the explicit dependency on six.

2015/06/10:
===========

Features:
---------

* Customizable prompt. (Thanks [Steve Robbins](https://github.com/steverobbins))
* Make `\G` formatting to behave more like mysql.

Bug Fixes:
----------

* Formatting issue in \G for really long column values.


2015/06/07:
===========

Features:
---------

* Upgrade `prompt_toolkit` to 0.38. This improves the performance of pasting long queries.
* Add support for reading my.cnf files.
* Add editor command \e.
* Replace ConfigParser with ConfigObj.
* Add \dt to show all tables.
* Add fuzzy completion for table names and column names.
* Automatically reconnect when connection is lost to the database.

Bug Fixes:
----------

* Fix a bug with reconnect failure.
* Fix the issue with `use` command not changing the prompt.
* Fix the issue where `\\r` shortcut was not recognized.


2015/05/24
==========

Features:
---------

* Add support for connecting via socket.
* Add completion for SQL functions.
* Add completion support for SHOW statements.
* Made the timing of sql statements human friendly.
* Automatically prompt for a password if needed.

Bug Fixes:
----------
* Fixed the installation issues with PyMySQL dependency on case-sensitive file systems.

[Daniel West]: http://github.com/danieljwest
[Irina Truong]: https://github.com/j-bennet
[Amjith Ramanujam]: https://blog.amjith.com
[Kacper Kwapisz]: https://github.com/KKKas
[Martijn Engler]: https://github.com/martijnengler
[Matheus Rosa]:  https://github.com/mdsrosa
[Shoma Suzuki]: https://github.com/shoma
[spacewander]: https://github.com/spacewander
[Thomas Roten]: https://github.com/tsroten
[Artem Bezsmertnyi]: https://github.com/mrdeathless
[Mikhail Borisov]: https://github.com/borman
[Casper Langemeijer]: Casper Langemeijer
[Lennart Weller]: https://github.com/lhw
[Phil Cohen]: https://github.com/phlipper
[Terseus]: https://github.com/Terseus
[William GARCIA]: https://github.com/willgarcia
[Jonathan Slenders]: https://github.com/jonathanslenders
[Casper Langemeijer]: https://github.com/langemeijer
[Scrappy Soft]: https://github.com/scrappysoft
[Dick Marinus]: https://github.com/meeuw
[François Pietka]: https://github.com/fpietka
[Frederic Aoustin]: https://github.com/fraoustin

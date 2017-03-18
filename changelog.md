1.9.0:
======

Features:
---------

* Add tee/notee commands for outputing results to a file. (Thanks: [Dick Marinus]).
* Add date, port, and whitespace options to prompt configuration. (Thanks: [Matheus Rosa]).
* Allow user to specify LESS pager flags. (Thanks: [John Sterling]).
* Add support for auto-reconnect. (Thanks: [Jialong Liu]).
* Add CSV batch output. (Thanks: [Matheus Rosa]).
* Add auto_vertical_output config to myclirc. (Thanks: [Matheus Rosa]).
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
* Read the smart_completion config from myclirc. (Thanks: [Thomas Roten]).

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
* Support MYCLI_HISTFILE environment variable to specify where to write the history file. (Thanks: [Scrappy Soft]).
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

* Upgrade prompt_toolkit to 1.0.0. (Thanks: [Jonathan Slenders])

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

* Upgrade prompt_toolkit to 0.60.
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
* Make pycrypto optional and only install it in \*nix systems. (Thanks: [Iryna Cherniavska]).
* Add badge for PyPI version to README. (Thanks: [Shoma Suzuki]).
* Updated release script with a --dry-run and --confirm-steps option. (Thanks: [Iryna Cherniavska]).
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

* Upgrade prompt_toolkit to 0.46. (Thanks: [Jonathan Slenders])

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
  a group to use in the my.cnf files. (Thanks: [Iryna Cherniavska](http://github.com/j-bennet))

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

* Upgrade prompt_toolkit dependency version to 0.45.
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
* Honor the `pager` setting in my.cnf files. (Thanks: [Iryna Cherniavska](http://github.com/j-bennet))

Bug Fixes:
----------

* Fix a crashing bug in completion engine for cross joins.
* Make `<null>` value consistent between tabular and vertical output.

Internal Changes:
-----------------

* Changed pymysql version to be greater than 0.6.6.
* Upgrade prompt_toolkit version to 0.42. (Thanks: [Yasuhiro Matsumoto](https://github.com/mattn))
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

* Upgrade prompt_toolkit to 0.38. This improves the performance of pasting long queries.
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
[Iryna Cherniavska]: https://github.com/j-bennet
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

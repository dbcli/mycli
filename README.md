# mycli

[![Build Status](https://github.com/dbcli/mycli/workflows/mycli/badge.svg)](https://github.com/dbcli/mycli/actions?query=workflow%3Amycli)
[![PyPI](https://img.shields.io/pypi/v/mycli.svg)](https://pypi.python.org/pypi/mycli)
[![LGTM](https://img.shields.io/lgtm/grade/python/github/dbcli/mycli.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/dbcli/mycli/context:python)

A command line client for MySQL that can do auto-completion and syntax highlighting.

HomePage: [http://mycli.net](http://mycli.net)
Documentation: [http://mycli.net/docs](http://mycli.net/docs)

![Completion](screenshots/tables.png)
![CompletionGif](screenshots/main.gif)

Postgres Equivalent: [http://pgcli.com](http://pgcli.com)

Quick Start
-----------

If you already know how to install python packages, then you can install it via pip:

You might need sudo on linux.

```
$ pip install -U mycli
```

or

```
$ brew update && brew install mycli  # Only on macOS
```

or

```
$ sudo apt-get install mycli # Only on debian or ubuntu
```

### Usage

    $ mycli --help
    Usage: mycli [OPTIONS] [DATABASE]

      A MySQL terminal client with auto-completion and syntax highlighting.

      Examples:
        - mycli my_database
        - mycli -u my_user -h my_host.com my_database
        - mycli mysql://my_user@my_host.com:3306/my_database

    Options:
      -h, --host TEXT               Host address of the database.
      -P, --port INTEGER            Port number to use for connection. Honors
                                    $MYSQL_TCP_PORT.

      -u, --user TEXT               User name to connect to the database.
      -S, --socket TEXT             The socket file to use for connection.
      -p, --password TEXT           Password to connect to the database.
      --pass TEXT                   Password to connect to the database.
      --ssh-user TEXT               User name to connect to ssh server.
      --ssh-host TEXT               Host name to connect to ssh server.
      --ssh-port INTEGER            Port to connect to ssh server.
      --ssh-password TEXT           Password to connect to ssh server.
      --ssh-key-filename TEXT       Private key filename (identify file) for the
                                    ssh connection.

      --ssh-config-path TEXT        Path to ssh configuration.
      --ssh-config-host TEXT        Host to connect to ssh server reading from ssh
                                    configuration.

      --ssl                         Enable SSL for connection (automatically
                                    enabled with other flags).
      --ssl-ca PATH                 CA file in PEM format.
      --ssl-capath TEXT             CA directory.
      --ssl-cert PATH               X509 cert in PEM format.
      --ssl-key PATH                X509 key in PEM format.
      --ssl-cipher TEXT             SSL cipher to use.
      --ssl-verify-server-cert      Verify server's "Common Name" in its cert
                                    against hostname used when connecting. This
                                    option is disabled by default.

      -V, --version                 Output mycli's version.
      -v, --verbose                 Verbose output.
      -D, --database TEXT           Database to use.
      -d, --dsn TEXT                Use DSN configured into the [alias_dsn]
                                    section of myclirc file.

      --list-dsn                    list of DSN configured into the [alias_dsn]
                                    section of myclirc file.

      --list-ssh-config             list ssh configurations in the ssh config
                                    (requires paramiko).

      -R, --prompt TEXT             Prompt format (Default: "\t \u@\h:\d> ").
      -l, --logfile FILENAME        Log every query and its results to a file.
      --defaults-group-suffix TEXT  Read MySQL config groups with the specified
                                    suffix.

      --defaults-file PATH          Only read MySQL options from the given file.
      --myclirc PATH                Location of myclirc file.
      --auto-vertical-output        Automatically switch to vertical output mode
                                    if the result is wider than the terminal
                                    width.

      -t, --table                   Display batch output in table format.
      --csv                         Display batch output in CSV format.
      --warn / --no-warn            Warn before running a destructive query.
      --local-infile BOOLEAN        Enable/disable LOAD DATA LOCAL INFILE.
      -g, --login-path TEXT         Read this path from the login file.
      -e, --execute TEXT            Execute command and quit.
      --init-command TEXT           SQL statement to execute after connecting.
      --charset TEXT                Character set for MySQL session.
      --password-file PATH          File or FIFO path containing the password
                                    to connect to the db if not specified otherwise
      --help                        Show this message and exit.


Features
--------

`mycli` is written using [prompt_toolkit](https://github.com/jonathanslenders/python-prompt-toolkit/).

* Auto-completion as you type for SQL keywords as well as tables, views and
  columns in the database.
* Syntax highlighting using Pygments.
* Smart-completion (enabled by default) will suggest context-sensitive completion.
    - `SELECT * FROM <tab>` will only show table names.
    - `SELECT * FROM users WHERE <tab>` will only show column names.
* Support for multiline queries.
* Favorite queries with optional positional parameters. Save a query using
  `\fs alias query` and execute it with `\f alias` whenever you need.
* Timing of sql statements and table rendering.
* Config file is automatically created at ``~/.myclirc`` at first launch.
* Log every query and its results to a file (disabled by default).
* Pretty prints tabular data (with colors!)
* Support for SSL connections
* Some features are only exposed as [key bindings](doc/key_bindings.rst)

Contributions:
--------------

If you're interested in contributing to this project, first of all I would like
to extend my heartfelt gratitude. I've written a small doc to describe how to
get this running in a development setup.

https://github.com/dbcli/mycli/blob/main/CONTRIBUTING.md

Please feel free to reach out to me if you need help.

My email: amjith.r@gmail.com

Twitter: [@amjithr](http://twitter.com/amjithr)

## Detailed Install Instructions:

### Arch, Manjaro

You can install the mycli package available in the AUR:

```
$ yay -S mycli
```

### Debian, Ubuntu

On Debian, Ubuntu distributions, you can easily install the mycli package using apt:

```
$ sudo apt-get install mycli
```

### Fedora

Fedora has a package available for mycli, install it using dnf:

```
$ sudo dnf install mycli
```

### RHEL, Centos

I haven't built an RPM package for mycli for RHEL or Centos yet. So please use `pip` to install `mycli`. You can install pip on your system using:

```
$ sudo yum install python3-pip
```

Once that is installed, you can install mycli as follows:

```
$ sudo pip3 install mycli
```

### Windows

Follow the instructions on this blogpost: https://www.codewall.co.uk/installing-using-mycli-on-windows/

### Cygwin

1. Make sure the following Cygwin packages are installed:
`python3`, `python3-pip`.
2. Install mycli: `pip3 install mycli`

### Thanks:

This project was funded through kickstarter. My thanks to the [backers](http://mycli.net/sponsors) who supported the project.

A special thanks to [Jonathan Slenders](https://twitter.com/jonathan_s) for
creating [Python Prompt Toolkit](http://github.com/jonathanslenders/python-prompt-toolkit),
which is quite literally the backbone library, that made this app possible.
Jonathan has also provided valuable feedback and support during the development
of this app.

[Click](http://click.pocoo.org/) is used for command line option parsing
and printing error messages.

Thanks to [PyMysql](https://github.com/PyMySQL/PyMySQL) for a pure python adapter to MySQL database.


### Compatibility

Mycli is tested on macOS and Linux, and requires Python 3.7 or better.

**Mycli is not tested on Windows**, but the libraries used in this app are Windows-compatible.
This means it should work without any modifications. If you're unable to run it
on Windows, please [file a bug](https://github.com/dbcli/mycli/issues/new).

### Configuration and Usage

For more information on using and configuring mycli, [check out our documentation](http://mycli.net/docs).

Common topics include:
- [Configuring mycli](http://mycli.net/config)
- [Using/Disabling the pager](http://mycli.net/pager)
- [Syntax colors](http://mycli.net/syntax)

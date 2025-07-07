# mycli

[![Build Status](https://github.com/dbcli/mycli/workflows/mycli/badge.svg)](https://github.com/dbcli/mycli/actions?query=workflow%3Amycli)

A command line client for MySQL that can do auto-completion and syntax highlighting.

Homepage: [http://mycli.net](http://mycli.net)
Documentation: [http://mycli.net/docs](http://mycli.net/docs)

![Completion](screenshots/tables.png)
![CompletionGif](screenshots/main.gif)

Postgres Equivalent: [http://pgcli.com](http://pgcli.com)

Quick Start
-----------

If you already know how to install Python packages, then you can install it via `pip`:

You might need sudo on Linux.

```bash
$ pip install -U mycli
```

or

```bash
$ brew update && brew install mycli  # Only on macOS
```

or

```bash
$ sudo apt-get install mycli  # Only on Debian or Ubuntu
```

### Usage

See

```bash
$ mycli --help
```

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
* Shell-style trailing redirects with `$>`, `$>>` and `$|` operators.
* Some features are only exposed as [key bindings](doc/key_bindings.rst)

Contributions:
--------------

If you're interested in contributing to this project, first of all I would like
to extend my heartfelt gratitude. I've written a small doc to describe how to
get this running in a development setup.

https://github.com/dbcli/mycli/blob/main/CONTRIBUTING.md


## Additional Install Instructions:

These are some alternative ways to install mycli that are not managed by our team but provided by OS package maintainers. These packages could be slightly out of date and take time to release the latest version.

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

### Windows

Follow the instructions on this blogpost: http://web.archive.org/web/20221006045208/https://www.codewall.co.uk/installing-using-mycli-on-windows/


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

Mycli is tested on macOS and Linux, and requires Python 3.9 or better.

**Mycli is not tested on Windows**, but the libraries used in this app are Windows-compatible.
This means it should work without any modifications. If you're unable to run it
on Windows, please [file a bug](https://github.com/dbcli/mycli/issues/new).

### Configuration and Usage

For more information on using and configuring mycli, [check out our documentation](http://mycli.net/docs).

Common topics include:
- [Configuring mycli](http://mycli.net/config)
- [Using/Disabling the pager](http://mycli.net/pager)
- [Syntax colors](http://mycli.net/syntax)

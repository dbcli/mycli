# mycli
A command line client for MySQL that can do auto-completion and syntax highlighting.

## Installation

I plan to create DEB, RPM and Brew packages in the future.

Right now, one can use `pip` (Python Package Manager) to install directly from the repo.

###OSX:
---
    $ pip install -U -e git+https://github.com/dbcli/mycli.git#egg=mycli

###Linux:
---
    $ sudo pip install -U -e git+https://github.com/dbcli/mycli.git#egg=mycli
    
That will install the `mycli` package from the source. 

If you're not familiar with `pip`, here are some quickstart guides. 

https://pip.pypa.io/en/stable/installing.html

https://pip.pypa.io/en/stable/quickstart.html


## Usage

```
$ mycli --help
Usage: mycli [OPTIONS] [DATABASE]

Options:
  -h, --host TEXT      Host address of the database.
  -P, --port TEXT      Port number at which the Port number to use for
                       connection. Honors $MYSQL_TCP_PORT
  -u, --user TEXT      User name to connect to the database.
  -S, --socket TEXT    The socket file to use for connection.
  -p, --password       Force password prompt.
  --pass TEXT          Password to connect to the database
  -v, --version        Version of mycli.
  -D, --database TEXT  Database to use.
  -R, --prompt TEXT    Prompt format (Default: "\u@\h:\d> ")
  --help               Show this message and exit.
```

## Configuration

The config file is located at ~/.myclirc

The app ships with sane defaults. But if you're unsatisfied with the current behavior take a look at the configs. 

## Compatibility

Tests have been run on OS X and Linux.

NOT TESTED THIS IN WINDOWS. But all the libraries used in this app are Windows compatible. So it should work without any modifications. If you're unable to run it on Windows, please file a bug. I will try my best to fix it.

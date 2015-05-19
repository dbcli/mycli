# mycli
A command line client for MySQL that can do auto-completion and syntax highlighting.

## Installation

I plan to create DEB, RPM and Brew packages in the future.

If you're familiar with `pip` then you can simply do:

    $ pip install mycli

If you're not familiar with `pip`, here are some quickstart guides. 

https://pip.pypa.io/en/stable/installing.html

https://pip.pypa.io/en/stable/quickstart.html


## Usage

```
$ mycli --help
Usage: mycli [OPTIONS] [DATABASE]

Options:
  -h, --host TEXT      Host address of the database.
  -P, --port INTEGER   Port number at which the MySQL instance is listening.
  -u, --user TEXT      User name to connect to the database.
  -p, --password       Force password prompt.
  -v, --version        Version of mycli.
  -D, --database TEXT  Database to use.
  --help               Show this message and exit.
```

## Configuration

The config file is located at ~/.myclirc

## Compatibility

Tests have been run on OS X and Linux.

NOT TESTED THIS IN WINDOWS. But all the libraries used in this app are Windows compatible. So it should work without any modifications. If you're unable to run it on Windows, please file a bug. I will try my best to fix it.

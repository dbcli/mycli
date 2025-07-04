# Development Guide

This is a guide for developers who would like to contribute to this project.

If you're interested in contributing to mycli, thank you. We'd love your help!
You'll always get credit for your work.

## GitHub Workflow

1. [Fork the repository](https://github.com/dbcli/mycli) on GitHub.

2. Clone your fork locally:
    ```bash
    $ git clone <url-for-your-fork>
    ```

3. Add the official repository (`upstream`) as a remote repository:
    ```bash
    $ git remote add upstream git@github.com:dbcli/mycli.git
    ```

4. Set up [uv](https://docs.astral.sh/uv/getting-started/installation/)
   for development:

    ```bash
    $ cd mycli
    $ uv sync --extra dev --extra ssh
    ```

    We've just created a virtual environment and installed all the dependencies
    and tools we need to work on mycli.

5. Create a branch for your bugfix or feature based off the `main` branch:

    ```bash
    $ git checkout -b <name-of-bugfix-or-feature> main
    ```

6. While you work on your bugfix or feature, be sure to pull the latest changes from `upstream`. This ensures that your local codebase is up-to-date:

    ```bash
    $ git pull upstream main
    ```

7. When your work is ready for the mycli team to review it, push your branch to your fork:

    ```bash
    $ git push origin <name-of-bugfix-or-feature>
    ```

8. [Create a pull request](https://help.github.com/articles/creating-a-pull-request-from-a-fork/)
   on GitHub.


## Running mycli

To run mycli with your local changes:

```bash
$ uv run mycli
```


## Running the Tests

While you work on mycli, it's important to run the tests to make sure your code
hasn't broken any existing functionality. To run the tests, just type in:

```bash
$ uv run tox
```

### Test Database Credentials

Some tests require a database connection to work. You can tell the tests which
credentials to use by setting the applicable environment variables:

```bash
$ export PYTEST_HOST=localhost
$ export PYTEST_USER=mycli
$ export PYTEST_PASSWORD=myclirocks
$ export PYTEST_PORT=3306
$ export PYTEST_CHARSET=utf8
```

The default values are `localhost`, `root`, no password, `3306`, and `utf8`.
You only need to set the values that differ from the defaults.

If you would like to run the tests as a user with only the necessary privileges,
create a `mycli` user and run the following grant statements.

```sql
GRANT ALL PRIVILEGES ON `mycli_%`.* TO 'mycli'@'localhost';
GRANT SELECT ON mysql.* TO 'mycli'@'localhost';
GRANT SELECT ON performance_schema.* TO 'mycli'@'localhost';
```

### CLI Tests

Some CLI tests expect the program `ex` to be a symbolic link to `vim`.

In some systems (e.g. Arch Linux) `ex` is a symbolic link to `vi`, which will
change the output and therefore make some tests fail.

You can check this by running:
```bash
$ readlink -f $(which ex)
```


## Releasing a new version of mycli

Create a new [release](https://github.com/dbcli/mycli/releases) in Github. This will trigger a Github action which will run all the tests, build the wheel and upload it to PyPI.

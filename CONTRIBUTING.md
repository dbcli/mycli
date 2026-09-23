# Development Guide

This is a guide for developers who would like to contribute to the project.

If you're interested in contributing to mycli, thank you. We'd love your help!
You'll always get credit and appreciation for your work.

## GitHub Workflow

1. [Fork the repository](https://github.com/dbcli/mycli) on GitHub.

2. Clone your fork locally:

    ```bash
    git clone <url-for-your-fork>
    ```

3. Add the official repository (`upstream`) as a remote repository:

    ```bash
    git remote add upstream git@github.com:dbcli/mycli.git
    ```

4. Once you have added upstream, the following command will pull the latest changes to your local `main`:

    ```bash
    git pull upstream main
    ```

5. Set up [uv](https://docs.astral.sh/uv/getting-started/installation/)
   for development:

    ```bash
    cd mycli
    uv sync --all-extras
    ```

    We've just created a virtual environment and installed all the dependencies
    and tools we need to work on mycli.

6. Create a branch for your bugfix or feature based off the `main` branch:

    ```bash
    git checkout -b <name-of-bugfix-or-feature> main
    ```

7. When your work is ready for the mycli team to review it, push your branch to your fork:

    ```bash
    git push origin <name-of-bugfix-or-feature>
    ```

8. [Create a pull request](https://help.github.com/articles/creating-a-pull-request-from-a-fork/)
   on GitHub.


## Running Mycli with Changes

To run mycli with your local changes:

```bash
uv run mycli
```


## Running the Tests

While you work on mycli, it's important to run the tests to make sure your code
hasn't broken any existing functionality. To run the tests, just run:

```bash
uv run tox
```

### Test Database Credentials

Some tests require a database connection to work. You can tell the tests which
credentials to use by setting the applicable environment variables:

```bash
export PYTEST_HOST=localhost
export PYTEST_USER=mycli
export PYTEST_PASSWORD=myclirocks
export PYTEST_PORT=3306
export PYTEST_CHARSET=utf8mb4
```

Since the default values are

```bash
export PYTEST_HOST=localhost
export PYTEST_USER=root
export PYTEST_PASSWORD=<no password>
export PYTEST_PORT=3306
export PYTEST_CHARSET=utf8mb4
```

for most cases you only need to set the values which differ from the defaults:

```bash
export PYTEST_USER=mycli
export PYTEST_PASSWORD=myclirocks
```

If you would like to run the tests as a user with only the necessary privileges,
create a `mycli` user on your MySQL server and run the following GRANT statements:

```sql
GRANT ALL PRIVILEGES ON `mycli_%`.* TO 'mycli'@'localhost';
GRANT SELECT ON mysql.* TO 'mycli'@'localhost';
GRANT SELECT ON performance_schema.* TO 'mycli'@'localhost';
```

### Editor Tests

Some tests expect the program `ex` to be a symbolic link to `vim`.

In some systems (e.g. Arch Linux) `ex` is a symbolic link to `vi`, which will
change the output and therefore make some tests fail.

You can check this by running:
```bash
readlink -f $(which ex)
```

# GitHub PR checklist

 * add the contribution to `changelog.md`
 * add your name to the `AUTHORS` file (or make sure it is already there)
 * run

    ```bash
    uv run ruff check && uv run ruff format && uv run mypy --install-types .
    ```


## Releasing a New Version of Mycli (For Maintainers)

We create a new [release](https://github.com/dbcli/mycli/releases) in GitHub. This triggers a GitHub Action which will

 * run all the tests
 * build a wheel and upload it to PyPI
 * build a Docker image and upload it to ghcr.io

Steps to create a release:

 * Update `changelog.md`, setting the release version and date at the top.  Bump the feature version if there are new features in the changelog, otherwise only bump the patch version.  Merge this change.
 * Navigate to https://github.com/dbcli/mycli/releases/new .
 * Press "Select Tag" and enter the new version number.  It should be the same as in `changelog.md` but with a leading `v`.  It should not already exist.
 * Press "Generate Release Notes", which will fill in the notes and the title.
 * Sanity check the generated release notes.
 * Press "Publish Release".

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import click
import pytest

from mycli import cli_args as cli_args_module
from mycli.cli_args import (
    EMPTY_PASSWORD_FLAG_SENTINEL,
    INT_OR_STRING_CLICK_TYPE,
    CliArgs,
    get_password_from_file,
    preprocess_cli_args,
)


def valid_connection_scheme(value: str) -> tuple[bool, str | None]:
    scheme, _, _ = value.partition('://')
    return scheme == 'mysql', scheme or None


def test_int_or_string_click_type_accepts_int_string_and_none() -> None:
    assert INT_OR_STRING_CLICK_TYPE.convert(7, None, None) == 7
    assert INT_OR_STRING_CLICK_TYPE.convert('secret', None, None) == 'secret'
    assert INT_OR_STRING_CLICK_TYPE.convert(None, None, None) is None


def test_int_or_string_click_type_rejects_other_values() -> None:
    with pytest.raises(click.BadParameter, match='Not a valid password string'):
        INT_OR_STRING_CLICK_TYPE.convert(object(), None, None)


def test_get_password_from_file_reads_first_line_without_trailing_newline(tmp_path: Path) -> None:
    password_file = tmp_path / 'password.txt'
    password_file.write_text('secret\nignored\n', encoding='utf8')

    assert get_password_from_file(str(password_file)) == 'secret'


def test_get_password_from_file_returns_none_for_missing_path() -> None:
    assert get_password_from_file(None) is None
    assert get_password_from_file('') is None


@pytest.mark.parametrize(
    ('exception', 'expected'),
    [
        (FileNotFoundError(), "Password file 'secret.txt' not found"),
        (PermissionError(), "Permission denied reading password file 'secret.txt'"),
        (IsADirectoryError(), "Path 'secret.txt' is a directory, not a file"),
        (RuntimeError('boom'), "Error reading password file 'secret.txt': boom"),
    ],
)
def test_get_password_from_file_exits_with_error_for_read_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exception: Exception,
    expected: str,
) -> None:
    def raise_error(*_args: Any, **_kwargs: Any) -> None:
        raise exception

    monkeypatch.setattr(builtins, 'open', raise_error)

    with pytest.raises(SystemExit) as excinfo:
        get_password_from_file('secret.txt')

    assert excinfo.value.code == 1
    assert expected in capsys.readouterr().err


def test_preprocess_cli_args_moves_dsn_from_password_to_database() -> None:
    cli_args = CliArgs()
    cli_args.password = 'mysql://user:pass@host/db'

    verbosity = preprocess_cli_args(cli_args, valid_connection_scheme)

    assert verbosity == 0
    assert cli_args.database == 'mysql://user:pass@host/db'
    assert cli_args.password == EMPTY_PASSWORD_FLAG_SENTINEL  # type: ignore[comparison-overlap]


def test_preprocess_cli_args_rejects_unknown_dsn_scheme(capsys: pytest.CaptureFixture[str]) -> None:
    cli_args = CliArgs()
    cli_args.password = 'postgres://user:pass@host/db'

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert 'Unknown connection scheme provided for DSN URI (postgres://)' in capsys.readouterr().err


def test_preprocess_cli_args_reads_password_file_when_password_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_args = CliArgs()
    cli_args.password_file = 'secret.txt'
    monkeypatch.setattr(cli_args_module, 'get_password_from_file', lambda password_file: f'from:{password_file}')

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password == 'from:secret.txt'


def test_preprocess_cli_args_uses_mysql_pwd_when_password_and_file_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = CliArgs()
    monkeypatch.setenv('MYSQL_PWD', 'env-secret')

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password == 'env-secret'


def test_preprocess_cli_args_prefers_existing_password_over_mysql_pwd(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_args = CliArgs()
    cli_args.password = 'cli-secret'
    monkeypatch.setenv('MYSQL_PWD', 'env-secret')

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == 0
    assert cli_args.password == 'cli-secret'


@pytest.mark.parametrize(
    ('checkpoint', 'batch', 'expected'),
    [
        (None, 'batch.sql', 'Error: --resume requires a --checkpoint file.'),
        (object(), None, 'Error: --resume requires a --batch file.'),
    ],
)
def test_preprocess_cli_args_validates_resume_requirements(
    capsys: pytest.CaptureFixture[str],
    checkpoint: object | None,
    batch: str | None,
    expected: str,
) -> None:
    cli_args = CliArgs()
    cli_args.resume = True
    cli_args.checkpoint = checkpoint  # type: ignore[assignment]
    cli_args.batch = batch

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert expected in capsys.readouterr().err


def test_preprocess_cli_args_rejects_verbose_and_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    cli_args = CliArgs()
    cli_args.verbose = 1
    cli_args.quiet = True

    with pytest.raises(SystemExit) as excinfo:
        preprocess_cli_args(cli_args, valid_connection_scheme)

    assert excinfo.value.code == 1
    assert 'Error: --verbose and --quiet are incompatible.' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('verbose', 'quiet', 'expected'),
    [
        (2, False, 2),
        (0, True, -1),
        (0, False, 0),
    ],
)
def test_preprocess_cli_args_returns_cli_verbosity(verbose: int, quiet: bool, expected: int) -> None:
    cli_args = CliArgs()
    cli_args.verbose = verbose
    cli_args.quiet = quiet

    assert preprocess_cli_args(cli_args, valid_connection_scheme) == expected

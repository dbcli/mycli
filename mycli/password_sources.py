from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import click

PasswordSource = Literal[
    'prompt',
    'cli_literal',
    'cli_file',
    'environment',
    'dsn',
    'vault',
    'mylogin_cnf',
    'keyring',
]
PasswordValue = str | int
PasswordLoader = Callable[[], PasswordValue | None]

KNOWN_PASSWORD_SOURCES: list[PasswordSource] = [
    'prompt',
    'cli_literal',
    'cli_file',
    'environment',
    'dsn',
    'vault',
    'mylogin_cnf',
    'keyring',
]


@dataclass(frozen=True, slots=True)
class SelectedPassword:
    source: PasswordSource
    value: PasswordValue


@dataclass(frozen=True, slots=True)
class PasswordCandidate:
    source: PasswordSource
    value: PasswordValue | None = None
    loader: PasswordLoader | None = None

    def resolve(self) -> SelectedPassword | None:
        value = self.loader() if self.loader is not None else self.value
        if value is None:
            return None
        return SelectedPassword(source=self.source, value=value)


class PasswordCandidates:
    def __init__(self) -> None:
        self._candidates: dict[PasswordSource, PasswordCandidate] = {}

    def add_value(self, source: PasswordSource, value: PasswordValue | None) -> None:
        self._candidates[source] = PasswordCandidate(source=source, value=value)

    def add_loader(self, source: PasswordSource, loader: PasswordLoader) -> None:
        self._candidates[source] = PasswordCandidate(source=source, loader=loader)

    def resolve(self, password_source_precedence) -> SelectedPassword | None:
        for source in password_source_precedence:
            if source not in KNOWN_PASSWORD_SOURCES:
                click.secho(f'Skipping unknown password source: {source}.', err=True, fg='red')
                continue
            candidate = self._candidates.get(source)
            if candidate is None:
                continue
            if selected := candidate.resolve():
                return selected
        return None

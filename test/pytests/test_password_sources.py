from __future__ import annotations

import pytest

from mycli.password_sources import (
    KNOWN_PASSWORD_SOURCES,
    PasswordCandidates,
)


def test_resolve_uses_fixed_precedence_instead_of_registration_order() -> None:
    candidates = PasswordCandidates()
    candidates.add_value('keyring', 'keyring-secret')
    candidates.add_value('dsn', 'dsn-secret')
    candidates.add_value('literal', 'cli-secret')

    selected = candidates.resolve(KNOWN_PASSWORD_SOURCES)

    assert selected is not None
    assert selected.source == 'literal'
    assert selected.value == 'cli-secret'


def test_resolve_treats_empty_string_as_password() -> None:
    candidates = PasswordCandidates()
    candidates.add_value('literal', '')
    candidates.add_value('file', 'file-secret')

    selected = candidates.resolve(KNOWN_PASSWORD_SOURCES)

    assert selected is not None
    assert selected.source == 'literal'
    assert selected.value == ''


def test_resolve_skips_lower_priority_lazy_loader() -> None:
    loader_calls: list[str] = []

    def load_vault_password() -> str:
        loader_calls.append('vault')
        return 'vault-secret'

    candidates = PasswordCandidates()
    candidates.add_loader('vault', load_vault_password)
    candidates.add_value('environment', 'environment-secret')

    selected = candidates.resolve(KNOWN_PASSWORD_SOURCES)

    assert selected is not None
    assert selected.source == 'environment'
    assert loader_calls == []


def test_resolve_falls_back_when_a_loader_returns_none() -> None:
    candidates = PasswordCandidates()
    candidates.add_loader('vault', lambda: None)
    candidates.add_value('login_path', 'mylogin-secret')

    selected = candidates.resolve(KNOWN_PASSWORD_SOURCES)

    assert selected is not None
    assert selected.source == 'login_path'
    assert selected.value == 'mylogin-secret'


def test_resolve_skips_unknown_source_and_returns_none(capsys: pytest.CaptureFixture[str]) -> None:
    candidates = PasswordCandidates()

    assert candidates.resolve(['unknown']) is None
    assert capsys.readouterr().err == 'Skipping unknown password source: unknown.\n'

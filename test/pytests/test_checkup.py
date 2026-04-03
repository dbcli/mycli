import importlib.metadata
import json
from types import SimpleNamespace
import urllib.error

from mycli.main_modes import checkup


class FakeUrlResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> 'FakeUrlResponse':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode('utf8')


def test_pypi_api_fetch_success(monkeypatch) -> None:
    def fake_urlopen(url: str, timeout: int) -> FakeUrlResponse:
        assert url == 'https://pypi.org/pypi/mycli/json'
        assert timeout == 5
        return FakeUrlResponse({'info': {'version': '1.2.3'}})

    monkeypatch.setattr(checkup.urllib.request, 'urlopen', fake_urlopen)

    assert checkup.pypi_api_fetch('/mycli/json') == {'info': {'version': '1.2.3'}}


def test_pypi_api_fetch_url_error(monkeypatch, capsys) -> None:
    def fake_urlopen(url: str, timeout: int) -> FakeUrlResponse:
        raise urllib.error.URLError('offline')

    monkeypatch.setattr(checkup.urllib.request, 'urlopen', fake_urlopen)

    assert checkup.pypi_api_fetch('mycli/json') == {}
    assert 'Failed to connect to PyPi on https://pypi.org/pypi/mycli/json' in capsys.readouterr().err


def test_dependencies_checkup(monkeypatch, capsys) -> None:
    versions = {
        'cli_helpers': '1.0.0',
        'click': '2.0.0',
        'prompt_toolkit': '3.0.0',
        'pymysql': '4.0.0',
    }

    def fake_version(name: str) -> str:
        if name == 'tabulate':
            raise importlib.metadata.PackageNotFoundError
        return versions[name]

    def fake_pypi_api_fetch(fragment: str) -> dict:
        dependency = fragment.strip('/').removesuffix('/json')
        return {'info': {'version': f'latest-{dependency}'}}

    monkeypatch.setattr(checkup.importlib.metadata, 'version', fake_version)
    monkeypatch.setattr(checkup, 'pypi_api_fetch', fake_pypi_api_fetch)

    checkup._dependencies_checkup()
    output = capsys.readouterr().out

    assert '### Key Python dependencies:' in output
    assert 'cli_helpers version 1.0.0 (latest latest-cli_helpers)' in output
    assert 'click version 2.0.0 (latest latest-click)' in output
    assert 'prompt_toolkit version 3.0.0 (latest latest-prompt_toolkit)' in output
    assert 'pymysql version 4.0.0 (latest latest-pymysql)' in output
    assert 'tabulate version None (latest latest-tabulate)' in output


def test_executables_checkup(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        checkup.shutil,
        'which',
        lambda executable: f'/usr/bin/{executable}' if executable != 'fzf' else None,
    )

    checkup._executables_checkup()
    output = capsys.readouterr().out

    assert '### External executables:' in output
    assert 'The "less" executable was found' in output
    assert 'The recommended "fzf" executable was not found' in output
    assert 'The "pygmentize" executable was found' in output


def test_environment_checkup(monkeypatch, capsys) -> None:
    monkeypatch.setenv('EDITOR', 'vim')
    monkeypatch.delenv('VISUAL', raising=False)

    checkup._environment_checkup()
    output = capsys.readouterr().out

    assert '### Environment variables:' in output
    assert 'The $EDITOR environment variable was set to "vim" ' in output
    assert 'The $VISUAL environment variable was not set' in output


def test_configuration_checkup_missing_file(capsys) -> None:
    mycli = SimpleNamespace(
        config={},
        config_without_package_defaults={},
        config_without_user_options={},
    )

    checkup._configuration_checkup(mycli)
    output = capsys.readouterr().out

    assert '### Missing file:' in output
    assert 'The local ~/,myclirc is missing or empty.' in output
    assert f'{checkup.REPO_URL}/blob/main/mycli/myclirc' in output


def test_configuration_checkup_reports_missing_unsupported_and_deprecated(capsys) -> None:
    mycli = SimpleNamespace(
        config={
            'main': {
                'present': '',
                'missing_item': '',
            },
            'extra_section': {
                'extra_item': '',
            },
        },
        config_without_package_defaults={
            'main': {
                'present': '',
                'unsupported_item': '',
                'default_character_set': '',
            },
            'unsupported_section': {
                'anything': '',
            },
            'colors': {
                'sql.keyword': '',
            },
            'favorite_queries': {
                'demo': 'select 1',
            },
        },
        config_without_user_options={
            'main': {
                'present': '',
            },
            'colors': {},
        },
    )

    checkup._configuration_checkup(mycli)
    output = capsys.readouterr().out

    assert '### Missing in user ~/.myclirc:' in output
    assert 'The entire section:\n\n    [extra_section]\n' in output
    assert 'The item:\n\n    [main]\n    missing_item =' in output
    assert '### Unsupported in user ~/.myclirc:' in output
    assert 'The entire section:\n\n    [unsupported_section]\n' in output
    assert 'The item:\n\n    [main]\n    unsupported_item =' in output
    assert '### Deprecated in user ~/.myclirc:' in output
    assert '    [main]\n    default_character_set' in output
    assert '    [connection]\n    default_character_set' in output
    assert f'{checkup.REPO_URL}/blob/main/mycli/myclirc' in output


def test_configuration_checkup_skips_transitioned_and_free_entry_items(capsys) -> None:
    mycli = SimpleNamespace(
        config={
            'extra_section': {
                'extra_item': '',
            },
            'connection': {
                'default_character_set': '',
            },
        },
        config_without_package_defaults={
            'connection': {},
            'unsupported_section': {
                'anything': '',
            },
            'favorite_queries': {
                'demo': 'select 1',
            },
        },
        config_without_user_options={
            'connection': {},
            'favorite_queries': {},
        },
    )

    checkup._configuration_checkup(mycli)
    output = capsys.readouterr().out

    assert 'Missing in user ~/.myclirc:' in output
    assert 'The entire section:\n\n    [extra_section]\n' in output
    assert 'Unsupported in user ~/.myclirc:' in output
    assert 'The entire section:\n\n    [unsupported_section]\n' in output
    assert '[connection]\n    default_character_set =' not in output
    assert '[favorite_queries]' not in output


def test_configuration_checkup_up_to_date(capsys) -> None:
    mycli = SimpleNamespace(
        config={
            'main': {
                'prompt': '',
            },
        },
        config_without_package_defaults={
            'main': {
                'prompt': '',
            },
        },
        config_without_user_options={
            'main': {
                'prompt': '',
            },
        },
    )

    checkup._configuration_checkup(mycli)
    output = capsys.readouterr().out

    assert '### Configuration:' in output
    assert 'User configuration all up to date!' in output


def test_main_checkup_calls_all_sections(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    mycli = SimpleNamespace(name='mycli')

    monkeypatch.setattr(checkup, '_dependencies_checkup', lambda: calls.append(('dependencies', None)))
    monkeypatch.setattr(checkup, '_executables_checkup', lambda: calls.append(('executables', None)))
    monkeypatch.setattr(checkup, '_environment_checkup', lambda: calls.append(('environment', None)))
    monkeypatch.setattr(checkup, '_configuration_checkup', lambda arg: calls.append(('configuration', arg)))

    checkup.main_checkup(mycli)

    assert calls == [
        ('dependencies', None),
        ('executables', None),
        ('environment', None),
        ('configuration', mycli),
    ]

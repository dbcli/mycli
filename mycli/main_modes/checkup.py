import importlib.metadata
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

from tabulate import tabulate

from mycli.constants import REPO_URL

PYPI_API_BASE = 'https://pypi.org/pypi'


def pypi_api_fetch(fragment: str) -> dict:
    fragment = fragment.lstrip('/')
    url = f'{PYPI_API_BASE}/{fragment}'
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode('utf8'))
    except urllib.error.URLError:
        print(f'Failed to connect to PyPi on {url}', file=sys.stderr)
        return {}


def _dependencies_checkup() -> None:
    print('\n### Key Python dependencies:\n')
    table = []
    for dependency, purpose in [
        ('cli_helpers', 'required'),
        ('click', 'required'),
        ('prompt_toolkit', 'required'),
        ('pygments', 'required'),
        ('pymysql', 'required'),
        ('sqlglot', 'required'),
        ('sqlglotc', 'required'),
        ('tabulate', 'required'),
        ('llm', 'optional for /llm command'),
        ('polars', 'optional for .| operator'),
        ('altair', 'optional for .| operator'),
        ('vl-convert-python', 'optional for .| operator'),
    ]:
        try:
            installed_version = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            installed_version = None
        pypi_profile = pypi_api_fetch(f'/{dependency}/json')
        latest_version = pypi_profile.get('info', {}).get('version', None)
        table.append([dependency, installed_version, latest_version, purpose])
    print(tabulate(table, headers=['library', 'version', 'latest', 'purpose']))


def _executables_checkup() -> None:
    print('\n### External executables:\n')
    table = []
    for executable, purpose in [
        ('less', 'required for paging'),
        ('fzf', r'optional for history search and \x'),
        ('pygmentize', 'optional for history search'),
    ]:
        # executable, purpose = external
        if shutil.which(executable):
            table.append([executable, 'found', purpose])
        else:
            table.append([executable, 'MISSING', purpose])
    print(tabulate(table, headers=['executable', 'status', 'purpose']))


def _environment_checkup() -> None:
    print('\n### Environment variables:\n')
    table = []
    for variable, purpose in [
        ('EDITOR', r'optional for \edit and C-x C-e'),
        ('VISUAL', r'optional for \edit and C-x C-e'),
    ]:
        if value := os.environ.get(variable):
            table.append([f'${variable}', value, purpose])
        else:
            table.append([f'${variable}', 'UNSET', purpose])
    print(tabulate(table, headers=['variable', 'setting', 'purpose']))


def _configuration_checkup(mycli) -> None:
    did_output_missing = False
    did_output_unsupported = False
    did_output_deprecated = False

    indent = '    '
    transitions = {
        f'{indent}[main]\n{indent}default_character_set': f'{indent}[connection]\n{indent}default_character_set',
        f'{indent}[main]\n{indent}ssl_mode': f'{indent}[connection]\n{indent}default_ssl_mode',
    }
    reverse_transitions = {v: k for k, v in transitions.items()}

    if not list(mycli.config.keys()):
        print('\n### Missing file:\n')
        print('The local ~/,myclirc is missing or empty.\n')
        did_output_missing = True
    else:
        for section_name in mycli.config:
            if section_name not in mycli.config_without_package_defaults:
                if not did_output_missing:
                    print('\n### Missing in user ~/.myclirc:\n')
                print(f'The entire section:\n\n{indent}[{section_name}]\n')
                did_output_missing = True
                continue
            for item_name in mycli.config[section_name]:
                transition_key = f'{indent}[{section_name}]\n{indent}{item_name}'
                if transition_key in reverse_transitions:
                    continue
                if item_name not in mycli.config_without_package_defaults[section_name]:
                    if not did_output_missing:
                        print('\n### Missing in user ~/.myclirc:\n')
                    print(f'The item:\n\n{indent}[{section_name}]\n{indent}{item_name} =\n')
                    did_output_missing = True

        for section_name in mycli.config_without_package_defaults:
            if section_name not in mycli.config_without_user_options:
                if not did_output_unsupported:
                    print('\n### Unsupported in user ~/.myclirc:\n')
                did_output_unsupported = True
                print(f'The entire section:\n\n{indent}[{section_name}]\n')
                continue
            for item_name in mycli.config_without_package_defaults[section_name]:
                if section_name == 'colors' and item_name.startswith('sql.'):
                    # these are commented out in the package myclirc
                    continue
                if section_name in [
                    'favorite_queries',
                    'init-commands',
                    'alias_dsn',
                    'alias_dsn.init-commands',
                ]:
                    # these are free-entry sections, so a comparison per item is not meaningful
                    continue
                transition_key = f'{indent}[{section_name}]\n{indent}{item_name}'
                if transition_key in transitions:
                    continue
                if item_name not in mycli.config_without_user_options[section_name]:
                    if not did_output_unsupported:
                        print('\n### Unsupported in user ~/.myclirc:\n')
                    print(f'The item:\n\n{indent}[{section_name}]\n{indent}{item_name} =\n')
                    did_output_unsupported = True

        for section_name in mycli.config_without_package_defaults:
            if section_name not in mycli.config_without_user_options:
                continue
            for item_name in mycli.config_without_package_defaults[section_name]:
                if section_name == 'colors' and item_name.startswith('sql.'):
                    # these are commented out in the package myclirc
                    continue
                transition_key = f'{indent}[{section_name}]\n{indent}{item_name}'
                if transition_key in transitions:
                    if not did_output_deprecated:
                        print('\n### Deprecated in user ~/.myclirc:\n')
                    transition_value = transitions[transition_key]
                    print(f'It is recommended to transition:\n\n{transition_key}\n\nto\n\n{transition_value}\n')
                    did_output_deprecated = True

    if did_output_missing or did_output_unsupported or did_output_deprecated:
        print(f'For more info on supported features, see the commentary and defaults at:\n\n    * {REPO_URL}/blob/main/mycli/myclirc\n')
    else:
        print('\n### Configuration:\n')
        print('User configuration all up to date!\n')


def main_checkup(mycli) -> None:
    _dependencies_checkup()
    _executables_checkup()
    _environment_checkup()
    _configuration_checkup(mycli)

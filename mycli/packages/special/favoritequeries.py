from __future__ import annotations

import logging
import os
import re
from typing import Any

from jinja2 import meta, nodes
from jinja2.sandbox import SandboxedEnvironment

from mycli.config import log, read_config_file

logger = logging.getLogger(__name__)

MISSING = object()

favorite_query_template_environment = SandboxedEnvironment(autoescape=False)
favorite_query_variable_pattern = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')


def analyze_favorite_query_template(query: str) -> tuple[set[str], bool]:
    """Return statically referenced keys and whether ``kv`` is used dynamically."""
    parsed_template = favorite_query_template_environment.parse(query)
    if 'kv' not in meta.find_undeclared_variables(parsed_template):
        return set(), False

    keys: set[str] = set()
    called_attributes: set[int] = set()
    accessed_names: set[int] = set()
    dynamic_access = False
    for call in parsed_template.find_all(nodes.Call):
        called = call.node
        if isinstance(called, nodes.Getattr) and isinstance(called.node, nodes.Name) and called.node.name == 'kv':
            called_attributes.add(id(called))
            accessed_names.add(id(called.node))
            if called.attr == 'get' and call.args:
                key = call.args[0]
                if isinstance(key, nodes.Const) and isinstance(key.value, str):
                    keys.add(key.value)
                else:
                    dynamic_access = True
            else:
                dynamic_access = True

    for attribute in parsed_template.find_all(nodes.Getattr):
        if isinstance(attribute.node, nodes.Name) and attribute.node.name == 'kv':
            accessed_names.add(id(attribute.node))
            if id(attribute) not in called_attributes:
                keys.add(attribute.attr)

    for item in parsed_template.find_all(nodes.Getitem):
        if isinstance(item.node, nodes.Name) and item.node.name == 'kv':
            accessed_names.add(id(item.node))
            key = item.arg
            if isinstance(key, nodes.Const) and isinstance(key.value, str):
                keys.add(key.value)
            else:
                dynamic_access = True

    if any(name.name == 'kv' and id(name) not in accessed_names for name in parsed_template.find_all(nodes.Name)):
        dynamic_access = True

    return keys, dynamic_access


def find_favorite_query_template_keys(query: str) -> set[str]:
    """Return statically referenced keys from the template's ``kv`` dictionary."""
    keys, _dynamic_access = analyze_favorite_query_template(query)
    return keys


class FavoriteQueries:
    section_name: str = "favorite_queries"

    usage = """
Favorite Queries are a way to save frequently used queries
with a short name.
Examples:

    # Save a new favorite query.
    > /fs simple SELECT * FROM abc WHERE a IS NOT NULL;

    # When multi-line mode is on, pressing Return twice is needed to save.
    # This supports multi-statement favorites.

    # List all favorite queries.
    > /f
    ╒═══════════╤══════════════════════════════════════════════════╕
    │ Name      │ Query                                            │
    ╞═══════════╪══════════════════════════════════════════════════╡
    │ simple    │ SELECT * FROM abc WHERE a IS NOT NULL            │
    │ find_user │ SELECT * FROM users WHERE name = '{{ kv.name }}' │
    ╘═══════════╧══════════════════════════════════════════════════╛

    # Run a favorite query.
    > /f simple
    ╒════════╤════════╕
    │ a      │ b      │
    ╞════════╪════════╡
    │ 日本語 │ 日本語 │
    ╘════════╧════════╛

    # Run a favorite query containing {{ kv.name }} in the template.
    > /f find_user --name=henry
    > /f find_user --name henry

    # Run a favorite query containing positional parameter $1 in the
    # template.
    > /f find_user henry

    # Use -- to disambiguate positional parameters such as $1, especially
    # if the positional value starts with a dash.
    > /f query --key=value -- positional-value
    > /f query -- --positional-value-which-looks-like-a-flag--

    # Delete a favorite query.
    > /fd simple
    simple: Deleted.
"""

    # Class-level variable, for convenience to use as a singleton.
    instance: FavoriteQueries

    def __init__(self, config: Any, config_file: str | None = None) -> None:
        self.config = config
        self.config_file = config_file

    @classmethod
    def from_config(
        cls,
        config: Any,
        config_file: str | None = None,
        shared_favorites_file: str | None = None,
    ) -> FavoriteQueries:
        favorites = cls(config, config_file)
        if not shared_favorites_file:
            return favorites

        shared_favorites_file = os.path.expanduser(shared_favorites_file)
        if not os.path.isabs(shared_favorites_file):
            log(
                logger,
                logging.WARNING,
                f"Shared favorites file path must be absolute: '{shared_favorites_file}'.",
            )
            return favorites

        if not os.path.isfile(shared_favorites_file):
            log(
                logger,
                logging.WARNING,
                f"Unable to read shared favorites file '{shared_favorites_file}'.",
            )
            return favorites

        shared_config = read_config_file(shared_favorites_file)
        if shared_config is None:
            return favorites

        configured_queries = config.get(cls.section_name, {})
        shared_queries = shared_config.get(cls.section_name, {})
        config[cls.section_name] = {}
        config[cls.section_name].update(shared_queries)
        config[cls.section_name].update(configured_queries)
        return favorites

    def _clean_query(self, query: str | None) -> str | None:
        if not query:
            return query
        query = query.lstrip(' \t\n\r')
        query = query.rstrip(' \t\n\r')
        query = query.removesuffix(';')
        query = query.removesuffix(r'\G')
        query = query.removesuffix(r'\x')
        query = query.rstrip(' \t\n\r')
        return query

    def _config_for_write(self) -> Any:
        if self.config_file is None:
            return self.config

        config = read_config_file(self.config_file, preserve_quotes=True)
        if config is None:
            raise OSError(f"Unable to read config file '{os.path.expanduser(self.config_file)}'.")
        return config

    def _set_query(self, config: Any, name: str, query: str) -> None:
        if self.section_name not in config:
            config[self.section_name] = {}
        config[self.section_name][name] = query

    def list(self) -> list[str | None]:
        return [self._clean_query(x) for x in self.config.get(self.section_name, {})]

    def get(self, name) -> str | None:
        return self._clean_query(self.config.get(self.section_name, {}).get(name, None))

    def save(self, name: str, query: str) -> None:
        config = self._config_for_write()
        query = self._clean_query(query) or ''
        config.encoding = "utf-8"
        section_existed = self.section_name in config
        previous_query = config.get(self.section_name, {}).get(name, MISSING)
        self._set_query(config, name, query)
        try:
            config.write()
        except Exception:
            if previous_query is MISSING:
                del config[self.section_name][name]
                if not section_existed:
                    del config[self.section_name]
            else:
                config[self.section_name][name] = previous_query
            raise

        if config is not self.config:
            self._set_query(self.config, name, query)

    def delete(self, name: str) -> str:
        try:
            self.config[self.section_name][name]
        except KeyError:
            return f'{name}: Not Found.'

        config = self._config_for_write()
        if name in config.get(self.section_name, {}):
            query = config[self.section_name][name]
            del config[self.section_name][name]
            try:
                config.write()
            except Exception:
                config[self.section_name][name] = query
                raise

        if config is not self.config:
            del self.config[self.section_name][name]
        return f'{name}: Deleted.'

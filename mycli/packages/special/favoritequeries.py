from __future__ import annotations

import re

from jinja2 import meta, nodes
from jinja2.sandbox import SandboxedEnvironment

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
    > /fs simple select * from abc where a is not Null;

    # List all favorite queries.
    > /f
    ╒═══════════╤══════════════════════════════════════════════════╕
    │ Name      │ Query                                            │
    ╞═══════════╪══════════════════════════════════════════════════╡
    │ simple    │ SELECT * FROM abc where a is not NULL            │
    │ find_user │ SELECT * FROM users WHERE name = '{{ kv.name }}' │
    ╘═══════════╧══════════════════════════════════════════════════╛

    # Run a favorite query.
    > /f simple
    ╒════════╤════════╕
    │ a      │ b      │
    ╞════════╪════════╡
    │ 日本語 │ 日本語 │
    ╘════════╧════════╛

    # Run a favorite query containing {{ kv.name }} in the template:
    > /f find_user --name=henry
    > /f find_user --name henry

    # Run a favorite query containing $1 in the template:
    > /f find_user henry

    # Use -- to disambiguate positional parameters, especially if
    # the positional value starts with a dash.
    > /f query --key=value -- positional-value
    > /f query -- --positional-value-which-looks-like-a-flag--

    # Delete a favorite query.
    > /fd simple
    simple: Deleted.
"""

    # Class-level variable, for convenience to use as a singleton.
    instance: FavoriteQueries

    def __init__(self, config) -> None:
        self.config = config

    @classmethod
    def from_config(cls, config):
        return FavoriteQueries(config)

    def list(self) -> list[str | None]:
        return list(self.config.get(self.section_name, {}))

    def get(self, name) -> str | None:
        return self.config.get(self.section_name, {}).get(name, None)

    def save(self, name: str, query: str) -> None:
        self.config.encoding = "utf-8"
        if self.section_name not in self.config:
            self.config[self.section_name] = {}
        self.config[self.section_name][name] = query
        self.config.write()

    def delete(self, name: str) -> str:
        try:
            del self.config[self.section_name][name]
        except KeyError:
            return f'{name}: Not Found.'
        self.config.write()
        return f'{name}: Deleted.'

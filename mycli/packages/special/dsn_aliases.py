from __future__ import annotations

DSN_SUBCOMMANDS = {'help', 'list', 'show', 'save', 'delete'}


class DsnAliases:
    section_name: str = 'alias_dsn'

    usage = """
DSN aliases are a way to save frequently used connections
with a short alias.  You can manage them by editing ~/.myclirc
directly or by using this command.

Examples:

    # Show a DSN for the current connection
    mysql> /dsn show
    mysql://mycli@localhost/mysql

    # List all DSN aliases
    mysql> /dsn list
    ┌───────┬───────────────────────────────┐
    │ Alias │ DSN                           │
    ├───────┼───────────────────────────────┤
    │ rocks │ mysql://mycli@localhost/mysql │
    └───────┴───────────────────────────────┘

    # Save a new DSN alias based on the current connection.
    # The password will not be included!
    mysql> /dsn save connection_1

    # Delete a DSN alias.
    mysql> /dsn delete connection_1
"""

    # Class-level variable, for convenience to use as a singleton.
    instance: DsnAliases

    def __init__(self, config) -> None:
        self.config = config

    @classmethod
    def from_config(cls, config):
        return DsnAliases(config)

    def list(self) -> list[str]:
        return list(self.config.get(self.section_name, {}))

    def get(self, alias: str) -> str | None:
        return self.config.get(self.section_name, {}).get(alias, None)

    def save(self, alias: str, dsn: str) -> str:
        self.config.encoding = 'utf-8'
        if self.section_name not in self.config:
            self.config[self.section_name] = {}
        self.config[self.section_name][alias] = dsn
        self.config.write()
        return f'Saved: {alias}'

    def delete(self, alias: str) -> str:
        try:
            del self.config[self.section_name][alias]
        except KeyError:
            return f'Not Found: {alias}'
        self.config.write()
        return f'Deleted: {alias}'

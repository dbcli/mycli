from __future__ import annotations


class FavoriteQueries:
    section_name: str = "favorite_queries"

    usage = """
Favorite Queries are a way to save frequently used queries
with a short name.
Examples:

    # Save a new favorite query.
    > \\fs simple select * from abc where a is not Null;

    # List all favorite queries.
    > \\f
    ╒════════╤═══════════════════════════════════════╕
    │ Name   │ Query                                 │
    ╞════════╪═══════════════════════════════════════╡
    │ simple │ SELECT * FROM abc where a is not NULL │
    ╘════════╧═══════════════════════════════════════╛

    # Run a favorite query.
    > \\f simple
    ╒════════╤════════╕
    │ a      │ b      │
    ╞════════╪════════╡
    │ 日本語  │ 日本語  │
    ╘════════╧════════╛

    # Delete a favorite query.
    > \\fd simple
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
        return self.config.get(self.section_name, [])

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

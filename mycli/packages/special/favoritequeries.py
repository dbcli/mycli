# -*- coding: utf-8 -*-
from __future__ import unicode_literals

class FavoriteQueries(object):

    section_name = 'favorite_queries'

    usage = '''
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
    │ 日本語 │ 日本語 │
    ╘════════╧════════╛

    # Delete a favorite query.
    > \\fd simple
    simple: Deleted
'''

    def __init__(self, config):
        self.config = config

    def list(self):
        return self.config.get(self.section_name, [])

    def get(self, name):
        return self.config.get(self.section_name, {}).get(name, None)

    def save(self, name, query):
        if self.section_name not in self.config:
            self.config[self.section_name] = {}
        self.config[self.section_name][name] = query
        self.config.write()

    def delete(self, name):
        try:
            del self.config[self.section_name][name]
        except KeyError:
            return '%s: Not Found.' % name
        self.config.write()
        return '%s: Deleted' % name

from ...config import read_config_file
favoritequeries = FavoriteQueries(read_config_file('~/.myclirc'))

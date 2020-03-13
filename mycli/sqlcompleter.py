from __future__ import print_function
from __future__ import unicode_literals
import logging
from re import compile, escape
from collections import Counter

from prompt_toolkit.completion import Completion

from sqlcomplete.parseutils.utils import last_word
from sqlcomplete.sqlcompleter import SQLCompleter

from .packages.completion_engine import suggest_type
from .packages.filepaths import parse_path, complete_path, suggest_path
from .packages.special.iocommands import favoritequeries

_logger = logging.getLogger(__name__)


class MySQLCompleter(SQLCompleter):
    name_escape_char = '`'

    def __init__(self, smart_completion=True, settings=None, supported_formats=(), keyword_casing='auto'):
        super(self.__class__, self).__init__(smart_completion, settings)
        # self.smart_completion = smart_completion
        # self.reserved_words = set()
        # for x in self.keywords:
        #     self.reserved_words.update(x.split())
        # self.name_pattern = compile("^[_a-z][_a-z0-9\$]*$")
        #
        self.special_commands = []
        self.change_items = []
        self.users = []
        self.show_items = []
        # self.table_formats = supported_formats
        # if keyword_casing not in ('upper', 'lower', 'auto'):
        #     keyword_casing = 'auto'
        # self.keyword_casing = keyword_casing
        # self.reset_completions()

    def extend_special_commands(self, special_commands):
        # Special commands are not part of all_completions since they can only
        # be at the beginning of a line.
        self.special_commands.extend(special_commands)

    def extend_show_items(self, show_items):
        for show_item in show_items:
            self.show_items.extend(show_item)
            self.all_completions.update(show_item)

    def extend_users(self, users):
        for user in users:
            self.users.extend(user)
            self.all_completions.update(user)

    # def extend_relations(self, data, kind):
    #     """Extend metadata for tables or views
    #
    #     :param data: list of (rel_name, ) tuples
    #     :param kind: either 'tables' or 'views'
    #     :return:
    #     """
    #     # 'data' is a generator object. It can throw an exception while being
    #     # consumed. This could happen if the user has launched the app without
    #     # specifying a database name. This exception must be handled to prevent
    #     # crashing.
    #     try:
    #         data = [self.escaped_names(d) for d in data]
    #     except Exception:
    #         data = []
    #
    #     # dbmetadata['tables'][$schema_name][$table_name] should be a list of
    #     # column names. Default to an asterisk
    #     metadata = self.dbmetadata[kind]
    #     for relname in data:
    #         try:
    #             metadata[self.dbname][relname[0]] = ['*']
    #         except KeyError:
    #             _logger.error('%r %r listed in unrecognized schema %r',
    #                           kind, relname[0], self.dbname)
    #         self.all_completions.add(relname[0])

    # def extend_columns(self, column_data, kind):
    #     """Extend column metadata
    #
    #     :param column_data: list of (rel_name, column_name) tuples
    #     :param kind: either 'tables' or 'views'
    #     :return:
    #     """
    #     # 'column_data' is a generator object. It can throw an exception while
    #     # being consumed. This could happen if the user has launched the app
    #     # without specifying a database name. This exception must be handled to
    #     # prevent crashing.
    #     try:
    #         column_data = [self.escaped_names(d) for d in column_data]
    #     except Exception:
    #         column_data = []
    #
    #     metadata = self.dbmetadata[kind]
    #     for relname, column in column_data:
    #         metadata[self.dbname][relname].append(column)
    #         self.all_completions.add(column)

    # def extend_functions(self, func_data):
    #     # 'func_data' is a generator object. It can throw an exception while
    #     # being consumed. This could happen if the user has launched the app
    #     # without specifying a database name. This exception must be handled to
    #     # prevent crashing.
    #     try:
    #         func_data = [self.escaped_names(d) for d in func_data]
    #     except Exception:
    #         func_data = []
    #
    #     # dbmetadata['functions'][$schema_name][$function_name] should return
    #     # function metadata.
    #     metadata = self.dbmetadata['functions']
    #
    #     for func in func_data:
    #         metadata[self.dbname][func[0]] = None
    #         self.all_completions.add(func[0])

    def set_dbname(self, dbname):
        self.dbname = dbname

    def reset_completions(self):
        super(MySQLCompleter, self).reset_completions()
        self.set_dbname('')
        self.users = []
        self.show_items = []

    # @staticmethod
    # def find_matches(text, collection, start_only=False, fuzzy=True, casing=None):
    #     """Find completion matches for the given text.
    #
    #     Given the user's input text and a collection of available
    #     completions, find completions matching the last word of the
    #     text.
    #
    #     If `start_only` is True, the text will match an available
    #     completion only at the beginning. Otherwise, a completion is
    #     considered a match if the text appears anywhere within it.
    #
    #     yields prompt_toolkit Completion instances for any matches found
    #     in the collection of available completions.
    #     """
    #     last = last_word(text, include='most_punctuations')
    #     text = last.lower()
    #
    #     completions = []
    #
    #     if fuzzy:
    #         regex = '.*?'.join(map(escape, text))
    #         pat = compile('(%s)' % regex)
    #         for item in sorted(collection):
    #             r = pat.search(item.lower())
    #             if r:
    #                 completions.append((len(r.group()), r.start(), item))
    #     else:
    #         match_end_limit = len(text) if start_only else None
    #         for item in sorted(collection):
    #             match_point = item.lower().find(text, 0, match_end_limit)
    #             if match_point >= 0:
    #                 completions.append((len(text), match_point, item))
    #
    #     if casing == 'auto':
    #         casing = 'lower' if last and last[-1].islower() else 'upper'
    #
    #     def apply_case(kw):
    #         if casing == 'upper':
    #             return kw.upper()
    #         return kw.lower()
    #
    #     return (Completion(z if casing is None else apply_case(z), -len(text))
    #             for x, y, z in sorted(completions))

    # def get_completions(self, document, complete_event, smart_completion=None):
    #     word_before_cursor = document.get_word_before_cursor(WORD=True)
    #     if smart_completion is None:
    #         smart_completion = self.smart_completion
    #
    #     # If smart_completion is off then match any word that starts with
    #     # 'word_before_cursor'.
    #     if not smart_completion:
    #         return self.find_matches(word_before_cursor, self.all_completions,
    #                                  start_only=True, fuzzy=False)
    #
    #     completions = []
    #     suggestions = suggest_type(document.text, document.text_before_cursor)
    #
    #     for suggestion in suggestions:
    #
    #         _logger.debug('Suggestion type: %r', suggestion['type'])
    #
    #         if suggestion['type'] == 'column':
    #             tables = suggestion['tables']
    #             _logger.debug("Completion column scope: %r", tables)
    #             scoped_cols = self.populate_scoped_cols(tables)
    #             if suggestion.get('drop_unique'):
    #                 # drop_unique is used for 'tb11 JOIN tbl2 USING (...'
    #                 # which should suggest only columns that appear in more than
    #                 # one table
    #                 scoped_cols = [
    #                     col for (col, count) in Counter(scoped_cols).items()
    #                     if count > 1 and col != '*'
    #                 ]
    #
    #             cols = self.find_matches(word_before_cursor, scoped_cols)
    #             completions.extend(cols)
    #
    #         elif suggestion['type'] == 'function':
    #             # suggest user-defined functions using substring matching
    #             funcs = self.populate_schema_objects(suggestion['schema'],
    #                                                  'functions')
    #             user_funcs = self.find_matches(word_before_cursor, funcs)
    #             completions.extend(user_funcs)
    #
    #             # suggest hardcoded functions using startswith matching only if
    #             # there is no schema qualifier. If a schema qualifier is
    #             # present it probably denotes a table.
    #             # eg: SELECT * FROM users u WHERE u.
    #             if not suggestion['schema']:
    #                 predefined_funcs = self.find_matches(word_before_cursor,
    #                                                      self.functions,
    #                                                      start_only=True,
    #                                                      fuzzy=False,
    #                                                      casing=self.keyword_casing)
    #                 completions.extend(predefined_funcs)
    #
    #         elif suggestion['type'] == 'table':
    #             tables = self.populate_schema_objects(suggestion['schema'],
    #                                                   'tables')
    #             tables = self.find_matches(word_before_cursor, tables)
    #             completions.extend(tables)
    #
    #         elif suggestion['type'] == 'view':
    #             views = self.populate_schema_objects(suggestion['schema'],
    #                                                  'views')
    #             views = self.find_matches(word_before_cursor, views)
    #             completions.extend(views)
    #
    #         elif suggestion['type'] == 'alias':
    #             aliases = suggestion['aliases']
    #             aliases = self.find_matches(word_before_cursor, aliases)
    #             completions.extend(aliases)
    #
    #         elif suggestion['type'] == 'database':
    #             dbs = self.find_matches(word_before_cursor, self.databases)
    #             completions.extend(dbs)
    #
    #         elif suggestion['type'] == 'keyword':
    #             keywords = self.find_matches(word_before_cursor, self.keywords,
    #                                          start_only=True,
    #                                          fuzzy=False,
    #                                          casing=self.keyword_casing)
    #             completions.extend(keywords)
    #
    #         elif suggestion['type'] == 'show':
    #             show_items = self.find_matches(word_before_cursor,
    #                                            self.show_items,
    #                                            start_only=False,
    #                                            fuzzy=True,
    #                                            casing=self.keyword_casing)
    #             completions.extend(show_items)
    #
    #         elif suggestion['type'] == 'change':
    #             change_items = self.find_matches(word_before_cursor,
    #                                              self.change_items,
    #                                              start_only=False,
    #                                              fuzzy=True)
    #             completions.extend(change_items)
    #         elif suggestion['type'] == 'user':
    #             users = self.find_matches(word_before_cursor, self.users,
    #                                       start_only=False,
    #                                       fuzzy=True)
    #             completions.extend(users)
    #
    #         elif suggestion['type'] == 'special':
    #             special = self.find_matches(word_before_cursor,
    #                                         self.special_commands,
    #                                         start_only=True,
    #                                         fuzzy=False)
    #             completions.extend(special)
    #         elif suggestion['type'] == 'favoritequery':
    #             queries = self.find_matches(word_before_cursor,
    #                                         favoritequeries.list(),
    #                                         start_only=False, fuzzy=True)
    #             completions.extend(queries)
    #         elif suggestion['type'] == 'table_format':
    #             formats = self.find_matches(word_before_cursor,
    #                                         self.table_formats,
    #                                         start_only=True, fuzzy=False)
    #             completions.extend(formats)
    #         elif suggestion['type'] == 'file_name':
    #             file_names = self.find_files(word_before_cursor)
    #             completions.extend(file_names)
    #
    #     return completions

    def find_files(self, word):
        """Yield matching directory or file names.

        :param word:
        :return: iterable

        """
        base_path, last_path, position = parse_path(word)
        paths = suggest_path(word)
        for name in sorted(paths):
            suggestion = complete_path(name, last_path)
            if suggestion:
                yield Completion(suggestion, position)

    # def populate_scoped_cols(self, scoped_tbls):
    #     """Find all columns in a set of scoped_tables
    #     :param scoped_tbls: list of (schema, table, alias) tuples
    #     :return: list of column names
    #     """
    #     columns = []
    #     meta = self.dbmetadata
    #
    #     for tbl in scoped_tbls:
    #         # A fully qualified schema.relname reference or default_schema
    #         # DO NOT escape schema names.
    #         schema = tbl.schema or self.dbname
    #         relname = tbl.name
    #         escaped_relname = self.escape_name(relname)
    #
    #         # We don't know if schema.relname is a table or view. Since
    #         # tables and views cannot share the same name, we can check one
    #         # at a time
    #         try:
    #             columns.extend(meta['tables'][schema][relname])
    #
    #             # Table exists, so don't bother checking for a view
    #             continue
    #         except KeyError:
    #             try:
    #                 columns.extend(meta['tables'][schema][escaped_relname])
    #                 # Table exists, so don't bother checking for a view
    #                 continue
    #             except KeyError:
    #                 pass
    #
    #         try:
    #             columns.extend(meta['views'][schema][relname])
    #         except KeyError:
    #             pass
    #
    #     return columns

    # def populate_schema_objects(self, schema, obj_type):
    #     """Returns list of tables or functions for a (optional) schema"""
    #     metadata = self.dbmetadata[obj_type]
    #     schema = schema or self.dbname
    #
    #     try:
    #         objects = metadata[schema].keys()
    #     except KeyError:
    #         # schema doesn't exist
    #         objects = []
    #
    #     return objects

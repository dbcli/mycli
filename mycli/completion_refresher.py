import threading
from .packages.special.main import COMMANDS
try:
    from collections import OrderedDict
except ImportError:
    from .packages.ordereddict import OrderedDict

from .sqlcompleter import SQLCompleter
from .sqlexecute import SQLExecute

class CompletionRefresher(object):

    refreshers = OrderedDict()

    def __init__(self):
        self._completer_thread = None
        self._restart_refresh = threading.Event()

    def refresh(self, executor, callbacks):
        """
        Creates a SQLCompleter object and populates it with the relevant
        completion suggestions in a background thread.

        executor - SQLExecute object, used to extract the credentials to connect
                   to the database.
        callbacks - A function or a list of functions to call after the thread
                    has completed the refresh. The newly created completion
                    object will be passed in as an argument to each callback.
        """
        if self.is_refreshing():
            self._restart_refresh.set()
            return [(None, None, None, 'Auto-completion refresh restarted.')]
        else:
            self._completer_thread = threading.Thread(target=self._bg_refresh,
                                                      args=(executor, callbacks),
                                                      name='completion_refresh')
            self._completer_thread.setDaemon(True)
            self._completer_thread.start()
            return [(None, None, None,
                     'Auto-completion refresh started in the background.')]

    def is_refreshing(self):
        return self._completer_thread and self._completer_thread.is_alive()

    def _bg_refresh(self, sqlexecute, callbacks):
        completer = SQLCompleter(smart_completion=True)

        # Create a new pgexecute method to popoulate the completions.
        e = sqlexecute
        executor = SQLExecute(e.dbname, e.user, e.password, e.host, e.port,
                              e.socket, e.charset, e.local_infile, e.ssl)

        # If callbacks is a single function then push it into a list.
        if callable(callbacks):
            callbacks = [callbacks]

        while 1:
            for refresher in self.refreshers.values():
                refresher(completer, executor)
                if self._restart_refresh.is_set():
                    self._restart_refresh.clear()
                    break
            else:
                # Break out of while loop if the for loop finishes natually
                # without hitting the break statement.
                break

            # Start over the refresh from the beginning if the for loop hit the
            # break statement.
            continue

        for callback in callbacks:
            callback(completer)

def refresher(name, refreshers=CompletionRefresher.refreshers):
    """Decorator to add the decorated function to the dictionary of
    refreshers. Any function decorated with a @refresher will be executed as
    part of the completion refresh routine."""
    def wrapper(wrapped):
        refreshers[name] = wrapped
        return wrapped
    return wrapper

@refresher('databases')
def refresh_databases(completer, executor):
    completer.extend_database_names(executor.databases())

@refresher('schemata')
def refresh_schemata(completer, executor):
    # schemata - In MySQL Schema is the same as database. But for mycli
    # schemata will be the name of the current database.
    completer.extend_schemata(executor.dbname)
    completer.set_dbname(executor.dbname)

@refresher('tables')
def refresh_tables(completer, executor):
    completer.extend_relations(executor.tables(), kind='tables')
    completer.extend_columns(executor.table_columns(), kind='tables')

@refresher('users')
def refresh_users(completer, executor):
    completer.extend_users(executor.users())

# @refresher('views')
# def refresh_views(completer, executor):
#     completer.extend_relations(executor.views(), kind='views')
#     completer.extend_columns(executor.view_columns(), kind='views')

@refresher('functions')
def refresh_functions(completer, executor):
    completer.extend_functions(executor.functions())

@refresher('special_commands')
def refresh_special(completer, executor):
    completer.extend_special_commands(COMMANDS.keys())

@refresher('show_commands')
def refresh_show_commands(completer, executor):
    completer.extend_show_items(executor.show_candidates())

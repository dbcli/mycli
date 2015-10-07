"""Connection and cursor wrappers around PyMySQL.

This module effectively backports PyMySQL functionality and error handling
so that mycli will support Debian's python-pymysql version (0.6.2).
"""

import pymysql

Cursor = pymysql.cursors.Cursor
connect = pymysql.connect


if pymysql.VERSION[1] == 6 and pymysql.VERSION[2] < 5:
    class Cursor(pymysql.cursors.Cursor):
        """Makes Cursor a context manager in PyMySQL < 0.6.5."""

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            del exc_info
            self.close()


if pymysql.VERSION[1] == 6 and pymysql.VERSION[2] < 3:
    class Connection(pymysql.connections.Connection):
        """Adds error handling to Connection in PyMySQL < 0.6.3."""

        def __del__(self):
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            self.socket = None
            self._rfile = None

    def connect(*args, **kwargs):
        """Makes connect() use our custom Connection class.

        PyMySQL < 0.6.3 uses the *passwd* argument instead of *password*. This
        function renames that keyword or assigns it the default value of '',
        which is the same default value PyMySQL gives it.

        See pymysql.connections.Connection.__init__() for more information
        about calling this function.
        """

        kwargs['passwd'] = kwargs.pop('password', '')

        return Connection(*args, **kwargs)

import logging
import pymysql
import sqlparse
from .packages import dbspecial
from .encodingutils import unicode2utf8

_logger = logging.getLogger(__name__)

class SQLExecute(object):

    databases_query = '''SHOW DATABASES'''

    tables_query = '''SHOW TABLES'''

    columns_query = '''SHOW COLUMNS FROM %s'''

    functions_query = ''' '''

    table_columns_query = '''select TABLE_NAME, COLUMN_NAME from information_schema.columns
                                    where table_schema = '%s'
                                    order by table_name,ordinal_position'''

    def __init__(self, database, user, password, host, port):
        self.dbname = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.connect()

    def connect(self, database=None, user=None, password=None, host=None,
            port=None):

        db = unicode2utf8(database or self.dbname)
        user = unicode2utf8(user or self.user)
        password = unicode2utf8(password or self.password)
        host = unicode2utf8(host or self.host)
        port = unicode2utf8(port or self.port)
        conn = pymysql.connect(database=db, user=user, password=password,
                host=host, port=port)
        if hasattr(self, 'conn'):
            self.conn.close()
        self.conn = conn
        self.conn.autocommit = True
        # Update them after the connection is made to ensure that it was a
        # successful connection.
        self.dbname = db
        self.user = user
        self.host = host
        self.port = port

    def run(self, statement):
        """Execute the sql in the database and return the results. The results
        are a list of tuples. Each tuple has 4 values (title, rows, headers, status).
        """

        # Remove spaces and EOL
        statement = statement.strip()
        if not statement:  # Empty string
            yield (None, None, None, None)

        # Split the sql into separate queries and run each one.
        for sql in sqlparse.split(statement):
            # Remove spaces, eol and semi-colons.
            sql = sql.rstrip(';')

            # \G is treated specially since we have to set the expanded output
            # and then proceed to execute the sql as normal.
            if sql.endswith('\\G'):
                dbspecial.set_expanded_output(True)
                yield self.execute_normal_sql(sql.rsplit('\\G', 1)[0])
            else:
                try:   # Special command
                    _logger.debug('Trying a dbspecial command. sql: %r', sql)
                    cur = self.conn.cursor()
                    for result in dbspecial.execute(cur, sql, self):
                        yield result
                except KeyError:  # Regular SQL
                    yield self.execute_normal_sql(sql)

    def execute_normal_sql(self, split_sql):
        _logger.debug('Regular sql statement. sql: %r', split_sql)
        cur = self.conn.cursor()
        cur.execute(split_sql)
        title = None
        # cur.description will be None for operations that do not return
        # rows.
        if cur.description:
            headers = [x[0] for x in cur.description]
            return (title, cur, headers, None)  # cur.statusmessage)
        else:
            _logger.debug('No rows in result.')
            return (title, None, None, None)  # cur.statusmessage)

    def tables(self):
        """Yields table names"""

        with self.conn.cursor() as cur:
            _logger.debug('Tables Query. sql: %r', self.tables_query)
            cur.execute(self.tables_query)
            for row in cur:
                yield row

    def table_columns(self):
        """Yields column names"""
        with self.conn.cursor() as cur:
            _logger.debug('Columns Query. sql: %r', self.table_columns_query)
            cur.execute(self.table_columns_query % self.dbname)
            for row in cur:
                yield row

    def databases(self):
        with self.conn.cursor() as cur:
            _logger.debug('Databases Query. sql: %r', self.databases_query)
            cur.execute(self.databases_query)
            return [x[0] for x in cur.fetchall()]

    def functions(self):
        """Yields tuples of (schema_name, function_name)"""

        with self.conn.cursor() as cur:
            _logger.debug('Functions Query. sql: %r', self.functions_query)
            cur.execute(self.functions_query)
            for row in cur:
                yield row

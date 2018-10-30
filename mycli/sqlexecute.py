import logging
import pymysql
import sqlparse
from .packages import special
from pymysql.constants import FIELD_TYPE
from pymysql.converters import (convert_mysql_timestamp, convert_datetime,
                                convert_timedelta, convert_date, conversions,
                                decoders)
try:
    import paramiko
except:
    paramiko = False

_logger = logging.getLogger(__name__)

FIELD_TYPES = decoders.copy()
FIELD_TYPES.update({
    FIELD_TYPE.NULL: type(None)
})

class SQLExecute(object):

    databases_query = '''SHOW DATABASES'''

    tables_query = '''SHOW TABLES'''

    version_query = '''SELECT @@VERSION'''

    version_comment_query = '''SELECT @@VERSION_COMMENT'''
    version_comment_query_mysql4 = '''SHOW VARIABLES LIKE "version_comment"'''

    show_candidates_query = '''SELECT name from mysql.help_topic WHERE name like "SHOW %"'''

    users_query = '''SELECT CONCAT("'", user, "'@'",host,"'") FROM mysql.user'''

    functions_query = '''SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES
    WHERE ROUTINE_TYPE="FUNCTION" AND ROUTINE_SCHEMA = "%s"'''

    table_columns_query = '''select TABLE_NAME, COLUMN_NAME from information_schema.columns
                                    where table_schema = '%s'
                                    order by table_name,ordinal_position'''

    def __init__(self, database, user, password, host, port, socket, charset,
                 local_infile, ssl, ssh_user, ssh_host, ssh_port, ssh_password,
                 ssh_key_filename):
        self.dbname = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.socket = socket
        self.charset = charset
        self.local_infile = local_infile
        self.ssl = ssl
        self._server_type = None
        self.connection_id = None
        self.ssh_user = ssh_user
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_password = ssh_password
        self.ssh_key_filename = ssh_key_filename
        self.connect()

    def connect(self, database=None, user=None, password=None, host=None,
                port=None, socket=None, charset=None, local_infile=None,
                ssl=None, ssh_host=None, ssh_port=None, ssh_user=None,
                ssh_password=None, ssh_key_filename=None):
        db = (database or self.dbname)
        user = (user or self.user)
        password = (password or self.password)
        host = (host or self.host)
        port = (port or self.port)
        socket = (socket or self.socket)
        charset = (charset or self.charset)
        local_infile = (local_infile or self.local_infile)
        ssl = (ssl or self.ssl)
        ssh_user = (ssh_user or self.ssh_user)
        ssh_host = (ssh_host or self.ssh_host)
        ssh_port = (ssh_port or self.ssh_port)
        ssh_password = (ssh_password or self.ssh_password)
        ssh_key_filename = (ssh_key_filename or self.ssh_key_filename)
        _logger.debug(
            'Connection DB Params: \n'
            '\tdatabase: %r'
            '\tuser: %r'
            '\thost: %r'
            '\tport: %r'
            '\tsocket: %r'
            '\tcharset: %r'
            '\tlocal_infile: %r'
            '\tssl: %r'
            '\tssh_user: %r'
            '\tssh_host: %r'
            '\tssh_port: %r'
            '\tssh_password: %r'
            '\tssh_key_filename: %r',
            db, user, host, port, socket, charset, local_infile, ssl,
            ssh_user, ssh_host, ssh_port, ssh_password, ssh_key_filename
        )
        conv = conversions.copy()
        conv.update({
            FIELD_TYPE.TIMESTAMP: lambda obj: (convert_mysql_timestamp(obj) or obj),
            FIELD_TYPE.DATETIME: lambda obj: (convert_datetime(obj) or obj),
            FIELD_TYPE.TIME: lambda obj: (convert_timedelta(obj) or obj),
            FIELD_TYPE.DATE: lambda obj: (convert_date(obj) or obj),
        })

        defer_connect = False

        if ssh_host:
            defer_connect = True

        conn = pymysql.connect(
            database=db, user=user, password=password, host=host, port=port,
            unix_socket=socket, use_unicode=True, charset=charset,
            autocommit=True, client_flag=pymysql.constants.CLIENT.INTERACTIVE,
            local_infile=local_infile, conv=conv, ssl=ssl, program_name="mycli",
            defer_connect=defer_connect
        )

        if ssh_host and paramiko:
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
            client.connect(
                ssh_host, ssh_port, ssh_user, ssh_password,
                key_filename=ssh_key_filename
            )
            chan = client.get_transport().open_channel(
                'direct-tcpip',
                (host, port),
                ('0.0.0.0', 0),
            )
            conn.connect(chan)

        if hasattr(self, 'conn'):
            self.conn.close()
        self.conn = conn
        # Update them after the connection is made to ensure that it was a
        # successful connection.
        self.dbname = db
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.socket = socket
        self.charset = charset
        self.ssl = ssl
        # retrieve connection id
        self.reset_connection_id()

    def run(self, statement):
        """Execute the sql in the database and return the results. The results
        are a list of tuples. Each tuple has 4 values
        (title, rows, headers, status).
        """

        # Remove spaces and EOL
        statement = statement.strip()
        if not statement:  # Empty string
            yield (None, None, None, None)

        # Split the sql into separate queries and run each one.
        # Unless it's saving a favorite query, in which case we
        # want to save them all together.
        if statement.startswith('\\fs'):
            components = [statement]
        else:
            components = sqlparse.split(statement)

        for sql in components:
            # Remove spaces, eol and semi-colons.
            sql = sql.rstrip(';')

            # \G is treated specially since we have to set the expanded output.
            if sql.endswith('\\G'):
                special.set_expanded_output(True)
                sql = sql[:-2].strip()

            cur = self.conn.cursor()
            try:   # Special command
                _logger.debug('Trying a dbspecial command. sql: %r', sql)
                for result in special.execute(cur, sql):
                    yield result
            except special.CommandNotFound:  # Regular SQL
                _logger.debug('Regular sql statement. sql: %r', sql)
                cur.execute(sql)
                while True:
                    yield self.get_result(cur)

                    # PyMySQL returns an extra, empty result set with stored
                    # procedures. We skip it (rowcount is zero and no
                    # description).
                    if not cur.nextset() or (not cur.rowcount and cur.description is None):
                        break

    def get_result(self, cursor):
        """Get the current result's data from the cursor."""
        title = headers = None

        # cursor.description is not None for queries that return result sets,
        # e.g. SELECT or SHOW.
        if cursor.description is not None:
            headers = [x[0] for x in cursor.description]
            status = '{0} row{1} in set'
        else:
            _logger.debug('No rows in result.')
            status = 'Query OK, {0} row{1} affected'
        status = status.format(cursor.rowcount,
                               '' if cursor.rowcount == 1 else 's')

        return (title, cursor if cursor.description else None, headers, status)

    def tables(self):
        """Yields table names"""

        with self.conn.cursor() as cur:
            _logger.debug('Tables Query. sql: %r', self.tables_query)
            cur.execute(self.tables_query)
            for row in cur:
                yield row

    def table_columns(self):
        """Yields (table name, column name) pairs"""
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
            cur.execute(self.functions_query % self.dbname)
            for row in cur:
                yield row

    def show_candidates(self):
        with self.conn.cursor() as cur:
            _logger.debug('Show Query. sql: %r', self.show_candidates_query)
            try:
                cur.execute(self.show_candidates_query)
            except pymysql.DatabaseError as e:
                _logger.error('No show completions due to %r', e)
                yield ''
            else:
                for row in cur:
                    yield (row[0].split(None, 1)[-1], )

    def users(self):
        with self.conn.cursor() as cur:
            _logger.debug('Users Query. sql: %r', self.users_query)
            try:
                cur.execute(self.users_query)
            except pymysql.DatabaseError as e:
                _logger.error('No user completions due to %r', e)
                yield ''
            else:
                for row in cur:
                    yield row

    def server_type(self):
        if self._server_type:
            return self._server_type
        with self.conn.cursor() as cur:
            _logger.debug('Version Query. sql: %r', self.version_query)
            cur.execute(self.version_query)
            version = cur.fetchone()[0]
            if version[0] == '4':
                _logger.debug('Version Comment. sql: %r',
                              self.version_comment_query_mysql4)
                cur.execute(self.version_comment_query_mysql4)
                version_comment = cur.fetchone()[1].lower()
                if isinstance(version_comment, bytes):
                    # with python3 this query returns bytes
                    version_comment = version_comment.decode('utf-8')
            else:
                _logger.debug('Version Comment. sql: %r',
                              self.version_comment_query)
                cur.execute(self.version_comment_query)
                version_comment = cur.fetchone()[0].lower()

        if 'mariadb' in version_comment:
            product_type = 'mariadb'
        elif 'percona' in version_comment:
            product_type = 'percona'
        else:
            product_type = 'mysql'

        self._server_type = (product_type, version)
        return self._server_type

    def get_connection_id(self):
        if not self.connection_id:
            self.reset_connection_id()
        return self.connection_id

    def reset_connection_id(self):
        # Remember current connection id
        _logger.debug('Get current connection id')
        res = self.run('select connection_id()')
        for title, cur, headers, status in res:
            self.connection_id = cur.fetchone()[0]
        _logger.debug('Current connection id: %s', self.connection_id)

    def change_db(self, db):
        self.conn.select_db(db)
        self.dbname = db

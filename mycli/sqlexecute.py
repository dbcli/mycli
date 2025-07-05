import enum
import logging
import re

import pymysql
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions, convert_date, convert_datetime, convert_timedelta, decoders

from mycli.packages import special

try:
    import paramiko  # noqa: F401
    import sshtunnel
except ImportError:
    pass

_logger = logging.getLogger(__name__)

FIELD_TYPES = decoders.copy()
FIELD_TYPES.update({FIELD_TYPE.NULL: type(None)})


ERROR_CODE_ACCESS_DENIED = 1045


class ServerSpecies(enum.Enum):
    MySQL = "MySQL"
    MariaDB = "MariaDB"
    Percona = "Percona"
    TiDB = "TiDB"
    Unknown = "Unknown"


class ServerInfo:
    def __init__(self, species, version_str):
        self.species = species
        self.version_str = version_str
        self.version = self.calc_mysql_version_value(version_str)

    @staticmethod
    def calc_mysql_version_value(version_str) -> int:
        if not version_str or not isinstance(version_str, str):
            return 0
        try:
            major, minor, patch = version_str.split(".")
        except ValueError:
            return 0
        else:
            return int(major) * 10_000 + int(minor) * 100 + int(patch)

    @classmethod
    def from_version_string(cls, version_string):
        if not version_string:
            return cls(ServerSpecies.MySQL, "")

        re_species = (
            (r"(?P<version>[0-9\.]+)-MariaDB", ServerSpecies.MariaDB),
            (r"[0-9\.]*-TiDB-v(?P<version>[0-9\.]+)-?(?P<comment>[a-z0-9\-]*)", ServerSpecies.TiDB),
            (r"(?P<version>[0-9\.]+)[a-z0-9]*-(?P<comment>[0-9]+$)", ServerSpecies.Percona),
            (r"(?P<version>[0-9\.]+)[a-z0-9]*-(?P<comment>[A-Za-z0-9_]+)", ServerSpecies.MySQL),
        )
        for regexp, species in re_species:
            match = re.search(regexp, version_string)
            if match is not None:
                parsed_version = match.group("version")
                detected_species = species
                break
        else:
            detected_species = ServerSpecies.MySQL
            parsed_version = ""

        return cls(detected_species, parsed_version)

    def __str__(self):
        if self.species:
            return f"{self.species.value} {self.version_str}"
        else:
            return self.version_str


class SQLExecute(object):
    databases_query = """SHOW DATABASES"""

    tables_query = """SHOW TABLES"""

    show_candidates_query = '''SELECT name from mysql.help_topic WHERE name like "SHOW %"'''

    users_query = """SELECT CONCAT("'", user, "'@'",host,"'") FROM mysql.user"""

    functions_query = '''SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES
    WHERE ROUTINE_TYPE="FUNCTION" AND ROUTINE_SCHEMA = "%s"'''

    table_columns_query = """select TABLE_NAME, COLUMN_NAME from information_schema.columns
                                    where table_schema = '%s'
                                    order by table_name,ordinal_position"""

    now_query = """SELECT NOW()"""

    def __init__(
        self,
        database,
        user,
        password,
        host,
        port,
        socket,
        charset,
        local_infile,
        ssl,
        ssh_user,
        ssh_host,
        ssh_port,
        ssh_password,
        ssh_key_filename,
        init_command=None,
    ):
        self.dbname = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.socket = socket
        self.charset = charset
        self.local_infile = local_infile
        self.ssl = ssl
        self.server_info = None
        self.connection_id = None
        self.ssh_user = ssh_user
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_password = ssh_password
        self.ssh_key_filename = ssh_key_filename
        self.init_command = init_command
        self.connect()

    def connect(
        self,
        database=None,
        user=None,
        password=None,
        host=None,
        port=None,
        socket=None,
        charset=None,
        local_infile=None,
        ssl=None,
        ssh_host=None,
        ssh_port=None,
        ssh_user=None,
        ssh_password=None,
        ssh_key_filename=None,
        init_command=None,
    ):
        db = database or self.dbname
        user = user or self.user
        password = password or self.password
        host = host or self.host
        port = port or self.port
        socket = socket or self.socket
        charset = charset or self.charset
        local_infile = local_infile or self.local_infile
        ssl = ssl or self.ssl
        ssh_user = ssh_user or self.ssh_user
        ssh_host = ssh_host or self.ssh_host
        ssh_port = ssh_port or self.ssh_port
        ssh_password = ssh_password or self.ssh_password
        ssh_key_filename = ssh_key_filename or self.ssh_key_filename
        init_command = init_command or self.init_command
        _logger.debug(
            "Connection DB Params: \n"
            "\tdatabase: %r"
            "\tuser: %r"
            "\thost: %r"
            "\tport: %r"
            "\tsocket: %r"
            "\tcharset: %r"
            "\tlocal_infile: %r"
            "\tssl: %r"
            "\tssh_user: %r"
            "\tssh_host: %r"
            "\tssh_port: %r"
            "\tssh_password: %r"
            "\tssh_key_filename: %r"
            "\tinit_command: %r",
            db,
            user,
            host,
            port,
            socket,
            charset,
            local_infile,
            ssl,
            ssh_user,
            ssh_host,
            ssh_port,
            ssh_password,
            ssh_key_filename,
            init_command,
        )
        conv = conversions.copy()
        conv.update({
            FIELD_TYPE.TIMESTAMP: lambda obj: (convert_datetime(obj) or obj),
            FIELD_TYPE.DATETIME: lambda obj: (convert_datetime(obj) or obj),
            FIELD_TYPE.TIME: lambda obj: (convert_timedelta(obj) or obj),
            FIELD_TYPE.DATE: lambda obj: (convert_date(obj) or obj),
        })

        defer_connect = False

        if ssh_host:
            defer_connect = True

        client_flag = pymysql.constants.CLIENT.INTERACTIVE
        if init_command and len(list(special.split_queries(init_command))) > 1:
            client_flag |= pymysql.constants.CLIENT.MULTI_STATEMENTS

        ssl_context = None
        if ssl:
            ssl_context = self._create_ssl_ctx(ssl)

        conn = pymysql.connect(
            database=db,
            user=user,
            password=password,
            host=host,
            port=port,
            unix_socket=socket,
            use_unicode=True,
            charset=charset,
            autocommit=True,
            client_flag=client_flag,
            local_infile=local_infile,
            conv=conv,
            ssl=ssl_context,
            program_name="mycli",
            defer_connect=defer_connect,
            init_command=init_command or None,
        )

        if ssh_host:
            ##### paramiko.Channel is a bad socket implementation overall if you want SSL through an SSH tunnel
            #####
            # instead let's open a tunnel and rewrite host:port to local bind
            try:
                chan = sshtunnel.SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    ssh_username=ssh_user,
                    ssh_pkey=ssh_key_filename,
                    ssh_password=ssh_password,
                    remote_bind_address=(host, port),
                )
                chan.start()

                conn.host = chan.local_bind_host
                conn.port = chan.local_bind_port
                conn.connect()
            except Exception as e:
                raise e

        if hasattr(self, "conn"):
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
        self.init_command = init_command
        # retrieve connection id
        self.reset_connection_id()
        self.server_info = ServerInfo.from_version_string(conn.server_version)

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
        if statement.startswith("\\fs"):
            components = [statement]
        else:
            components = special.split_queries(statement)

        for sql in components:
            # \G is treated specially since we have to set the expanded output.
            if sql.endswith("\\G"):
                special.set_expanded_output(True)
                sql = sql[:-2].strip()
            # \g is treated specially since we might want collapsed output when
            # auto vertical output is enabled
            elif sql.endswith('\\g'):
                special.set_expanded_output(False)
                special.set_forced_horizontal_output(True)
                sql = sql[:-2].strip()

            cur = self.conn.cursor()
            try:  # Special command
                _logger.debug("Trying a dbspecial command. sql: %r", sql)
                for result in special.execute(cur, sql):
                    yield result
            except special.CommandNotFound:  # Regular SQL
                _logger.debug("Regular sql statement. sql: %r", sql)
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
            status = "{0} row{1} in set"
        else:
            _logger.debug("No rows in result.")
            status = "Query OK, {0} row{1} affected"
        status = status.format(cursor.rowcount, "" if cursor.rowcount == 1 else "s")

        return (title, cursor if cursor.description else None, headers, status)

    def tables(self):
        """Yields table names"""

        with self.conn.cursor() as cur:
            _logger.debug("Tables Query. sql: %r", self.tables_query)
            cur.execute(self.tables_query)
            for row in cur:
                yield row

    def table_columns(self):
        """Yields (table name, column name) pairs"""
        with self.conn.cursor() as cur:
            _logger.debug("Columns Query. sql: %r", self.table_columns_query)
            cur.execute(self.table_columns_query % self.dbname)
            for row in cur:
                yield row

    def databases(self):
        with self.conn.cursor() as cur:
            _logger.debug("Databases Query. sql: %r", self.databases_query)
            cur.execute(self.databases_query)
            return [x[0] for x in cur.fetchall()]

    def functions(self):
        """Yields tuples of (schema_name, function_name)"""

        with self.conn.cursor() as cur:
            _logger.debug("Functions Query. sql: %r", self.functions_query)
            cur.execute(self.functions_query % self.dbname)
            for row in cur:
                yield row

    def show_candidates(self):
        with self.conn.cursor() as cur:
            _logger.debug("Show Query. sql: %r", self.show_candidates_query)
            try:
                cur.execute(self.show_candidates_query)
            except pymysql.DatabaseError as e:
                _logger.error("No show completions due to %r", e)
                yield ""
            else:
                for row in cur:
                    yield (row[0].split(None, 1)[-1],)

    def users(self):
        with self.conn.cursor() as cur:
            _logger.debug("Users Query. sql: %r", self.users_query)
            try:
                cur.execute(self.users_query)
            except pymysql.DatabaseError as e:
                _logger.error("No user completions due to %r", e)
                yield ""
            else:
                for row in cur:
                    yield row

    def now(self):
        with self.conn.cursor() as cur:
            _logger.debug("Now Query. sql: %r", self.now_query)
            cur.execute(self.now_query)
            return cur.fetchone()[0]

    def get_connection_id(self):
        if not self.connection_id:
            self.reset_connection_id()
        return self.connection_id

    def reset_connection_id(self):
        # Remember current connection id
        _logger.debug("Get current connection id")
        try:
            res = self.run("select connection_id()")
            for title, cur, headers, status in res:
                self.connection_id = cur.fetchone()[0]
        except Exception as e:
            # See #1054
            self.connection_id = -1
            _logger.error("Failed to get connection id: %s", e)
        else:
            _logger.debug("Current connection id: %s", self.connection_id)

    def change_db(self, db):
        self.conn.select_db(db)
        self.dbname = db

    def _create_ssl_ctx(self, sslp):
        import ssl

        ca = sslp.get("ca")
        capath = sslp.get("capath")
        hasnoca = ca is None and capath is None
        ctx = ssl.create_default_context(cafile=ca, capath=capath)
        ctx.check_hostname = not hasnoca and sslp.get("check_hostname", True)
        ctx.verify_mode = ssl.CERT_NONE if hasnoca else ssl.CERT_REQUIRED
        if "cert" in sslp:
            ctx.load_cert_chain(sslp["cert"], keyfile=sslp.get("key"))
        if "cipher" in sslp:
            ctx.set_ciphers(sslp["cipher"])

        # raise this default to v1.1 or v1.2?
        ctx.minimum_version = ssl.TLSVersion.TLSv1

        if "tls_version" in sslp:
            tls_version = sslp["tls_version"]

            if tls_version == "TLSv1":
                ctx.minimum_version = ssl.TLSVersion.TLSv1
                ctx.maximum_version = ssl.TLSVersion.TLSv1
            elif tls_version == "TLSv1.1":
                ctx.minimum_version = ssl.TLSVersion.TLSv1_1
                ctx.maximum_version = ssl.TLSVersion.TLSv1_1
            elif tls_version == "TLSv1.2":
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            elif tls_version == "TLSv1.3":
                ctx.minimum_version = ssl.TLSVersion.TLSv1_3
                ctx.maximum_version = ssl.TLSVersion.TLSv1_3
            else:
                _logger.error("Invalid tls version: %s", tls_version)

        return ctx

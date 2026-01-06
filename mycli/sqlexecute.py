from __future__ import annotations

import datetime
import enum
import logging
import re
import ssl
from typing import Any, Generator, Iterable

import pymysql
from pymysql.connections import Connection
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions, convert_date, convert_datetime, convert_timedelta, decoders
from pymysql.cursors import Cursor

from mycli.packages.special import iocommands
from mycli.packages.special.main import CommandNotFound, execute

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
    def __init__(self, species: ServerSpecies | None, version_str: str) -> None:
        self.species = species
        self.version_str = version_str
        self.version = self.calc_mysql_version_value(version_str)

    @staticmethod
    def calc_mysql_version_value(version_str: str) -> int:
        if not version_str or not isinstance(version_str, str):
            return 0
        try:
            major, minor, patch = version_str.split(".")
        except ValueError:
            return 0
        else:
            return int(major) * 10_000 + int(minor) * 100 + int(patch)

    @classmethod
    def from_version_string(cls, version_string: str) -> ServerInfo:
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

    def __str__(self) -> str:
        if self.species:
            return f"{self.species.value} {self.version_str}"
        else:
            return self.version_str


class SQLExecute:
    databases_query = """SHOW DATABASES"""

    tables_query = """SHOW TABLES"""

    show_candidates_query = '''SELECT name from mysql.help_topic WHERE name like "SHOW %"'''

    users_query = """SELECT CONCAT("'", user, "'@'",host,"'") FROM mysql.user"""

    functions_query = '''SELECT ROUTINE_NAME FROM INFORMATION_SCHEMA.ROUTINES
    WHERE ROUTINE_TYPE="FUNCTION" AND ROUTINE_SCHEMA = "%s"'''

    table_columns_query = """select TABLE_NAME, COLUMN_NAME from information_schema.columns
                                    where table_schema = '%s'
                                    order by table_name,ordinal_position"""

    enum_values_query = """select TABLE_NAME, COLUMN_NAME, COLUMN_TYPE from information_schema.columns
                                    where table_schema = '%s' and data_type = 'enum'
                                    order by table_name,ordinal_position"""

    now_query = """SELECT NOW()"""

    @staticmethod
    def _parse_enum_values(column_type: str) -> list[str]:
        if not column_type or not column_type.lower().startswith("enum("):
            return []

        values: list[str] = []
        current: list[str] = []
        in_quote = False
        i = column_type.find("(") + 1

        while i < len(column_type):
            ch = column_type[i]

            if not in_quote:
                if ch == "'":
                    in_quote = True
                    current = []
                elif ch == ")":
                    break
            else:
                if ch == "\\" and i + 1 < len(column_type):
                    current.append(column_type[i + 1])
                    i += 1
                elif ch == "'":
                    if i + 1 < len(column_type) and column_type[i + 1] == "'":
                        current.append("'")
                        i += 1
                    else:
                        values.append("".join(current))
                        in_quote = False
                else:
                    current.append(ch)
            i += 1

        return values

    def __init__(
        self,
        database: str | None,
        user: str | None,
        password: str | None,
        host: str | None,
        port: int | None,
        socket: str | None,
        charset: str | None,
        local_infile: bool | None,
        ssl: dict[str, Any] | None,
        ssh_user: str | None,
        ssh_host: str | None,
        ssh_port: int | None,
        ssh_password: str | None,
        ssh_key_filename: str | None,
        init_command: str | None = None,
    ) -> None:
        self.dbname = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.socket = socket
        self.charset = charset
        self.local_infile = local_infile
        self.ssl = ssl
        self.server_info: ServerInfo | None = None
        self.connection_id: int | None = None
        self.ssh_user = ssh_user
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_password = ssh_password
        self.ssh_key_filename = ssh_key_filename
        self.init_command = init_command
        self.conn: Connection | None = None
        self.connect()

    def connect(
        self,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        host: str | None = None,
        port: int | None = None,
        socket: str | None = None,
        charset: str | None = None,
        local_infile: bool | None = None,
        ssl: dict[str, Any] | None = None,
        ssh_host: str | None = None,
        ssh_port: int | None = None,
        ssh_user: str | None = None,
        ssh_password: str | None = None,
        ssh_key_filename: str | None = None,
        init_command: str | None = None,
    ):
        db = database if database is not None else self.dbname
        user = user if user is not None else self.user
        password = password if password is not None else self.password
        host = host if host is not None else self.host
        port = port if port is not None else self.port
        socket = socket if socket is not None else self.socket
        charset = charset if charset is not None else self.charset
        local_infile = local_infile if local_infile is not None else self.local_infile
        ssl = ssl if ssl is not None else self.ssl
        ssh_user = ssh_user if ssh_user is not None else self.ssh_user
        ssh_host = ssh_host if ssh_host is not None else self.ssh_host
        ssh_port = ssh_port if ssh_port is not None else self.ssh_port
        ssh_password = ssh_password if ssh_password is not None else self.ssh_password
        ssh_key_filename = ssh_key_filename if ssh_key_filename is not None else self.ssh_key_filename
        init_command = init_command if init_command is not None else self.init_command
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
            FIELD_TYPE.TIMESTAMP: lambda obj: convert_datetime(obj) or obj,
            FIELD_TYPE.DATETIME: lambda obj: convert_datetime(obj) or obj,
            FIELD_TYPE.TIME: lambda obj: convert_timedelta(obj) or obj,
            FIELD_TYPE.DATE: lambda obj: convert_date(obj) or obj,
        })

        defer_connect = False

        if ssh_host:
            defer_connect = True

        client_flag = pymysql.constants.CLIENT.INTERACTIVE
        if init_command and len(list(iocommands.split_queries(init_command))) > 1:
            client_flag |= pymysql.constants.CLIENT.MULTI_STATEMENTS

        ssl_context = None
        if ssl:
            ssl_context = self._create_ssl_ctx(ssl)

        conn = pymysql.connect(
            database=db,
            user=user,
            password=password or '',
            host=host,
            port=port or 0,
            unix_socket=socket,
            use_unicode=True,
            charset=charset or '',
            autocommit=True,
            client_flag=client_flag,
            local_infile=local_infile or False,
            conv=conv,
            ssl=ssl_context,  # type: ignore[arg-type]
            program_name="mycli",
            defer_connect=defer_connect,
            init_command=init_command or None,
        )  # type: ignore[misc]

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

        if self.conn is not None:
            try:
                self.conn.close()
            except pymysql.err.Error:
                pass
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
        self.server_info = ServerInfo.from_version_string(conn.server_version)  # type: ignore[attr-defined]

    def run(self, statement: str) -> Generator[tuple, None, None]:
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
            components: Iterable[str] = [statement]
        else:
            components = iocommands.split_queries(statement)

        for sql in components:
            # \G is treated specially since we have to set the expanded output.
            if sql.endswith("\\G"):
                iocommands.set_expanded_output(True)
                sql = sql[:-2].strip()
            # \g is treated specially since we might want collapsed output when
            # auto vertical output is enabled
            elif sql.endswith('\\g'):
                iocommands.set_expanded_output(False)
                iocommands.set_forced_horizontal_output(True)
                sql = sql[:-2].strip()

            assert isinstance(self.conn, Connection)
            cur = self.conn.cursor()
            try:  # Special command
                _logger.debug("Trying a dbspecial command. sql: %r", sql)
                for result in execute(cur, sql):
                    yield result
            except CommandNotFound:  # Regular SQL
                _logger.debug("Regular sql statement. sql: %r", sql)
                cur.execute(sql)
                while True:
                    yield self.get_result(cur)

                    # PyMySQL returns an extra, empty result set with stored
                    # procedures. We skip it (rowcount is zero and no
                    # description).
                    if not cur.nextset() or (not cur.rowcount and cur.description is None):
                        break

    def get_result(self, cursor: Cursor) -> tuple:
        """Get the current result's data from the cursor."""
        title = headers = None

        # cursor.description is not None for queries that return result sets,
        # e.g. SELECT or SHOW.
        plural = '' if cursor.rowcount == 1 else 's'
        if cursor.description:
            headers = [x[0] for x in cursor.description]
            status = f'{cursor.rowcount} row{plural} in set'
        else:
            _logger.debug("No rows in result.")
            status = f'Query OK, {cursor.rowcount} row{plural} affected'

        if cursor.warning_count > 0:
            plural = '' if cursor.warning_count == 1 else 's'
            status = f'{status}, {cursor.warning_count} warning{plural}'

        return (title, cursor, headers, status)

    def tables(self) -> Generator[tuple[str], None, None]:
        """Yields table names"""

        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Tables Query. sql: %r", self.tables_query)
            cur.execute(self.tables_query)
            for row in cur:
                yield row

    def table_columns(self) -> Generator[tuple[str, str], None, None]:
        """Yields (table name, column name) pairs"""
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Columns Query. sql: %r", self.table_columns_query)
            cur.execute(self.table_columns_query % self.dbname)
            for row in cur:
                yield row

    def enum_values(self) -> Generator[tuple[str, str, list[str]], None, None]:
        """Yields (table name, column name, enum values) tuples"""
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Enum Values Query. sql: %r", self.enum_values_query)
            cur.execute(self.enum_values_query % self.dbname)
            for table_name, column_name, column_type in cur:
                values = self._parse_enum_values(column_type)
                if values:
                    yield (table_name, column_name, values)

    def databases(self) -> list[str]:
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Databases Query. sql: %r", self.databases_query)
            cur.execute(self.databases_query)
            return [x[0] for x in cur.fetchall()]

    def functions(self) -> Generator[tuple[str, str], None, None]:
        """Yields tuples of (schema_name, function_name)"""

        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Functions Query. sql: %r", self.functions_query)
            cur.execute(self.functions_query % self.dbname)
            for row in cur:
                yield row

    def show_candidates(self) -> Generator[tuple, None, None]:
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Show Query. sql: %r", self.show_candidates_query)
            try:
                cur.execute(self.show_candidates_query)
            except pymysql.DatabaseError as e:
                _logger.error("No show completions due to %r", e)
                yield ()
            else:
                for row in cur:
                    yield (row[0].split(None, 1)[-1],)

    def users(self) -> Generator[tuple, None, None]:
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Users Query. sql: %r", self.users_query)
            try:
                cur.execute(self.users_query)
            except pymysql.DatabaseError as e:
                _logger.error("No user completions due to %r", e)
                yield ()
            else:
                for row in cur:
                    yield row

    def now(self) -> datetime.datetime:
        assert isinstance(self.conn, Connection)
        with self.conn.cursor() as cur:
            _logger.debug("Now Query. sql: %r", self.now_query)
            cur.execute(self.now_query)
            if one := cur.fetchone():
                return one[0]
            else:
                return datetime.datetime.now()

    def get_connection_id(self) -> int | None:
        if not self.connection_id:
            self.reset_connection_id()
        return self.connection_id

    def reset_connection_id(self) -> None:
        # Remember current connection id
        _logger.debug("Get current connection id")
        try:
            res = self.run("select connection_id()")
            for _title, cur, _headers, _status in res:
                self.connection_id = cur.fetchone()[0]
        except Exception as e:
            # See #1054
            self.connection_id = -1
            _logger.error("Failed to get connection id: %s", e)
        else:
            _logger.debug("Current connection id: %s", self.connection_id)

    def change_db(self, db: str) -> None:
        assert isinstance(self.conn, Connection)
        self.conn.select_db(db)
        self.dbname = db

    def _create_ssl_ctx(self, sslp: dict) -> ssl.SSLContext:
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

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except pymysql.err.Error:
                pass

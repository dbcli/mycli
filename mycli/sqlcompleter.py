from collections import Counter
import logging
import re

from prompt_toolkit.completion import Completer, Completion

from mycli.packages.completion_engine import suggest_type
from mycli.packages.filepaths import complete_path, parse_path, suggest_path
from mycli.packages.parseutils import last_word
from mycli.packages.special.favoritequeries import FavoriteQueries

_logger = logging.getLogger(__name__)


class SQLCompleter(Completer):
    keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "UPDATE",
        "DELETE FROM",
        "GROUP BY",
        "JOIN",
        "INSERT INTO",
        "LIKE",
        "LIMIT",
        "ACCESS",
        "ADD",
        "ALL",
        "ALTER TABLE",
        "AND",
        "ANY",
        "AS",
        "ASC",
        "AUTO_INCREMENT",
        "BEFORE",
        "BEGIN",
        "BETWEEN",
        "BIGINT",
        "BINARY",
        "BY",
        "CASE",
        "CHANGE MASTER TO",
        "CHAR",
        "CHARACTER SET",
        "CHECK",
        "COLLATE",
        "COLUMN",
        "COMMENT",
        "COMMIT",
        "CONSTRAINT",
        "CREATE",
        "CURRENT",
        "CURRENT_TIMESTAMP",
        "DATABASE",
        "DATE",
        "DECIMAL",
        "DEFAULT",
        "DESC",
        "DESCRIBE",
        "DROP",
        "ELSE",
        "END",
        "ENGINE",
        "ESCAPE",
        "EXISTS",
        "FILE",
        "FLOAT",
        "FOR",
        "FOREIGN KEY",
        "FORMAT",
        "FULL",
        "FUNCTION",
        "GRANT",
        "HAVING",
        "HOST",
        "IDENTIFIED",
        "IN",
        "INCREMENT",
        "INDEX",
        "INT",
        "INTEGER",
        "INTERVAL",
        "INTO",
        "IS",
        "KEY",
        "LEFT",
        "LEVEL",
        "LOCK",
        "LOGS",
        "LONG",
        "MASTER",
        "MEDIUMINT",
        "MODE",
        "MODIFY",
        "NOT",
        "NULL",
        "NUMBER",
        "OFFSET",
        "ON",
        "OPTION",
        "OR",
        "ORDER BY",
        "OUTER",
        "OWNER",
        "PASSWORD",
        "PORT",
        "PRIMARY",
        "PRIVILEGES",
        "PROCESSLIST",
        "PURGE",
        "REFERENCES",
        "REGEXP",
        "RENAME",
        "REPAIR",
        "RESET",
        "REVOKE",
        "RIGHT",
        "ROLLBACK",
        "ROW",
        "ROWS",
        "ROW_FORMAT",
        "SAVEPOINT",
        "SESSION",
        "SET",
        "SHARE",
        "SHOW",
        "SLAVE",
        "SMALLINT",
        "START",
        "STOP",
        "TABLE",
        "THEN",
        "TINYINT",
        "TO",
        "TRANSACTION",
        "TRIGGER",
        "TRUNCATE",
        "UNION",
        "UNIQUE",
        "UNSIGNED",
        "USE",
        "USER",
        "USING",
        "VALUES",
        "VARCHAR",
        "VIEW",
        "WHEN",
        "WITH",
    ]

    tidb_keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "DELETE FROM",
        "UPDATE",
        "GROUP BY",
        "JOIN",
        "INSERT INTO",
        "LIKE",
        "LIMIT",
        "ACCOUNT",
        "ACTION",
        "ADD",
        "ADDDATE",
        "ADMIN",
        "ADVISE",
        "AFTER",
        "AGAINST",
        "AGO",
        "ALGORITHM",
        "ALL",
        "ALTER",
        "ALWAYS",
        "ANALYZE",
        "AND",
        "ANY",
        "APPROX_COUNT_DISTINCT",
        "APPROX_PERCENTILE",
        "AS",
        "ASC",
        "ASCII",
        "ATTRIBUTES",
        "AUTO_ID_CACHE",
        "AUTO_INCREMENT",
        "AUTO_RANDOM",
        "AUTO_RANDOM_BASE",
        "AVG",
        "AVG_ROW_LENGTH",
        "BACKEND",
        "BACKUP",
        "BACKUPS",
        "BATCH",
        "BEGIN",
        "BERNOULLI",
        "BETWEEN",
        "BIGINT",
        "BINARY",
        "BINDING",
        "BINDINGS",
        "BINDING_CACHE",
        "BINLOG",
        "BIT",
        "BIT_AND",
        "BIT_OR",
        "BIT_XOR",
        "BLOB",
        "BLOCK",
        "BOOL",
        "BOOLEAN",
        "BOTH",
        "BOUND",
        "BRIEF",
        "BTREE",
        "BUCKETS",
        "BUILTINS",
        "BY",
        "BYTE",
        "CACHE",
        "CALL",
        "CANCEL",
        "CAPTURE",
        "CARDINALITY",
        "CASCADE",
        "CASCADED",
        "CASE",
        "CAST",
        "CAUSAL",
        "CHAIN",
        "CHANGE",
        "CHAR",
        "CHARACTER",
        "CHARSET",
        "CHECK",
        "CHECKPOINT",
        "CHECKSUM",
        "CIPHER",
        "CLEANUP",
        "CLIENT",
        "CLIENT_ERRORS_SUMMARY",
        "CLUSTERED",
        "CMSKETCH",
        "COALESCE",
        "COLLATE",
        "COLLATION",
        "COLUMN",
        "COLUMNS",
        "COLUMN_FORMAT",
        "COLUMN_STATS_USAGE",
        "COMMENT",
        "COMMIT",
        "COMMITTED",
        "COMPACT",
        "COMPRESSED",
        "COMPRESSION",
        "CONCURRENCY",
        "CONFIG",
        "CONNECTION",
        "CONSISTENCY",
        "CONSISTENT",
        "CONSTRAINT",
        "CONSTRAINTS",
        "CONTEXT",
        "CONVERT",
        "COPY",
        "CORRELATION",
        "CPU",
        "CREATE",
        "CROSS",
        "CSV_BACKSLASH_ESCAPE",
        "CSV_DELIMITER",
        "CSV_HEADER",
        "CSV_NOT_NULL",
        "CSV_NULL",
        "CSV_SEPARATOR",
        "CSV_TRIM_LAST_SEPARATORS",
        "CUME_DIST",
        "CURRENT",
        "CURRENT_DATE",
        "CURRENT_ROLE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "CURTIME",
        "CYCLE",
        "DATA",
        "DATABASE",
        "DATABASES",
        "DATE",
        "DATETIME",
        "DATE_ADD",
        "DATE_SUB",
        "DAY",
        "DAY_HOUR",
        "DAY_MICROSECOND",
        "DAY_MINUTE",
        "DAY_SECOND",
        "DDL",
        "DEALLOCATE",
        "DECIMAL",
        "DEFAULT",
        "DEFINER",
        "DELAYED",
        "DELAY_KEY_WRITE",
        "DENSE_RANK",
        "DEPENDENCY",
        "DEPTH",
        "DESC",
        "DESCRIBE",
        "DIRECTORY",
        "DISABLE",
        "DISABLED",
        "DISCARD",
        "DISK",
        "DISTINCT",
        "DISTINCTROW",
        "DIV",
        "DO",
        "DOT",
        "DOUBLE",
        "DRAINER",
        "DROP",
        "DRY",
        "DUAL",
        "DUMP",
        "DUPLICATE",
        "DYNAMIC",
        "ELSE",
        "ENABLE",
        "ENABLED",
        "ENCLOSED",
        "ENCRYPTION",
        "END",
        "ENFORCED",
        "ENGINE",
        "ENGINES",
        "ENUM",
        "ERROR",
        "ERRORS",
        "ESCAPE",
        "ESCAPED",
        "EVENT",
        "EVENTS",
        "EVOLVE",
        "EXACT",
        "EXCEPT",
        "EXCHANGE",
        "EXCLUSIVE",
        "EXECUTE",
        "EXISTS",
        "EXPANSION",
        "EXPIRE",
        "EXPLAIN",
        "EXPR_PUSHDOWN_BLACKLIST",
        "EXTENDED",
        "EXTRACT",
        "FALSE",
        "FAST",
        "FAULTS",
        "FETCH",
        "FIELDS",
        "FILE",
        "FIRST",
        "FIRST_VALUE",
        "FIXED",
        "FLASHBACK",
        "FLOAT",
        "FLUSH",
        "FOLLOWER",
        "FOLLOWERS",
        "FOLLOWER_CONSTRAINTS",
        "FOLLOWING",
        "FOR",
        "FORCE",
        "FOREIGN",
        "FORMAT",
        "FULL",
        "FULLTEXT",
        "FUNCTION",
        "GENERAL",
        "GENERATED",
        "GET_FORMAT",
        "GLOBAL",
        "GRANT",
        "GRANTS",
        "GROUPS",
        "GROUP_CONCAT",
        "HASH",
        "HAVING",
        "HELP",
        "HIGH_PRIORITY",
        "HISTOGRAM",
        "HISTOGRAMS_IN_FLIGHT",
        "HISTORY",
        "HOSTS",
        "HOUR",
        "HOUR_MICROSECOND",
        "HOUR_MINUTE",
        "HOUR_SECOND",
        "IDENTIFIED",
        "IF",
        "IGNORE",
        "IMPORT",
        "IMPORTS",
        "IN",
        "INCREMENT",
        "INCREMENTAL",
        "INDEX",
        "INDEXES",
        "INFILE",
        "INNER",
        "INPLACE",
        "INSERT_METHOD",
        "INSTANCE",
        "INSTANT",
        "INT",
        "INT1",
        "INT2",
        "INT3",
        "INT4",
        "INT8",
        "INTEGER",
        "INTERNAL",
        "INTERSECT",
        "INTERVAL",
        "INTO",
        "INVISIBLE",
        "INVOKER",
        "IO",
        "IPC",
        "IS",
        "ISOLATION",
        "ISSUER",
        "JOB",
        "JOBS",
        "JSON",
        "JSON_ARRAYAGG",
        "JSON_OBJECTAGG",
        "KEY",
        "KEYS",
        "KEY_BLOCK_SIZE",
        "KILL",
        "LABELS",
        "LAG",
        "LANGUAGE",
        "LAST",
        "LASTVAL",
        "LAST_BACKUP",
        "LAST_VALUE",
        "LEAD",
        "LEADER",
        "LEADER_CONSTRAINTS",
        "LEADING",
        "LEARNER",
        "LEARNERS",
        "LEARNER_CONSTRAINTS",
        "LEFT",
        "LESS",
        "LEVEL",
        "LINEAR",
        "LINES",
        "LIST",
        "LOAD",
        "LOCAL",
        "LOCALTIME",
        "LOCALTIMESTAMP",
        "LOCATION",
        "LOCK",
        "LOCKED",
        "LOGS",
        "LONG",
        "LONGBLOB",
        "LONGTEXT",
        "LOW_PRIORITY",
        "MASTER",
        "MATCH",
        "MAX",
        "MAXVALUE",
        "MAX_CONNECTIONS_PER_HOUR",
        "MAX_IDXNUM",
        "MAX_MINUTES",
        "MAX_QUERIES_PER_HOUR",
        "MAX_ROWS",
        "MAX_UPDATES_PER_HOUR",
        "MAX_USER_CONNECTIONS",
        "MB",
        "MEDIUMBLOB",
        "MEDIUMINT",
        "MEDIUMTEXT",
        "MEMORY",
        "MERGE",
        "MICROSECOND",
        "MIN",
        "MINUTE",
        "MINUTE_MICROSECOND",
        "MINUTE_SECOND",
        "MINVALUE",
        "MIN_ROWS",
        "MOD",
        "MODE",
        "MODIFY",
        "MONTH",
        "NAMES",
        "NATIONAL",
        "NATURAL",
        "NCHAR",
        "NEVER",
        "NEXT",
        "NEXTVAL",
        "NEXT_ROW_ID",
        "NO",
        "NOCACHE",
        "NOCYCLE",
        "NODEGROUP",
        "NODE_ID",
        "NODE_STATE",
        "NOMAXVALUE",
        "NOMINVALUE",
        "NONCLUSTERED",
        "NONE",
        "NORMAL",
        "NOT",
        "NOW",
        "NOWAIT",
        "NO_WRITE_TO_BINLOG",
        "NTH_VALUE",
        "NTILE",
        "NULL",
        "NULLS",
        "NUMERIC",
        "NVARCHAR",
        "OF",
        "OFF",
        "OFFSET",
        "ON",
        "ONLINE",
        "ONLY",
        "ON_DUPLICATE",
        "OPEN",
        "OPTIMISTIC",
        "OPTIMIZE",
        "OPTION",
        "OPTIONAL",
        "OPTIONALLY",
        "OPT_RULE_BLACKLIST",
        "OR",
        "ORDER",
        "OUTER",
        "OUTFILE",
        "OVER",
        "PACK_KEYS",
        "PAGE",
        "PARSER",
        "PARTIAL",
        "PARTITION",
        "PARTITIONING",
        "PARTITIONS",
        "PASSWORD",
        "PERCENT",
        "PERCENT_RANK",
        "PER_DB",
        "PER_TABLE",
        "PESSIMISTIC",
        "PLACEMENT",
        "PLAN",
        "PLAN_CACHE",
        "PLUGINS",
        "POLICY",
        "POSITION",
        "PRECEDING",
        "PRECISION",
        "PREDICATE",
        "PREPARE",
        "PRESERVE",
        "PRE_SPLIT_REGIONS",
        "PRIMARY",
        "PRIMARY_REGION",
        "PRIVILEGES",
        "PROCEDURE",
        "PROCESS",
        "PROCESSLIST",
        "PROFILE",
        "PROFILES",
        "PROXY",
        "PUMP",
        "PURGE",
        "QUARTER",
        "QUERIES",
        "QUERY",
        "QUICK",
        "RANGE",
        "RANK",
        "RATE_LIMIT",
        "READ",
        "REAL",
        "REBUILD",
        "RECENT",
        "RECOVER",
        "RECURSIVE",
        "REDUNDANT",
        "REFERENCES",
        "REGEXP",
        "REGION",
        "REGIONS",
        "RELEASE",
        "RELOAD",
        "REMOVE",
        "RENAME",
        "REORGANIZE",
        "REPAIR",
        "REPEAT",
        "REPEATABLE",
        "REPLACE",
        "REPLAYER",
        "REPLICA",
        "REPLICAS",
        "REPLICATION",
        "REQUIRE",
        "REQUIRED",
        "RESET",
        "RESPECT",
        "RESTART",
        "RESTORE",
        "RESTORES",
        "RESTRICT",
        "RESUME",
        "REVERSE",
        "REVOKE",
        "RIGHT",
        "RLIKE",
        "ROLE",
        "ROLLBACK",
        "ROUTINE",
        "ROW",
        "ROWS",
        "ROW_COUNT",
        "ROW_FORMAT",
        "ROW_NUMBER",
        "RTREE",
        "RUN",
        "RUNNING",
        "S3",
        "SAMPLERATE",
        "SAMPLES",
        "SAN",
        "SAVEPOINT",
        "SCHEDULE",
        "SECOND",
        "SECONDARY_ENGINE",
        "SECONDARY_LOAD",
        "SECONDARY_UNLOAD",
        "SECOND_MICROSECOND",
        "SECURITY",
        "SEND_CREDENTIALS_TO_TIKV",
        "SEPARATOR",
        "SEQUENCE",
        "SERIAL",
        "SERIALIZABLE",
        "SESSION",
        "SESSION_STATES",
        "SET",
        "SETVAL",
        "SHARD_ROW_ID_BITS",
        "SHARE",
        "SHARED",
        "SHOW",
        "SHUTDOWN",
        "SIGNED",
        "SIMPLE",
        "SKIP",
        "SKIP_SCHEMA_FILES",
        "SLAVE",
        "SLOW",
        "SMALLINT",
        "SNAPSHOT",
        "SOME",
        "SOURCE",
        "SPATIAL",
        "SPLIT",
        "SQL",
        "SQL_BIG_RESULT",
        "SQL_BUFFER_RESULT",
        "SQL_CACHE",
        "SQL_CALC_FOUND_ROWS",
        "SQL_NO_CACHE",
        "SQL_SMALL_RESULT",
        "SQL_TSI_DAY",
        "SQL_TSI_HOUR",
        "SQL_TSI_MINUTE",
        "SQL_TSI_MONTH",
        "SQL_TSI_QUARTER",
        "SQL_TSI_SECOND",
        "SQL_TSI_WEEK",
        "SQL_TSI_YEAR",
        "SSL",
        "STALENESS",
        "START",
        "STARTING",
        "STATISTICS",
        "STATS",
        "STATS_AUTO_RECALC",
        "STATS_BUCKETS",
        "STATS_COL_CHOICE",
        "STATS_COL_LIST",
        "STATS_EXTENDED",
        "STATS_HEALTHY",
        "STATS_HISTOGRAMS",
        "STATS_META",
        "STATS_OPTIONS",
        "STATS_PERSISTENT",
        "STATS_SAMPLE_PAGES",
        "STATS_SAMPLE_RATE",
        "STATS_TOPN",
        "STATUS",
        "STD",
        "STDDEV",
        "STDDEV_POP",
        "STDDEV_SAMP",
        "STOP",
        "STORAGE",
        "STORED",
        "STRAIGHT_JOIN",
        "STRICT",
        "STRICT_FORMAT",
        "STRONG",
        "SUBDATE",
        "SUBJECT",
        "SUBPARTITION",
        "SUBPARTITIONS",
        "SUBSTRING",
        "SUM",
        "SUPER",
        "SWAPS",
        "SWITCHES",
        "SYSTEM",
        "SYSTEM_TIME",
        "TABLE",
        "TABLES",
        "TABLESAMPLE",
        "TABLESPACE",
        "TABLE_CHECKSUM",
        "TARGET",
        "TELEMETRY",
        "TELEMETRY_ID",
        "TEMPORARY",
        "TEMPTABLE",
        "TERMINATED",
        "TEXT",
        "THAN",
        "THEN",
        "TIDB",
        "TIFLASH",
        "TIKV_IMPORTER",
        "TIME",
        "TIMESTAMP",
        "TIMESTAMPADD",
        "TIMESTAMPDIFF",
        "TINYBLOB",
        "TINYINT",
        "TINYTEXT",
        "TLS",
        "TO",
        "TOKUDB_DEFAULT",
        "TOKUDB_FAST",
        "TOKUDB_LZMA",
        "TOKUDB_QUICKLZ",
        "TOKUDB_SMALL",
        "TOKUDB_SNAPPY",
        "TOKUDB_UNCOMPRESSED",
        "TOKUDB_ZLIB",
        "TOP",
        "TOPN",
        "TRACE",
        "TRADITIONAL",
        "TRAILING",
        "TRANSACTION",
        "TRIGGER",
        "TRIGGERS",
        "TRIM",
        "TRUE",
        "TRUE_CARD_COST",
        "TRUNCATE",
        "TYPE",
        "UNBOUNDED",
        "UNCOMMITTED",
        "UNDEFINED",
        "UNICODE",
        "UNION",
        "UNIQUE",
        "UNKNOWN",
        "UNLOCK",
        "UNSIGNED",
        "USAGE",
        "USE",
        "USER",
        "USING",
        "UTC_DATE",
        "UTC_TIME",
        "UTC_TIMESTAMP",
        "VALIDATION",
        "VALUE",
        "VALUES",
        "VARBINARY",
        "VARCHAR",
        "VARCHARACTER",
        "VARIABLES",
        "VARIANCE",
        "VARYING",
        "VAR_POP",
        "VAR_SAMP",
        "VERBOSE",
        "VIEW",
        "VIRTUAL",
        "VISIBLE",
        "VOTER",
        "VOTERS",
        "VOTER_CONSTRAINTS",
        "WAIT",
        "WARNINGS",
        "WEEK",
        "WEIGHT_STRING",
        "WHEN",
        "WIDTH",
        "WINDOW",
        "WITH",
        "WITHOUT",
        "WRITE",
        "X509",
        "XOR",
        "YEAR",
        "YEAR_MONTH",
        "ZEROFILL",
    ]

    functions = [
        "AVG",
        "CONCAT",
        "COUNT",
        "DISTINCT",
        "FIRST",
        "FORMAT",
        "FROM_UNIXTIME",
        "LAST",
        "LCASE",
        "LEN",
        "MAX",
        "MID",
        "MIN",
        "NOW",
        "ROUND",
        "SUM",
        "TOP",
        "UCASE",
        "UNIX_TIMESTAMP",
    ]

    # https://docs.pingcap.com/tidb/dev/tidb-functions
    tidb_functions = [
        "TIDB_BOUNDED_STALENESS",
        "TIDB_DECODE_KEY",
        "TIDB_DECODE_PLAN",
        "TIDB_IS_DDL_OWNER",
        "TIDB_PARSE_TSO",
        "TIDB_VERSION",
        "TIDB_DECODE_SQL_DIGESTS",
        "VITESS_HASH",
        "TIDB_SHARD",
    ]

    show_items = []

    change_items = [
        "MASTER_BIND",
        "MASTER_HOST",
        "MASTER_USER",
        "MASTER_PASSWORD",
        "MASTER_PORT",
        "MASTER_CONNECT_RETRY",
        "MASTER_HEARTBEAT_PERIOD",
        "MASTER_LOG_FILE",
        "MASTER_LOG_POS",
        "RELAY_LOG_FILE",
        "RELAY_LOG_POS",
        "MASTER_SSL",
        "MASTER_SSL_CA",
        "MASTER_SSL_CAPATH",
        "MASTER_SSL_CERT",
        "MASTER_SSL_KEY",
        "MASTER_SSL_CIPHER",
        "MASTER_SSL_VERIFY_SERVER_CERT",
        "IGNORE_SERVER_IDS",
    ]

    users = []

    def __init__(self, smart_completion=True, supported_formats=(), keyword_casing="auto"):
        super(self.__class__, self).__init__()
        self.smart_completion = smart_completion
        self.reserved_words = set()
        for x in self.keywords:
            self.reserved_words.update(x.split())
        self.name_pattern = re.compile(r"^[_a-z][_a-z0-9\$]*$")

        self.special_commands = []
        self.table_formats = supported_formats
        if keyword_casing not in ("upper", "lower", "auto"):
            keyword_casing = "auto"
        self.keyword_casing = keyword_casing
        self.reset_completions()

    def escape_name(self, name):
        if name and ((not self.name_pattern.match(name)) or (name.upper() in self.reserved_words) or (name.upper() in self.functions)):
            name = "`%s`" % name

        return name

    def unescape_name(self, name):
        """Unquote a string."""
        if name and name[0] == '"' and name[-1] == '"':
            name = name[1:-1]

        return name

    def escaped_names(self, names):
        return [self.escape_name(name) for name in names]

    def extend_special_commands(self, special_commands):
        # Special commands are not part of all_completions since they can only
        # be at the beginning of a line.
        self.special_commands.extend(special_commands)

    def extend_database_names(self, databases):
        self.databases.extend(databases)

    def extend_keywords(self, keywords, replace=False):
        if replace:
            self.keywords = keywords
        else:
            self.keywords.extend(keywords)
        self.all_completions.update(keywords)

    def extend_show_items(self, show_items):
        for show_item in show_items:
            self.show_items.extend(show_item)
            self.all_completions.update(show_item)

    def extend_change_items(self, change_items):
        for change_item in change_items:
            self.change_items.extend(change_item)
            self.all_completions.update(change_item)

    def extend_users(self, users):
        for user in users:
            self.users.extend(user)
            self.all_completions.update(user)

    def extend_schemata(self, schema):
        if schema is None:
            return
        metadata = self.dbmetadata["tables"]
        metadata[schema] = {}

        # dbmetadata.values() are the 'tables' and 'functions' dicts
        for metadata in self.dbmetadata.values():
            metadata[schema] = {}
        self.all_completions.update(schema)

    def extend_relations(self, data, kind):
        """Extend metadata for tables or views

        :param data: list of (rel_name, ) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """
        # 'data' is a generator object. It can throw an exception while being
        # consumed. This could happen if the user has launched the app without
        # specifying a database name. This exception must be handled to prevent
        # crashing.
        try:
            data = [self.escaped_names(d) for d in data]
        except Exception:
            data = []

        # dbmetadata['tables'][$schema_name][$table_name] should be a list of
        # column names. Default to an asterisk
        metadata = self.dbmetadata[kind]
        for relname in data:
            try:
                metadata[self.dbname][relname[0]] = ["*"]
            except KeyError:
                _logger.error("%r %r listed in unrecognized schema %r", kind, relname[0], self.dbname)
            self.all_completions.add(relname[0])

    def extend_columns(self, column_data, kind):
        """Extend column metadata

        :param column_data: list of (rel_name, column_name) tuples
        :param kind: either 'tables' or 'views'
        :return:
        """
        # 'column_data' is a generator object. It can throw an exception while
        # being consumed. This could happen if the user has launched the app
        # without specifying a database name. This exception must be handled to
        # prevent crashing.
        try:
            column_data = [self.escaped_names(d) for d in column_data]
        except Exception:
            column_data = []

        metadata = self.dbmetadata[kind]
        for relname, column in column_data:
            if relname not in metadata[self.dbname]:
                _logger.error("relname '%s' was not found in db '%s'", relname, self.dbname)
                # this could happen back when the completer populated via two calls:
                # SHOW TABLES then SELECT table_name, column_name from information_schema.columns
                # it's a slight race, but much more likely on Vitess picking random shards for each.
                # see discussion in https://github.com/dbcli/mycli/pull/1182 (tl;dr - let's keep it)
                continue
            metadata[self.dbname][relname].append(column)
            self.all_completions.add(column)

    def extend_functions(self, func_data, builtin=False):
        # if 'builtin' is set this is extending the list of builtin functions
        if builtin:
            self.functions.extend(func_data)
            return

        # 'func_data' is a generator object. It can throw an exception while
        # being consumed. This could happen if the user has launched the app
        # without specifying a database name. This exception must be handled to
        # prevent crashing.
        try:
            func_data = [self.escaped_names(d) for d in func_data]
        except Exception:
            func_data = []

        # dbmetadata['functions'][$schema_name][$function_name] should return
        # function metadata.
        metadata = self.dbmetadata["functions"]

        for func in func_data:
            metadata[self.dbname][func[0]] = None
            self.all_completions.add(func[0])

    def set_dbname(self, dbname):
        self.dbname = dbname

    def reset_completions(self):
        self.databases = []
        self.users = []
        self.show_items = []
        self.dbname = ""
        self.dbmetadata = {"tables": {}, "views": {}, "functions": {}}
        self.all_completions = set(self.keywords + self.functions)

    @staticmethod
    def find_matches(text, collection, start_only=False, fuzzy=True, casing=None):
        """Find completion matches for the given text.

        Given the user's input text and a collection of available
        completions, find completions matching the last word of the
        text.

        If `start_only` is True, the text will match an available
        completion only at the beginning. Otherwise, a completion is
        considered a match if the text appears anywhere within it.

        yields prompt_toolkit Completion instances for any matches found
        in the collection of available completions.
        """
        last = last_word(text, include="most_punctuations")
        text = last.lower()

        completions = []

        if fuzzy:
            regex = ".*?".join(map(re.escape, text))
            pat = re.compile("(%s)" % regex)
            for item in collection:
                r = pat.search(item.lower())
                if r:
                    completions.append((len(r.group()), r.start(), item))
        else:
            match_end_limit = len(text) if start_only else None
            for item in collection:
                match_point = item.lower().find(text, 0, match_end_limit)
                if match_point >= 0:
                    completions.append((len(text), match_point, item))

        if casing == "auto":
            casing = "lower" if last and last[-1].islower() else "upper"

        def apply_case(kw):
            if casing == "upper":
                return kw.upper()
            return kw.lower()

        return (Completion(z if casing is None else apply_case(z), -len(text)) for x, y, z in completions)

    def get_completions(self, document, complete_event, smart_completion=None):
        word_before_cursor = document.get_word_before_cursor(WORD=True)
        if smart_completion is None:
            smart_completion = self.smart_completion

        # If smart_completion is off then match any word that starts with
        # 'word_before_cursor'.
        if not smart_completion:
            return self.find_matches(word_before_cursor, self.all_completions, start_only=True, fuzzy=False)

        completions = []
        suggestions = suggest_type(document.text, document.text_before_cursor)

        for suggestion in suggestions:
            _logger.debug("Suggestion type: %r", suggestion["type"])

            if suggestion["type"] == "column":
                tables = suggestion["tables"]
                _logger.debug("Completion column scope: %r", tables)
                scoped_cols = self.populate_scoped_cols(tables)
                if suggestion.get("drop_unique"):
                    # drop_unique is used for 'tb11 JOIN tbl2 USING (...'
                    # which should suggest only columns that appear in more than
                    # one table
                    scoped_cols = [col for (col, count) in Counter(scoped_cols).items() if count > 1 and col != "*"]

                cols = self.find_matches(word_before_cursor, scoped_cols)
                completions.extend(cols)

            elif suggestion["type"] == "function":
                # suggest user-defined functions using substring matching
                funcs = self.populate_schema_objects(suggestion["schema"], "functions")
                user_funcs = self.find_matches(word_before_cursor, funcs)
                completions.extend(user_funcs)

                # suggest hardcoded functions using startswith matching only if
                # there is no schema qualifier. If a schema qualifier is
                # present it probably denotes a table.
                # eg: SELECT * FROM users u WHERE u.
                if not suggestion["schema"]:
                    predefined_funcs = self.find_matches(
                        word_before_cursor, self.functions, start_only=True, fuzzy=False, casing=self.keyword_casing
                    )
                    completions.extend(predefined_funcs)

            elif suggestion["type"] == "table":
                tables = self.populate_schema_objects(suggestion["schema"], "tables")
                tables = self.find_matches(word_before_cursor, tables)
                completions.extend(tables)

            elif suggestion["type"] == "view":
                views = self.populate_schema_objects(suggestion["schema"], "views")
                views = self.find_matches(word_before_cursor, views)
                completions.extend(views)

            elif suggestion["type"] == "alias":
                aliases = suggestion["aliases"]
                aliases = self.find_matches(word_before_cursor, aliases)
                completions.extend(aliases)

            elif suggestion["type"] == "database":
                dbs = self.find_matches(word_before_cursor, self.databases)
                completions.extend(dbs)

            elif suggestion["type"] == "keyword":
                keywords = self.find_matches(word_before_cursor, self.keywords, casing=self.keyword_casing)
                completions.extend(keywords)

            elif suggestion["type"] == "show":
                show_items = self.find_matches(
                    word_before_cursor, self.show_items, start_only=False, fuzzy=True, casing=self.keyword_casing
                )
                completions.extend(show_items)

            elif suggestion["type"] == "change":
                change_items = self.find_matches(word_before_cursor, self.change_items, start_only=False, fuzzy=True)
                completions.extend(change_items)
            elif suggestion["type"] == "user":
                users = self.find_matches(word_before_cursor, self.users, start_only=False, fuzzy=True)
                completions.extend(users)

            elif suggestion["type"] == "special":
                special = self.find_matches(word_before_cursor, self.special_commands, start_only=True, fuzzy=False)
                completions.extend(special)
            elif suggestion["type"] == "favoritequery":
                queries = self.find_matches(word_before_cursor, FavoriteQueries.instance.list(), start_only=False, fuzzy=True)
                completions.extend(queries)
            elif suggestion["type"] == "table_format":
                formats = self.find_matches(word_before_cursor, self.table_formats)

                completions.extend(formats)
            elif suggestion["type"] == "file_name":
                file_names = self.find_files(word_before_cursor)
                completions.extend(file_names)

        return completions

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

    def populate_scoped_cols(self, scoped_tbls):
        """Find all columns in a set of scoped_tables
        :param scoped_tbls: list of (schema, table, alias) tuples
        :return: list of column names
        """
        columns = []
        meta = self.dbmetadata

        for tbl in scoped_tbls:
            # A fully qualified schema.relname reference or default_schema
            # DO NOT escape schema names.
            schema = tbl[0] or self.dbname
            relname = tbl[1]
            escaped_relname = self.escape_name(tbl[1])

            # We don't know if schema.relname is a table or view. Since
            # tables and views cannot share the same name, we can check one
            # at a time
            try:
                columns.extend(meta["tables"][schema][relname])

                # Table exists, so don't bother checking for a view
                continue
            except KeyError:
                try:
                    columns.extend(meta["tables"][schema][escaped_relname])
                    # Table exists, so don't bother checking for a view
                    continue
                except KeyError:
                    pass

            try:
                columns.extend(meta["views"][schema][relname])
            except KeyError:
                pass

        return columns

    def populate_schema_objects(self, schema, obj_type):
        """Returns list of tables or functions for a (optional) schema"""
        metadata = self.dbmetadata[obj_type]
        schema = schema or self.dbname

        try:
            objects = metadata[schema].keys()
        except KeyError:
            # schema doesn't exist
            objects = []

        return objects

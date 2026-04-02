# type: ignore

from unittest.mock import MagicMock

from pymysql import ProgrammingError

from mycli.packages.completion_engine import suggest_type
from mycli.packages.special import dbcommands
from mycli.packages.special.dbcommands import list_databases, list_tables, status
from test.pytests.test_completion_engine import sorted_dicts


class FakeConnection:
    def __init__(
        self,
        *,
        host: str = 'db.example',
        port: int = 3306,
        host_info: str = 'Localhost via UNIX socket',
        unix_socket: str | None = None,
        thread_id_value: int = 42,
    ) -> None:
        self.host = host
        self.port = port
        self.host_info = host_info
        self.unix_socket = unix_socket
        self._thread_id_value = thread_id_value

    def thread_id(self) -> int:
        return self._thread_id_value


class FakeCursor:
    def __init__(
        self,
        *,
        query_results: dict[str, dict[str, object]],
        connection: FakeConnection | None = None,
        fail_on_queries: set[str] | None = None,
    ) -> None:
        self.query_results = query_results
        self.connection = connection or FakeConnection()
        self.fail_on_queries = fail_on_queries or set()
        self.description = None
        self.current_query = None
        self.executed: list[str] = []

    def execute(self, query: str) -> None:
        self.executed.append(query)
        self.current_query = query
        if query in self.fail_on_queries:
            raise ProgrammingError()
        self.description = self.query_results.get(query, {}).get('description')

    def fetchall(self):
        return self.query_results.get(self.current_query, {}).get('rows', [])

    def fetchone(self):
        rows = self.query_results.get(self.current_query, {}).get('rows', [])
        return rows[0] if rows else None


def test_list_tables_verbose_preserves_field_results():
    """Test that \\dt+ table_name returns SHOW FIELDS results, not SHOW CREATE TABLE results.

    This is a regression test for a bug where the cursor was reused for SHOW CREATE TABLE,
    which overwrote the SHOW FIELDS results.
    """
    # Mock cursor that simulates MySQL behavior
    cur = MagicMock()

    # Track which query is being executed
    query_results = {
        'SHOW FIELDS FROM test_table': {
            'description': [('Field',), ('Type',), ('Null',), ('Key',), ('Default',), ('Extra',)],
            'rows': [
                ('id', 'int', 'NO', 'PRI', None, 'auto_increment'),
                ('name', 'varchar(255)', 'YES', '', None, ''),
            ],
        },
        'SHOW CREATE TABLE test_table': {
            'description': [('Table',), ('Create Table',)],
            'rows': [('test_table', 'CREATE TABLE `test_table` ...')],
        },
    }

    current_query = [None]  # Use list to allow mutation in nested function

    def execute_side_effect(query):
        current_query[0] = query
        cur.description = query_results[query]['description']
        cur.rowcount = len(query_results[query]['rows'])

    def fetchall_side_effect():
        return query_results[current_query[0]]['rows']

    def fetchone_side_effect():
        rows = query_results[current_query[0]]['rows']
        return rows[0] if rows else None

    cur.execute.side_effect = execute_side_effect
    cur.fetchall.side_effect = fetchall_side_effect
    cur.fetchone.side_effect = fetchone_side_effect

    # Call list_tables with verbose=True (simulating \dt+ table_name)
    results = list_tables(cur, arg='test_table', verbose=True)

    assert len(results) == 1
    result = results[0]

    # The header should be from SHOW FIELDS
    assert result.header == ['Field', 'Type', 'Null', 'Key', 'Default', 'Extra']

    # The results should contain the field data, not be empty
    # Convert to list if it's a cursor or iterable
    result_data = list(result.rows) if hasattr(result.rows, '__iter__') else result.rows
    assert len(result_data) == 2
    assert result_data[0][0] == 'id'
    assert result_data[1][0] == 'name'

    # The postamble should contain the CREATE TABLE statement
    assert 'CREATE TABLE' in result.postamble


def test_u_suggests_databases():
    suggestions = suggest_type("\\u ", "\\u ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "database"}])


def test_describe_table():
    suggestions = suggest_type("\\dt", "\\dt ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "table", "schema": []}, {"type": "view", "schema": []}, {"type": "schema"}])


def test_list_or_show_create_tables():
    suggestions = suggest_type("\\dt+", "\\dt+ ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "table", "schema": []}, {"type": "view", "schema": []}, {"type": "schema"}])


def test_list_tables_nonverbose_and_empty_result() -> None:
    cursor = FakeCursor(
        query_results={
            'SHOW TABLES': {
                'description': [('Tables_in_test',)],
            },
            'SHOW FIELDS FROM missing_table': {
                'description': None,
            },
        }
    )

    listed = list_tables(cursor)
    assert listed[0].header == ['Tables_in_test']
    assert listed[0].rows is cursor

    described = list_tables(cursor, arg='missing_table')
    assert described[0].header is None
    assert described[0].rows is None


def test_list_databases_with_and_without_description() -> None:
    cursor = FakeCursor(
        query_results={
            'SHOW DATABASES': {
                'description': [('Database',)],
            },
        }
    )

    listed = list_databases(cursor)
    assert listed[0].header == ['Database']
    assert listed[0].rows is cursor

    empty_cursor = FakeCursor(query_results={'SHOW DATABASES': {'description': None}})
    empty = list_databases(empty_cursor)
    assert empty[0].header is None
    assert empty[0].rows is None


def test_status_uses_global_queries_decodes_bytes_and_formats_stats(monkeypatch) -> None:
    monkeypatch.setattr(dbcommands, '__version__', '9.9.9')
    monkeypatch.setattr(dbcommands.platform, 'python_implementation', lambda: 'CPython')
    monkeypatch.setattr(dbcommands.platform, 'python_version', lambda: '3.14.0')
    monkeypatch.setattr(dbcommands.iocommands, 'is_pager_enabled', lambda: True)
    monkeypatch.setattr(dbcommands, 'get_ssl_version', lambda cur: 'TLSv1.3')
    monkeypatch.setattr(dbcommands, 'format_uptime', lambda uptime: f'{uptime} seconds')
    monkeypatch.setenv('PAGER', 'less -SR')

    cursor = FakeCursor(
        connection=FakeConnection(host='tcp-host', port=3307, unix_socket=None),
        query_results={
            'SHOW GLOBAL STATUS;': {
                'rows': [
                    (b'Uptime', b'10'),
                    (b'Threads_connected', b'5'),
                    (b'Queries', b'20'),
                    (b'Slow_queries', b'1'),
                    (b'Opened_tables', b'2'),
                    (b'Flush_commands', b'3'),
                    (b'Open_tables', b'4'),
                ],
            },
            'SHOW GLOBAL VARIABLES;': {
                'rows': [
                    (b'version', b'8.0.0'),
                    (b'version_comment', b'Community'),
                    (b'protocol_version', b'10'),
                ],
            },
            'SELECT DATABASE(), USER();': {
                'rows': [('test_db', 'test_user')],
            },
            'SELECT @@character_set_server, @@character_set_database, @@character_set_client, @@character_set_connection LIMIT 1;': {
                'rows': [('utf8mb4', 'utf8mb4', 'utf8mb4', 'utf8mb4')],
            },
        },
    )

    result = status(cursor)[0]

    assert 'mycli 9.9.9 running on CPython 3.14.0' in result.preamble
    assert ('Connection id:', 42) in result.rows
    assert ('Current database:', 'test_db') in result.rows
    assert ('Current user:', 'test_user') in result.rows
    assert ('Current pager:', 'less -SR') in result.rows
    assert ('Server version:', '8.0.0 Community') in result.rows
    assert ('Protocol version:', '10') in result.rows
    assert ('SSL/TLS version:', 'TLSv1.3') in result.rows
    assert ('Connection:', 'tcp-host via TCP/IP') in result.rows
    assert ('TCP port:', 3307) in result.rows
    assert ('Uptime:', '10 seconds') in result.rows
    assert 'Connections: 5' in result.postamble
    assert 'Queries: 20' in result.postamble
    assert 'Slow queries: 1' in result.postamble
    assert 'Flush tables: 3' in result.postamble
    assert 'Queries per second avg: 2.000' in result.postamble
    assert '--------------' in result.postamble


def test_status_falls_back_to_show_status_and_handles_empty_selects(monkeypatch) -> None:
    monkeypatch.setattr(dbcommands, '__version__', '1.0.0')
    monkeypatch.setattr(dbcommands.platform, 'python_implementation', lambda: 'CPython')
    monkeypatch.setattr(dbcommands.platform, 'python_version', lambda: '3.10.0')
    monkeypatch.setattr(dbcommands.iocommands, 'is_pager_enabled', lambda: False)
    monkeypatch.setattr(dbcommands, 'get_ssl_version', lambda cur: 'none')
    monkeypatch.setattr(dbcommands, 'format_uptime', lambda uptime: f'{uptime} seconds')

    cursor = FakeCursor(
        connection=FakeConnection(unix_socket='/tmp/mysql.sock'),
        fail_on_queries={'SHOW GLOBAL STATUS;'},
        query_results={
            'SHOW STATUS;': {
                'rows': [
                    ('Slow_queries', '0'),
                    ('Opened_tables', '1'),
                    ('Open_tables', '2'),
                ],
            },
            'SHOW GLOBAL VARIABLES;': {
                'rows': [
                    ('version', '5.7.0'),
                    ('version_comment', 'Server'),
                    ('protocol_version', '10'),
                    ('socket', '/tmp/mysql.sock'),
                ],
            },
            'SELECT DATABASE(), USER();': {
                'rows': [],
            },
            'SELECT @@character_set_server, @@character_set_database, @@character_set_client, @@character_set_connection LIMIT 1;': {
                'rows': [],
            },
        },
    )

    result = status(cursor)[0]

    assert cursor.executed[0:2] == ['SHOW GLOBAL STATUS;', 'SHOW STATUS;']
    assert ('Current database:', '') in result.rows
    assert ('Current user:', '') in result.rows
    assert ('Current pager:', 'stdout') in result.rows
    assert ('Connection:', 'Localhost via UNIX socket') in result.rows
    assert ('UNIX socket:', '/tmp/mysql.sock') in result.rows
    assert ('Server characterset:', '') in result.rows
    assert ('Db characterset:', '') in result.rows
    assert ('Client characterset:', '') in result.rows
    assert ('Conn. characterset:', '') in result.rows
    assert 'Connections:' not in result.postamble
    assert '--------------' in result.postamble


def test_status_uses_system_default_pager_when_enabled_without_env(monkeypatch) -> None:
    monkeypatch.setattr(dbcommands.iocommands, 'is_pager_enabled', lambda: True)
    monkeypatch.setattr(dbcommands, 'get_ssl_version', lambda cur: 'TLS')
    monkeypatch.setattr(dbcommands.platform, 'python_implementation', lambda: 'CPython')
    monkeypatch.setattr(dbcommands.platform, 'python_version', lambda: '3.14.0')
    monkeypatch.delenv('PAGER', raising=False)

    cursor = FakeCursor(
        query_results={
            'SHOW GLOBAL STATUS;': {
                'rows': [('Slow_queries', '0'), ('Opened_tables', '1'), ('Open_tables', '2')],
            },
            'SHOW GLOBAL VARIABLES;': {
                'rows': [('version', '8.0'), ('version_comment', 'Server'), ('protocol_version', '10')],
            },
            'SELECT DATABASE(), USER();': {
                'rows': [('db', 'user')],
            },
            'SELECT @@character_set_server, @@character_set_database, @@character_set_client, @@character_set_connection LIMIT 1;': {
                'rows': [('utf8', 'utf8', 'utf8', 'utf8')],
            },
        },
    )

    result = status(cursor)[0]

    assert ('Current pager:', 'System default') in result.rows

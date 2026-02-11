# type: ignore

from unittest.mock import MagicMock

from mycli.packages.completion_engine import suggest_type
from mycli.packages.special.dbcommands import list_tables
from mycli.packages.special.utils import format_uptime
from test.test_completion_engine import sorted_dicts


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

    # The headers should be from SHOW FIELDS
    assert result.headers == ['Field', 'Type', 'Null', 'Key', 'Default', 'Extra']

    # The results should contain the field data, not be empty
    # Convert to list if it's a cursor or iterable
    result_data = list(result.results) if hasattr(result.results, '__iter__') else result.results
    assert len(result_data) == 2
    assert result_data[0][0] == 'id'
    assert result_data[1][0] == 'name'

    # The status should contain the CREATE TABLE statement
    assert 'CREATE TABLE' in result.status


def test_u_suggests_databases():
    suggestions = suggest_type("\\u ", "\\u ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "database"}])


def test_describe_table():
    suggestions = suggest_type("\\dt", "\\dt ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "table", "schema": []}, {"type": "view", "schema": []}, {"type": "schema"}])


def test_list_or_show_create_tables():
    suggestions = suggest_type("\\dt+", "\\dt+ ")
    assert sorted_dicts(suggestions) == sorted_dicts([{"type": "table", "schema": []}, {"type": "view", "schema": []}, {"type": "schema"}])


def test_format_uptime():
    seconds = 59
    assert "59 sec" == format_uptime(seconds)

    seconds = 120
    assert "2 min 0 sec" == format_uptime(seconds)

    seconds = 54890
    assert "15 hours 14 min 50 sec" == format_uptime(seconds)

    seconds = 598244
    assert "6 days 22 hours 10 min 44 sec" == format_uptime(seconds)

    seconds = 522600
    assert "6 days 1 hour 10 min 0 sec" == format_uptime(seconds)

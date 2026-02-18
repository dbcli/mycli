# type: ignore

import os.path
from unittest.mock import patch

from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
import pytest

import mycli.packages.special.main as special

metadata = {
    "users": ["id", "email", "first_name", "last_name"],
    "orders": ["id", "ordered_date", "status"],
    "select": ["id", "insert", "ABC"],
    "réveillé": ["id", "insert", "ABC"],
    "time_zone": ["Time_zone_id"],
    "time_zone_leap_second": ["Time_zone_id"],
    "time_zone_name": ["Time_zone_id"],
    "time_zone_transition": ["Time_zone_id"],
    "time_zone_transition_type": ["Time_zone_id"],
}


@pytest.fixture
def completer():
    import mycli.sqlcompleter as sqlcompleter

    comp = sqlcompleter.SQLCompleter(smart_completion=True)

    tables, columns = [], []

    for table, cols in metadata.items():
        tables.append((table,))
        columns.extend([(table, col) for col in cols])

    databases = ["test", "test 2"]

    for db in databases:
        comp.extend_schemata(db)
    comp.extend_database_names(databases)
    comp.set_dbname("test")
    comp.extend_relations(tables, kind="tables")
    comp.extend_columns(columns, kind="tables")
    comp.extend_enum_values([("orders", "status", ["pending", "shipped"])])
    comp.extend_special_commands(special.COMMANDS)

    return comp


@pytest.fixture
def empty_completer():
    import mycli.sqlcompleter as sqlcompleter

    comp = sqlcompleter.SQLCompleter(smart_completion=True)

    tables, columns = [], []

    for table, cols in metadata.items():
        tables.append((table,))
        columns.extend([(table, col) for col in cols])

    db = 'empty'

    comp.extend_schemata(db)
    comp.extend_database_names([db])
    comp.set_dbname(db)
    comp.extend_special_commands(special.COMMANDS)

    return comp


@pytest.fixture
def complete_event():
    from unittest.mock import Mock

    return Mock()


def test_use_database_completion(completer, complete_event):
    text = "USE "
    position = len(text)
    special.register_special_command(..., 'use', '\\u', 'Change to a new database.', aliases=['\\u'])
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
    ]


def test_special_name_completion(completer, complete_event):
    text = "\\d"
    position = len("\\d")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [Completion(text="\\dt", start_position=-2)]


def test_empty_string_completion(completer, complete_event):
    text = ""
    position = 0
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert list(map(Completion, completer.special_commands + completer.keywords)) == result


def test_select_keyword_completion(completer, complete_event):
    text = "SEL"
    position = len("SEL")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text='SELECT', start_position=-3),
        Completion(text='SERIAL', start_position=-3),
        Completion(text='MASTER_LOG_FILE', start_position=-3),
        Completion(text='MASTER_LOG_POS', start_position=-3),
        Completion(text='MASTER_TLS_CIPHERSUITES', start_position=-3),
        Completion(text='MASTER_TLS_VERSION', start_position=-3),
        Completion(text='SCHEDULE', start_position=-3),
        Completion(text='SERIALIZABLE', start_position=-3),
    ]


def test_select_star(completer, complete_event):
    text = "SELECT * "
    position = len(text)
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == list(map(Completion, completer.keywords))


def test_table_completion(completer, complete_event):
    text = "SELECT * FROM "
    position = len(text)
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="users", start_position=0),
        Completion(text="orders", start_position=0),
        Completion(text="`select`", start_position=0),
        Completion(text="`réveillé`", start_position=0),
        Completion(text="time_zone", start_position=0),
        Completion(text="time_zone_leap_second", start_position=0),
        Completion(text="time_zone_name", start_position=0),
        Completion(text="time_zone_transition", start_position=0),
        Completion(text="time_zone_transition_type", start_position=0),
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
    ]


def test_select_filtered_table_completion(completer, complete_event):
    text = "SELECT ABC FROM "
    position = len(text)
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="`select`", start_position=0),
        Completion(text="`réveillé`", start_position=0),
        Completion(text="users", start_position=0),
        Completion(text="orders", start_position=0),
        Completion(text="time_zone", start_position=0),
        Completion(text="time_zone_leap_second", start_position=0),
        Completion(text="time_zone_name", start_position=0),
        Completion(text="time_zone_transition", start_position=0),
        Completion(text="time_zone_transition_type", start_position=0),
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
    ]


def test_sub_select_filtered_table_completion(completer, complete_event):
    text = "SELECT * FROM (SELECT ordered_date FROM "
    position = len(text)
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="orders", start_position=0),
        Completion(text="users", start_position=0),
        Completion(text="`select`", start_position=0),
        Completion(text="`réveillé`", start_position=0),
        Completion(text="time_zone", start_position=0),
        Completion(text="time_zone_leap_second", start_position=0),
        Completion(text="time_zone_name", start_position=0),
        Completion(text="time_zone_transition", start_position=0),
        Completion(text="time_zone_transition_type", start_position=0),
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
    ]


def test_enum_value_completion(completer, complete_event):
    text = "SELECT * FROM orders WHERE status = "
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="'pending'", start_position=0),
        Completion(text="'shipped'", start_position=0),
    ]


def test_function_name_completion(completer, complete_event):
    text = "SELECT MA"
    position = len("SELECT MA")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text='MAX', start_position=-2),
        Completion(text='MATCH', start_position=-2),
        Completion(text='MASTER', start_position=-2),
        Completion(text='MAKE_SET', start_position=-2),
        Completion(text='MAKEDATE', start_position=-2),
        Completion(text='MAKETIME', start_position=-2),
        Completion(text='MAX_ROWS', start_position=-2),
        Completion(text='MAX_SIZE', start_position=-2),
        Completion(text='MAXVALUE', start_position=-2),
        Completion(text='MASTER_SSL', start_position=-2),
        Completion(text='MASTER_BIND', start_position=-2),
        Completion(text='MASTER_HOST', start_position=-2),
        Completion(text='MASTER_PORT', start_position=-2),
        Completion(text='MASTER_USER', start_position=-2),
        Completion(text='MASTER_DELAY', start_position=-2),
        Completion(text='MASTER_SSL_CA', start_position=-2),
        Completion(text='MASTER_LOG_POS', start_position=-2),
        Completion(text='MASTER_SSL_CRL', start_position=-2),
        Completion(text='MASTER_SSL_KEY', start_position=-2),
        Completion(text='MASTER_POS_WAIT', start_position=-2),
        Completion(text='MASTER_LOG_FILE', start_position=-2),
        Completion(text='MASTER_PASSWORD', start_position=-2),
        Completion(text='MASTER_SSL_CERT', start_position=-2),
        Completion(text='MASTER_SSL_CAPATH', start_position=-2),
        Completion(text='MASTER_SSL_CIPHER', start_position=-2),
        Completion(text='MASTER_RETRY_COUNT', start_position=-2),
        Completion(text='MASTER_SSL_CRLPATH', start_position=-2),
        Completion(text='MASTER_TLS_VERSION', start_position=-2),
        Completion(text='MASTER_AUTO_POSITION', start_position=-2),
        Completion(text='MASTER_CONNECT_RETRY', start_position=-2),
        Completion(text='MAX_QUERIES_PER_HOUR', start_position=-2),
        Completion(text='MAX_UPDATES_PER_HOUR', start_position=-2),
        Completion(text='MAX_USER_CONNECTIONS', start_position=-2),
        Completion(text='MASTER_PUBLIC_KEY_PATH', start_position=-2),
        Completion(text='MASTER_HEARTBEAT_PERIOD', start_position=-2),
        Completion(text='MASTER_TLS_CIPHERSUITES', start_position=-2),
        Completion(text='MAX_CONNECTIONS_PER_HOUR', start_position=-2),
        Completion(text='MASTER_COMPRESSION_ALGORITHMS', start_position=-2),
        Completion(text='MASTER_SSL_VERIFY_SERVER_CERT', start_position=-2),
        Completion(text='MASTER_ZSTD_COMPRESSION_LEVEL', start_position=-2),
        Completion(text='email', start_position=-2),
        Completion(text='DECIMAL', start_position=-2),
        Completion(text='SMALLINT', start_position=-2),
        Completion(text='TIMESTAMP', start_position=-2),
        Completion(text='COLUMN_FORMAT', start_position=-2),
        Completion(text='COLUMN_NAME', start_position=-2),
        Completion(text='COMPACT', start_position=-2),
        Completion(text='CONSTRAINT_SCHEMA', start_position=-2),
        Completion(text='CURRENT_TIMESTAMP', start_position=-2),
        Completion(text='FORMAT', start_position=-2),
        Completion(text='GET_FORMAT', start_position=-2),
        Completion(text='GET_MASTER_PUBLIC_KEY', start_position=-2),
        Completion(text='LOCALTIMESTAMP', start_position=-2),
        Completion(text='MESSAGE_TEXT', start_position=-2),
        Completion(text='MIGRATE', start_position=-2),
        Completion(text='NETWORK_NAMESPACE', start_position=-2),
        Completion(text='PRIMARY', start_position=-2),
        Completion(text='REQUIRE_ROW_FORMAT', start_position=-2),
        Completion(text='REQUIRE_TABLE_PRIMARY_KEY_CHECK', start_position=-2),
        Completion(text='ROW_FORMAT', start_position=-2),
        Completion(text='SCHEMA', start_position=-2),
        Completion(text='SCHEMA_NAME', start_position=-2),
        Completion(text='SCHEMAS', start_position=-2),
        Completion(text='SQL_SMALL_RESULT', start_position=-2),
        Completion(text='TEMPORARY', start_position=-2),
        Completion(text='TEMPTABLE', start_position=-2),
        Completion(text='TERMINATED', start_position=-2),
        Completion(text='TIMESTAMPADD', start_position=-2),
        Completion(text='TIMESTAMPDIFF', start_position=-2),
        Completion(text='UTC_TIMESTAMP', start_position=-2),
        Completion(text='CHANGE MASTER TO', start_position=-2),
    ]


def test_suggested_column_names(completer, complete_event):
    """Suggest column and function names when selecting from table.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT  from users"
    position = len("SELECT ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(
        [
            Completion(text="*", start_position=0),
            Completion(text="id", start_position=0),
            Completion(text="email", start_position=0),
            Completion(text="first_name", start_position=0),
            Completion(text="last_name", start_position=0),
        ]
        + list(map(Completion, completer.functions))
        + [Completion(text="users", start_position=0)]
        + [x for x in map(Completion, completer.keywords) if x.text not in completer.functions]
    )


def test_suggested_column_names_empty_db(empty_completer, complete_event):
    """Suggest * and function/keywords when selecting from no-table db.

    :param empty_completer:
    :param complete_event:
    :return:

    """
    text = "SELECT "
    position = len("SELECT ")
    result = list(empty_completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(
        [
            Completion(text="*", start_position=0),
        ]
        + list(map(Completion, empty_completer.functions))
        + [x for x in map(Completion, empty_completer.keywords) if x.text not in empty_completer.functions]
    )


def test_suggested_column_names_in_function(completer, complete_event):
    """Suggest column and function names when selecting multiple columns from
    table.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT MAX( from users"
    position = len("SELECT MAX(")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="email", start_position=0),
        Completion(text="first_name", start_position=0),
        Completion(text="last_name", start_position=0),
    ]


def test_suggested_column_names_with_table_dot(completer, complete_event):
    """Suggest column names on table name and dot.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT users. from users"
    position = len("SELECT users.")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="email", start_position=0),
        Completion(text="first_name", start_position=0),
        Completion(text="last_name", start_position=0),
    ]


def test_suggested_column_names_with_alias(completer, complete_event):
    """Suggest column names on table alias and dot.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT u. from users u"
    position = len("SELECT u.")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="email", start_position=0),
        Completion(text="first_name", start_position=0),
        Completion(text="last_name", start_position=0),
    ]


def test_suggested_multiple_column_names(completer, complete_event):
    """Suggest column and function names when selecting multiple columns from
    table.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT id,  from users u"
    position = len("SELECT id, ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(
        [
            Completion(text="*", start_position=0),
            Completion(text="id", start_position=0),
            Completion(text="email", start_position=0),
            Completion(text="first_name", start_position=0),
            Completion(text="last_name", start_position=0),
        ]
        + list(map(Completion, completer.functions))
        + [Completion(text="u", start_position=0)]
        + [x for x in map(Completion, completer.keywords) if x.text not in completer.functions]
    )


def test_suggested_multiple_column_names_with_alias(completer, complete_event):
    """Suggest column names on table alias and dot when selecting multiple
    columns from table.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT u.id, u. from users u"
    position = len("SELECT u.id, u.")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="email", start_position=0),
        Completion(text="first_name", start_position=0),
        Completion(text="last_name", start_position=0),
    ]


def test_suggested_multiple_column_names_with_dot(completer, complete_event):
    """Suggest column names on table names and dot when selecting multiple
    columns from table.

    :param completer:
    :param complete_event:
    :return:

    """
    text = "SELECT users.id, users. from users u"
    position = len("SELECT users.id, users.")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="email", start_position=0),
        Completion(text="first_name", start_position=0),
        Completion(text="last_name", start_position=0),
    ]


def test_suggested_aliases_after_on(completer, complete_event):
    text = "SELECT u.name, o.id FROM users u JOIN orders o ON "
    position = len("SELECT u.name, o.id FROM users u JOIN orders o ON ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="u", start_position=0),
        Completion(text="o", start_position=0),
    ]


def test_suggested_aliases_after_on_right_side(completer, complete_event):
    text = "SELECT u.name, o.id FROM users u JOIN orders o ON o.user_id = "
    position = len("SELECT u.name, o.id FROM users u JOIN orders o ON o.user_id = ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="u", start_position=0),
        Completion(text="o", start_position=0),
    ]


def test_suggested_tables_after_on(completer, complete_event):
    text = "SELECT users.name, orders.id FROM users JOIN orders ON "
    position = len("SELECT users.name, orders.id FROM users JOIN orders ON ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="users", start_position=0),
        Completion(text="orders", start_position=0),
    ]


def test_suggested_tables_after_on_right_side(completer, complete_event):
    text = "SELECT users.name, orders.id FROM users JOIN orders ON orders.user_id = "
    position = len("SELECT users.name, orders.id FROM users JOIN orders ON orders.user_id = ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="users", start_position=0),
        Completion(text="orders", start_position=0),
    ]


def test_table_names_after_from(completer, complete_event):
    text = "SELECT * FROM "
    position = len("SELECT * FROM ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="users", start_position=0),
        Completion(text="orders", start_position=0),
        Completion(text="`select`", start_position=0),
        Completion(text="`réveillé`", start_position=0),
        Completion(text="time_zone", start_position=0),
        Completion(text="time_zone_leap_second", start_position=0),
        Completion(text="time_zone_name", start_position=0),
        Completion(text="time_zone_transition", start_position=0),
        Completion(text="time_zone_transition_type", start_position=0),
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
    ]


def test_table_names_leading_partial(completer, complete_event):
    text = "SELECT * FROM time_zone"
    position = len("SELECT * FROM time_zone")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="time_zone", start_position=-9),
        Completion(text="time_zone_name", start_position=-9),
        Completion(text="time_zone_transition", start_position=-9),
        Completion(text="time_zone_leap_second", start_position=-9),
        Completion(text="time_zone_transition_type", start_position=-9),
    ]


def test_table_names_inter_partial(completer, complete_event):
    text = "SELECT * FROM time_leap"
    position = len("SELECT * FROM time_leap")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="time_zone_leap_second", start_position=-9),
        Completion(text='time_zone_name', start_position=-9),
        Completion(text='time_zone_transition', start_position=-9),
        Completion(text='time_zone_transition_type', start_position=-9),
    ]


def test_table_names_fuzzy(completer, complete_event):
    text = "SELECT * FROM tim_leap"
    position = len("SELECT * FROM tim_leap")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="time_zone_leap_second", start_position=-8),
    ]


def test_auto_escaped_col_names(completer, complete_event):
    text = "SELECT  from `select`"
    position = len("SELECT ")
    result = [x.text for x in completer.get_completions(Document(text=text, cursor_position=position), complete_event)]
    expected = (
        [
            "*",
            "id",
            "`insert`",
            "ABC",
        ]
        + completer.functions
        + ["select"]
        + [x for x in completer.keywords if x not in completer.functions]
    )
    assert result == expected


def test_un_escaped_table_names(completer, complete_event):
    text = "SELECT  from réveillé"
    position = len("SELECT ")
    result = [x.text for x in completer.get_completions(Document(text=text, cursor_position=position), complete_event)]
    assert result == [
        "*",
        "id",
        "`insert`",
        "ABC",
    ] + completer.functions + ["réveillé"] + [x for x in completer.keywords if x not in completer.functions]


# todo: the fixtures are insufficient; the database name should also appear in the result
def test_grant_on_suggets_tables_and_schemata(completer, complete_event):
    text = "GRANT ALL ON "
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="test", start_position=0),
        Completion(text="`test 2`", start_position=0),
        Completion(text='users', start_position=0),
        Completion(text='orders', start_position=0),
        Completion(text='`select`', start_position=0),
        Completion(text='`réveillé`', start_position=0),
        Completion(text='time_zone', start_position=0),
        Completion(text='time_zone_leap_second', start_position=0),
        Completion(text='time_zone_name', start_position=0),
        Completion(text='time_zone_transition', start_position=0),
        Completion(text='time_zone_transition_type', start_position=0),
    ]


# todo: this test belongs more logically in test_naive_completion.py, but it didn't work there:
#       multiple completion candidates were not suggested.
def test_deleted_keyword_completion(completer, complete_event):
    text = "exi"
    position = len("exi")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="exit", start_position=-3),
        Completion(text='exists', start_position=-3),
        Completion(text='explain', start_position=-3),
        Completion(text='expire', start_position=-3),
    ]


def test_numbers_no_completion(completer, complete_event):
    text = "SELECT COUNT(1) FROM time_zone WHERE Time_zone_id = 1"
    position = len("SELECT COUNT(1) FROM time_zone WHERE Time_zone_id = 1")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []  # ie not INT1


def dummy_list_path(dir_name):
    dirs = {
        "/": [
            "dir1",
            "file1.sql",
            "file2.sql",
        ],
        "/dir1": [
            "subdir1",
            "subfile1.sql",
            "subfile2.sql",
        ],
        "/dir1/subdir1": [
            "lastfile.sql",
        ],
    }
    return dirs.get(dir_name, [])


@patch("mycli.packages.filepaths.list_path", new=dummy_list_path)
@pytest.mark.parametrize(
    "text,expected",
    [
        ('source ', [('/', 0), ('~', 0), ('.', 0), ('..', 0)]),
        ("source /", [("dir1", 0), ("file1.sql", 0), ("file2.sql", 0)]),
        ("source /dir1/", [("subdir1", 0), ("subfile1.sql", 0), ("subfile2.sql", 0)]),
        ("source /dir1/subdir1/", [("lastfile.sql", 0)]),
    ],
)
def test_file_name_completion(completer, complete_event, text, expected):
    position = len(text)
    special.register_special_command(..., 'source', '\\. filename', 'Execute commands from file.', aliases=['\\.'])
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    expected = [Completion(txt, pos) for txt, pos in expected]
    assert result == expected


def test_auto_case_heuristic(completer, complete_event):
    text = "select jon_"
    position = len("select jon_")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert [x.text for x in result] == [
        'json_table',
        'json_value',
        'join',
        'json',
    ]


def test_create_table_like_completion(completer, complete_event):
    text = "CREATE TABLE foo LIKE ti"
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert [x.text for x in result] == [
        'time_zone',
        'time_zone_name',
        'time_zone_transition',
        'time_zone_leap_second',
        'time_zone_transition_type',
    ]


def test_source_eager_completion(completer, complete_event):
    text = "source sc"
    position = len(text)
    script_filename = 'script_for_test_suite.sql'
    f = open(script_filename, 'w')
    f.close()
    special.register_special_command(..., 'source', '\\. filename', 'Execute commands from file.', aliases=['\\.'])
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    success = True
    error = 'unknown'
    try:
        assert [x.text for x in result] == [
            script_filename,
            'screenshots/',
        ]
    except AssertionError as e:
        success = False
        error = e
    if os.path.exists(script_filename):
        os.remove(script_filename)
    if not success:
        raise AssertionError(error)


def test_source_leading_dot_suggestions_completion(completer, complete_event):
    text = "source ./sc"
    position = len(text)
    script_filename = 'script_for_test_suite.sql'
    f = open(script_filename, 'w')
    f.close()
    special.register_special_command(..., 'source', '\\. filename', 'Execute commands from file.', aliases=['\\.'])
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    success = True
    error = 'unknown'
    try:
        assert [x.text for x in result] == [
            script_filename,
            'screenshots/',
        ]
    except AssertionError as e:
        success = False
        error = e
    if os.path.exists(script_filename):
        os.remove(script_filename)
    if not success:
        raise AssertionError(error)


def test_string_no_completion(completer, complete_event):
    text = 'select "json'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


def test_string_no_completion_single_quote(completer, complete_event):
    text = "select 'json"
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


def test_string_no_completion_spaces(completer, complete_event):
    text = 'select "nocomplete json'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


def test_string_no_completion_spaces_inner_1(completer, complete_event):
    text = 'select "json nocomplete'
    position = len('select "json')
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


def test_string_no_completion_spaces_inner_2(completer, complete_event):
    text = 'select "json nocomplete'
    position = len('select "json ')
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


def test_backticked_column_completion(completer, complete_event):
    text = 'select `Tim'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        # todo it would be nicer if the column names sorted to the top
        Completion(text='`time`', start_position=-4),
        Completion(text='`timediff`', start_position=-4),
        Completion(text='`timestamp`', start_position=-4),
        Completion(text='`time_format`', start_position=-4),
        Completion(text='`time_to_sec`', start_position=-4),
        Completion(text='`Time_zone_id`', start_position=-4),
        Completion(text='`timestampadd`', start_position=-4),
        Completion(text='`timestampdiff`', start_position=-4),
        Completion(text='`datetime`', start_position=-4),
        Completion(text='`optimize`', start_position=-4),
        Completion(text='`optimizer_costs`', start_position=-4),
        Completion(text='`utc_time`', start_position=-4),
        Completion(text='`utc_timestamp`', start_position=-4),
        Completion(text='`current_time`', start_position=-4),
        Completion(text='`current_timestamp`', start_position=-4),
        Completion(text='`localtime`', start_position=-4),
        Completion(text='`localtimestamp`', start_position=-4),
        Completion(text='`password_lock_time`', start_position=-4),
    ]


def test_backticked_column_completion_component(completer, complete_event):
    text = 'select `com'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        # todo it would be nicer if "comment" sorted to the top because it is a column name,
        #      and because it is a reserved word
        Completion(text='`commit`', start_position=-4),
        Completion(text='`comment`', start_position=-4),
        Completion(text='`compact`', start_position=-4),
        Completion(text='`compress`', start_position=-4),
        Completion(text='`committed`', start_position=-4),
        Completion(text='`component`', start_position=-4),
        Completion(text='`completion`', start_position=-4),
        Completion(text='`compressed`', start_position=-4),
        Completion(text='`compression`', start_position=-4),
        Completion(text='`column`', start_position=-4),
        Completion(text='`column_format`', start_position=-4),
        Completion(text='`column_name`', start_position=-4),
        Completion(text='`columns`', start_position=-4),
        Completion(text='`second_microsecond`', start_position=-4),
        Completion(text='`uncommitted`', start_position=-4),
    ]


def test_backticked_column_completion_two_character(completer, complete_event):
    text = 'select `f'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        # todo it would be nicer if the column name "first_name" sorted to the top
        Completion(text='`for`', start_position=-2),
        Completion(text='`from`', start_position=-2),
        Completion(text='`fast`', start_position=-2),
        Completion(text='`file`', start_position=-2),
        Completion(text='`full`', start_position=-2),
        Completion(text='`field`', start_position=-2),
        Completion(text='`floor`', start_position=-2),
        Completion(text='`fixed`', start_position=-2),
        Completion(text='`float`', start_position=-2),
        Completion(text='`false`', start_position=-2),
        Completion(text='`fetch`', start_position=-2),
        Completion(text='`first`', start_position=-2),
        Completion(text='`flush`', start_position=-2),
        Completion(text='`force`', start_position=-2),
        Completion(text='`found`', start_position=-2),
        Completion(text='`float4`', start_position=-2),
        Completion(text='`float8`', start_position=-2),
        Completion(text='`factor`', start_position=-2),
        Completion(text='`faults`', start_position=-2),
        Completion(text='`fields`', start_position=-2),
        Completion(text='`filter`', start_position=-2),
        Completion(text='`finish`', start_position=-2),
        Completion(text='`format`', start_position=-2),
        Completion(text='`follows`', start_position=-2),
        Completion(text='`foreign`', start_position=-2),
        Completion(text='`fulltext`', start_position=-2),
        Completion(text='`function`', start_position=-2),
        Completion(text='`from_days`', start_position=-2),
        Completion(text='`following`', start_position=-2),
        Completion(text='`first_name`', start_position=-2),
        Completion(text='`found_rows`', start_position=-2),
        Completion(text='`find_in_set`', start_position=-2),
        Completion(text='`from_base64`', start_position=-2),
        Completion(text='`first_value`', start_position=-2),
        Completion(text='`foreign key`', start_position=-2),
        Completion(text='`format_bytes`', start_position=-2),
        Completion(text='`from_unixtime`', start_position=-2),
        Completion(text='`file_block_size`', start_position=-2),
        Completion(text='`format_pico_time`', start_position=-2),
        Completion(text='`failed_login_attempts`', start_position=-2),
        Completion(text='`left join`', start_position=-2),
        Completion(text='`after`', start_position=-2),
        Completion(text='`before`', start_position=-2),
        Completion(text='`default`', start_position=-2),
        Completion(text='`default_auth`', start_position=-2),
        Completion(text='`definer`', start_position=-2),
        Completion(text='`definition`', start_position=-2),
        Completion(text='`enforced`', start_position=-2),
        Completion(text='`if`', start_position=-2),
        Completion(text='`infile`', start_position=-2),
        Completion(text='`left`', start_position=-2),
        Completion(text='`logfile`', start_position=-2),
        Completion(text='`of`', start_position=-2),
        Completion(text='`off`', start_position=-2),
        Completion(text='`offset`', start_position=-2),
        Completion(text='`outfile`', start_position=-2),
        Completion(text='`profile`', start_position=-2),
        Completion(text='`profiles`', start_position=-2),
        Completion(text='`reference`', start_position=-2),
        Completion(text='`references`', start_position=-2),
    ]


def test_backticked_column_completion_three_character(completer, complete_event):
    text = 'select `fi'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        # todo it would be nicer if the column name "first_name" sorted to the top
        Completion(text='`file`', start_position=-3),
        Completion(text='`field`', start_position=-3),
        Completion(text='`fixed`', start_position=-3),
        Completion(text='`first`', start_position=-3),
        Completion(text='`fields`', start_position=-3),
        Completion(text='`filter`', start_position=-3),
        Completion(text='`finish`', start_position=-3),
        Completion(text='`first_name`', start_position=-3),
        Completion(text='`find_in_set`', start_position=-3),
        Completion(text='`first_value`', start_position=-3),
        Completion(text='`file_block_size`', start_position=-3),
        Completion(text='`definer`', start_position=-3),
        Completion(text='`definition`', start_position=-3),
        Completion(text='`failed_login_attempts`', start_position=-3),
        Completion(text='`foreign`', start_position=-3),
        Completion(text='`infile`', start_position=-3),
        Completion(text='`logfile`', start_position=-3),
        Completion(text='`outfile`', start_position=-3),
        Completion(text='`profile`', start_position=-3),
        Completion(text='`profiles`', start_position=-3),
        Completion(text='`foreign key`', start_position=-3),
    ]


def test_backticked_column_completion_four_character(completer, complete_event):
    text = 'select `fir'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        # todo it would be nicer if the column name "first_name" sorted to the top
        Completion(text='`first`', start_position=-4),
        Completion(text='`first_name`', start_position=-4),
        Completion(text='`first_value`', start_position=-4),
        Completion(text='`definer`', start_position=-4),
        Completion(text='`filter`', start_position=-4),
    ]


def test_backticked_table_completion_required(completer, complete_event):
    text = 'select ABC from `rév'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text='`réveillé`', start_position=-4),
    ]


def test_backticked_table_completion_not_required(completer, complete_event):
    text = 'select * from `t'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text='`test`', start_position=-2),
        Completion(text='`test 2`', start_position=-2),
        Completion(text='`time_zone`', start_position=-2),
        Completion(text='`time_zone_name`', start_position=-2),
        Completion(text='`time_zone_transition`', start_position=-2),
        Completion(text='`time_zone_leap_second`', start_position=-2),
        Completion(text='`time_zone_transition_type`', start_position=-2),
    ]


def test_string_no_completion_backtick(completer, complete_event):
    text = 'select * from "`t'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []


# todo this shouldn't suggest anything but the space resets the logic
# and it completes on "bar" alone
@pytest.mark.xfail
def test_backticked_no_completion_spaces(completer, complete_event):
    text = 'select * from `nocomplete bar'
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == []

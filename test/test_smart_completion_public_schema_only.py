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
}


@pytest.fixture
def completer():
    import mycli.sqlcompleter as sqlcompleter

    comp = sqlcompleter.SQLCompleter(smart_completion=True)

    tables, columns = [], []

    for table, cols in metadata.items():
        tables.append((table,))
        columns.extend([(table, col) for col in cols])

    comp.set_dbname("test")
    comp.extend_schemata("test")
    comp.extend_relations(tables, kind="tables")
    comp.extend_columns(columns, kind="tables")
    comp.extend_special_commands(special.COMMANDS)

    return comp


@pytest.fixture
def complete_event():
    from unittest.mock import Mock

    return Mock()


def test_special_name_completion(completer, complete_event):
    text = "\\d"
    position = len("\\d")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert result == [Completion(text="\\dt", start_position=-2)]


def test_empty_string_completion(completer, complete_event):
    text = ""
    position = 0
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert list(map(Completion, completer.keywords + completer.special_commands)) == result


def test_select_keyword_completion(completer, complete_event):
    text = "SEL"
    position = len("SEL")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [Completion(text="SELECT", start_position=-3)]


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
    ]


def test_function_name_completion(completer, complete_event):
    text = "SELECT MA"
    position = len("SELECT MA")
    result = completer.get_completions(Document(text=text, cursor_position=position), complete_event)
    assert list(result) == [
        Completion(text="MAX", start_position=-2),
        Completion(text="CHANGE MASTER TO", start_position=-2),
        Completion(text="CURRENT_TIMESTAMP", start_position=-2),
        Completion(text="DECIMAL", start_position=-2),
        Completion(text="FORMAT", start_position=-2),
        Completion(text="MASTER", start_position=-2),
        Completion(text="PRIMARY", start_position=-2),
        Completion(text="ROW_FORMAT", start_position=-2),
        Completion(text="SMALLINT", start_position=-2),
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
        + list(map(Completion, completer.keywords))
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
        + list(map(Completion, completer.keywords))
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
    ]


def test_auto_escaped_col_names(completer, complete_event):
    text = "SELECT  from `select`"
    position = len("SELECT ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [
        Completion(text="*", start_position=0),
        Completion(text="id", start_position=0),
        Completion(text="`insert`", start_position=0),
        Completion(text="`ABC`", start_position=0),
    ] + list(map(Completion, completer.functions)) + [Completion(text="select", start_position=0)] + list(
        map(Completion, completer.keywords)
    )


def test_un_escaped_table_names(completer, complete_event):
    text = "SELECT  from réveillé"
    position = len("SELECT ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(
        [
            Completion(text="*", start_position=0),
            Completion(text="id", start_position=0),
            Completion(text="`insert`", start_position=0),
            Completion(text="`ABC`", start_position=0),
        ]
        + list(map(Completion, completer.functions))
        + [Completion(text="réveillé", start_position=0)]
        + list(map(Completion, completer.keywords))
    )


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
        #    ('source ',  [('~', 0),
        #                  ('/', 0),
        #                  ('.', 0),
        #                  ('..', 0)]),
        ("source /", [("dir1", 0), ("file1.sql", 0), ("file2.sql", 0)]),
        ("source /dir1/", [("subdir1", 0), ("subfile1.sql", 0), ("subfile2.sql", 0)]),
        ("source /dir1/subdir1/", [("lastfile.sql", 0)]),
    ],
)
def test_file_name_completion(completer, complete_event, text, expected):
    position = len(text)
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    expected = [Completion(txt, pos) for txt, pos in expected]
    assert result == expected

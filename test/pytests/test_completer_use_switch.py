# type: ignore
"""Regression tests for completing right after a schema (``USE``) switch.

When the user runs ``USE <db>``, ``refresh_completions(reset=True)`` updates the
live completer's ``dbname`` *immediately* so unqualified completions reflect the
switch, while the matching table metadata is still being fetched on a background
thread (and only swapped in when the refresh finishes).

In that window ``self.dbname`` names a schema that is not yet a key in
``dbmetadata["tables"]``.  A naked ``SELECT `` completion reaches
``populate_scoped_cols`` with no scoped tables and used to crash with
``KeyError`` on ``meta["tables"][self.dbname]``.  These tests pin the safe
behaviour: suggest ``*`` during the window, real columns once loaded.
"""

import threading
import traceback

from prompt_toolkit.document import Document

from mycli.sqlcompleter import SQLCompleter


def _make_completer() -> SQLCompleter:
    completer = SQLCompleter(smart_completion=True)
    completer.load_schema_metadata(
        schema="old_db",
        table_columns={"orders": ["*", "id", "total"]},
        foreign_keys={},
        enum_values={},
        functions={},
        procedures={},
    )
    completer.set_dbname("old_db")
    return completer


def test_populate_scoped_cols_unloaded_schema_returns_star() -> None:
    completer = _make_completer()
    # Switch to a schema whose metadata has not been loaded yet.
    completer.set_dbname("new_db")
    assert "new_db" not in completer.dbmetadata["tables"]

    # Empty scoped tables => the "naked SELECT" branch that does the lookup.
    assert completer.populate_scoped_cols([]) == ["*"]


def test_get_completions_after_use_switch_before_refresh() -> None:
    completer = _make_completer()
    completer.set_dbname("new_db")  # metadata not loaded yet

    for text in ("SELECT ", "SELECT col", "SELECT a, "):
        document = Document(text, len(text))
        # Must not raise KeyError while the background refresh is in flight.
        completions = list(completer.get_completions(document, None))
        assert all(c.text for c in completions)


def test_columns_available_once_schema_loads() -> None:
    completer = _make_completer()
    completer.set_dbname("new_db")
    # Background refresh finishes and loads the new schema.
    completer.load_schema_metadata(
        schema="new_db",
        table_columns={"customers": ["*", "name", "email"]},
        foreign_keys={},
        enum_values={},
        functions={},
        procedures={},
    )

    cols = completer.populate_scoped_cols([])
    assert "name" in cols
    assert "email" in cols


def test_completion_during_concurrent_use_switch_does_not_crash() -> None:
    """A reader must survive a writer flipping ``dbname`` between schemas.

    Mirrors the live REPL: prompt_toolkit's completion thread reads the
    completer lock-free while a background refresh switches ``dbname`` and
    loads/unloads schema metadata.
    """
    completer = _make_completer()
    stop = threading.Event()
    errors: list[str] = []

    def reader() -> None:
        document = Document("SELECT ", len("SELECT "))
        while not stop.is_set():
            try:
                list(completer.get_completions(document, None))
            except Exception:
                errors.append(traceback.format_exc())
                return

    def writer() -> None:
        n = 0
        while not stop.is_set() and n < 2000:
            n += 1
            schema = f"db_{n}"
            # Point dbname at a not-yet-loaded schema, then load it, as the
            # reset=True refresh path does.
            completer.set_dbname(schema)
            completer.load_schema_metadata(
                schema=schema,
                table_columns={"t": ["*", "c1", "c2"]},
                foreign_keys={},
                enum_values={},
                functions={},
                procedures={},
            )

    threads = [threading.Thread(target=reader) for _ in range(3)]
    threads.append(threading.Thread(target=writer))
    for thread in threads:
        thread.start()
    threads[-1].join(timeout=5)
    stop.set()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors, "completion crashed during USE switch:\n" + "\n".join(errors)

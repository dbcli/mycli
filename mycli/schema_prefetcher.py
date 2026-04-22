"""Background prefetcher for multi-schema auto-completion.

The default completion refresher only populates metadata for the
currently-selected schema.  ``SchemaPrefetcher`` loads metadata for
additional schemas on a background thread so that users can get
qualified auto-completion suggestions (``OtherSchema.table``) without
switching databases first.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable

from mycli.sqlexecute import SQLExecute

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mycli.main import MyCli
    from mycli.sqlcompleter import SQLCompleter

_logger = logging.getLogger(__name__)


class PrefetchMode(str, Enum):
    ALWAYS = 'always'
    NEVER = 'never'
    LISTED = 'listed'


def parse_prefetch_config(mode: str, schema_list: list[str]) -> list[str] | None:
    """Parse the ``prefetch_schemas_mode`` / ``prefetch_schemas_list`` options.

    Returns ``None`` when every accessible schema should be prefetched
    (``always``), an empty list when prefetching is disabled
    (``never``), or ``schema_list`` when the mode is ``listed``.
    Unknown modes fall back to ``always``.
    """
    try:
        parsed = PrefetchMode(mode.strip().lower())
    except ValueError:
        return None
    if parsed is PrefetchMode.NEVER:
        return []
    if parsed is PrefetchMode.LISTED:
        return schema_list
    return None


class SchemaPrefetcher:
    """Run schema prefetch work on a dedicated background thread."""

    def __init__(self, mycli: 'MyCli') -> None:
        self.mycli = mycli
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._loaded: set[str] = set()

    def is_prefetching(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def clear_loaded(self) -> None:
        """Forget which schemas have been prefetched (used on reset)."""
        self._loaded.clear()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the background thread to stop and wait briefly for it."""
        if self._thread and self._thread.is_alive():
            self._cancel.set()
            self._thread.join(timeout=timeout)
        self._cancel = threading.Event()
        self._thread = None

    def start_configured(self) -> None:
        """Start prefetching based on the user's prefetch settings."""
        mode = getattr(self.mycli, 'prefetch_schemas_mode', PrefetchMode.ALWAYS.value)
        schema_list = getattr(self.mycli, 'prefetch_schemas_list', [])
        parsed = parse_prefetch_config(mode, schema_list)
        if parsed is not None and not parsed:
            # ``never`` or ``listed`` with an empty list — nothing to do.
            return
        self._start(parsed)

    def prefetch_schema_now(self, schema: str) -> None:
        """Fetch *schema* immediately on a background thread.

        Used when a user manually switches to a schema.  The method
        returns quickly; the actual work happens in the new thread.
        """
        if not schema:
            return
        # Avoid double-fetching while a full-prefetch pass is running.
        self.stop()
        self._start([schema])

    def _start(self, schemas: Iterable[str] | None) -> None:
        """Spawn the background worker.

        ``schemas=None`` defers resolution to the worker, which lists
        every database via its own dedicated connection — the main
        thread's ``sqlexecute`` must not be used here since the worker
        would race with the REPL.
        """
        self.stop()
        queue: list[str] | None = None if schemas is None else list(schemas)
        self._cancel = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(queue,),
            name='schema_prefetcher',
            daemon=True,
        )
        self._thread.start()
        self._invalidate_app()

    def _run(self, schemas: list[str] | None) -> None:
        executor: SQLExecute | None = None
        try:
            executor = self._make_executor()
        except Exception as e:  # pragma: no cover - defensive
            _logger.error('schema prefetch could not open connection: %r', e)
            self._invalidate_app()
            return
        try:
            if schemas is None:
                try:
                    schemas = list(executor.databases())
                except Exception as e:
                    _logger.error('failed to list databases for prefetch: %r', e)
                    return
            current = self._current_schema()
            existing = set(self.mycli.completer.dbmetadata.get('tables', {}).keys())
            queue = [s for s in schemas if s and s != current and s not in self._loaded and s not in existing]
            for schema in queue:
                if self._cancel.is_set():
                    return
                try:
                    self._prefetch_one(executor, schema)
                    self._loaded.add(schema)
                except Exception as e:
                    _logger.error('prefetch failed for schema %r: %r', schema, e)
        finally:
            try:
                executor.close()
            except Exception:  # pragma: no cover - defensive
                pass
            self._invalidate_app()

    def _prefetch_one(self, executor: SQLExecute, schema: str) -> None:
        _logger.debug('prefetching schema %r', schema)
        table_rows = list(executor.table_columns(schema=schema))
        fk_rows = list(executor.foreign_keys(schema=schema))
        enum_rows = list(executor.enum_values(schema=schema))
        func_rows = list(executor.functions(schema=schema))
        proc_rows = list(executor.procedures(schema=schema))

        # Use the live completer's escape logic so keys match what the
        # completion engine computes when parsing user input.
        completer = self.mycli.completer
        table_columns: dict[str, list[str]] = {}
        for table, column in table_rows:
            esc_table = completer.escape_name(table)
            esc_col = completer.escape_name(column)
            cols = table_columns.setdefault(esc_table, ['*'])
            cols.append(esc_col)

        fk_tables: dict[str, set[str]] = {}
        fk_relations: list[tuple[str, str, str, str]] = []
        for table, col, ref_table, ref_col in fk_rows:
            esc_table = completer.escape_name(table)
            esc_col = completer.escape_name(col)
            esc_ref_table = completer.escape_name(ref_table)
            esc_ref_col = completer.escape_name(ref_col)
            fk_tables.setdefault(esc_table, set()).add(esc_ref_table)
            fk_tables.setdefault(esc_ref_table, set()).add(esc_table)
            fk_relations.append((esc_table, esc_col, esc_ref_table, esc_ref_col))
        fk_payload: dict[str, Any] = {'tables': fk_tables, 'relations': fk_relations}

        enum_values: dict[str, dict[str, list[str]]] = {}
        for table, column, values in enum_rows:
            esc_table = completer.escape_name(table)
            esc_col = completer.escape_name(column)
            enum_values.setdefault(esc_table, {})[esc_col] = list(values)

        functions: dict[str, None] = {}
        for row in func_rows:
            if not row or not row[0]:
                continue
            functions[completer.escape_name(row[0])] = None

        procedures: dict[str, None] = {}
        for row in proc_rows:
            if not row or not row[0]:
                continue
            procedures[completer.escape_name(row[0])] = None

        with self.mycli._completer_lock:
            live_completer: 'SQLCompleter' = self.mycli.completer
            live_completer.load_schema_metadata(
                schema=schema,
                table_columns=table_columns,
                foreign_keys=fk_payload,
                enum_values=enum_values,
                functions=functions,
                procedures=procedures,
            )
        self._invalidate_app()

    def _current_schema(self) -> str | None:
        sqlexecute = self.mycli.sqlexecute
        return sqlexecute.dbname if sqlexecute is not None else None

    def _make_executor(self) -> SQLExecute:
        sqlexecute = self.mycli.sqlexecute
        assert sqlexecute is not None
        return SQLExecute(
            sqlexecute.dbname,
            sqlexecute.user,
            sqlexecute.password,
            sqlexecute.host,
            sqlexecute.port,
            sqlexecute.socket,
            sqlexecute.character_set,
            sqlexecute.local_infile,
            sqlexecute.ssl,
            sqlexecute.ssh_user,
            sqlexecute.ssh_host,
            sqlexecute.ssh_port,
            sqlexecute.ssh_password,
            sqlexecute.ssh_key_filename,
        )

    def _invalidate_app(self) -> None:
        prompt_session = getattr(self.mycli, 'prompt_session', None)
        if prompt_session is None:
            return
        try:
            prompt_session.app.invalidate()
        except Exception:  # pragma: no cover - defensive
            pass

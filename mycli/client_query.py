from __future__ import annotations

from typing import IO, TYPE_CHECKING, Any

import click
from pymysql.cursors import Cursor

from mycli.packages import special
from mycli.packages.sqlresult import SQLResult
from mycli.sqlcompleter import SQLCompleter


class ClientQueryMixin:
    if TYPE_CHECKING:
        schema_prefetcher: Any
        sqlexecute: Any
        _completer_lock: Any
        completer: Any
        completion_refresher: Any
        smart_completion: bool
        main_formatter: Any
        redirect_formatter: Any
        explorer_formatter: Any
        prompt_session: Any
        null_string: str | None
        numeric_alignment: str | None
        binary_display: str | None
        query_history: list[Any]
        checkpoint: IO | None

        def log_query(self, query: str) -> None: ...
        def log_output(self, output: str) -> None: ...
        def format_sqlresult(self, *args: Any, **kwargs: Any) -> Any: ...

    def refresh_completions(self, reset: bool = False) -> list[SQLResult]:
        # Cancel any in-flight schema prefetch before the completer is
        # replaced.  Loaded-schema bookkeeping is intentionally preserved
        # so switching between already-loaded schemas does not re-fetch.
        self.schema_prefetcher.stop()

        assert self.sqlexecute is not None
        if reset:
            # Update the active completer's current-schema pointer right
            # away so unqualified completions reflect a schema switch
            # even before the background refresh finishes.
            with self._completer_lock:
                self.completer.set_dbname(self.sqlexecute.dbname)
        self.completion_refresher.refresh(
            self.sqlexecute,
            self._on_completions_refreshed,
            {
                "smart_completion": self.smart_completion,
                "supported_formats": self.main_formatter.supported_formats,
                "keyword_casing": self.completer.keyword_casing,
            },
        )

        return [SQLResult(status="Auto-completion refresh started in the background.")]

    def _on_completions_refreshed(self, new_completer: SQLCompleter) -> None:
        """Swap the completer object in cli with the newly created completer."""
        with self._completer_lock:
            new_completer.copy_other_schemas_from(self.completer, exclude=new_completer.dbname)
            self.completer = new_completer

        if self.prompt_session:
            # After refreshing, redraw the CLI to clear the statusbar
            # "Refreshing completions..." indicator
            self.prompt_session.app.invalidate()

        # Kick off background prefetch for any extra schemas configured
        # via ``prefetch_schemas_mode`` so users get cross-schema completions.
        self.schema_prefetcher.start_configured()

    def run_query(
        self,
        query: str,
        checkpoint: str | None = None,
        new_line: bool = True,
    ) -> None:
        """Runs *query*."""
        assert self.sqlexecute is not None
        self.log_query(query)
        if checkpoint and not self.checkpoint:
            self.checkpoint = click.open_file(checkpoint, mode='a')
        results = self.sqlexecute.run(query)
        for result in results:
            self.main_formatter.query = query
            self.redirect_formatter.query = query
            self.explorer_formatter.query = query
            output = self.format_sqlresult(
                result,
                is_expanded=special.is_expanded_output(),
                is_redirected=special.is_redirected(),
                null_string=self.null_string,
                numeric_alignment=self.numeric_alignment,
                binary_display=self.binary_display,
            )
            for line in output:
                self.log_output(line)
                click.echo(line, nl=new_line)

            # get and display warnings if enabled
            if special.is_show_warnings_enabled() and isinstance(result.rows, Cursor) and result.rows.warning_count > 0:
                warnings = self.sqlexecute.run("SHOW WARNINGS")
                for warning in warnings:
                    output = self.format_sqlresult(
                        warning,
                        is_expanded=special.is_expanded_output(),
                        is_redirected=special.is_redirected(),
                        null_string=self.null_string,
                        numeric_alignment=self.numeric_alignment,
                        binary_display=self.binary_display,
                        is_warnings_style=True,
                    )
                    for line in output:
                        click.echo(line, nl=new_line)
        if self.checkpoint:
            self.checkpoint.write(query.rstrip('\n') + '\n')
            self.checkpoint.flush()

    def get_last_query(self) -> str | None:
        """Get the last query executed or None."""
        return self.query_history[-1][0] if self.query_history else None

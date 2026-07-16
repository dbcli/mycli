from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import TextIOWrapper
import itertools
import os
import shlex
import shutil
from typing import Generator, Literal, Protocol

from cli_helpers.tabular_output import TabularOutputFormatter, preprocessors
from cli_helpers.tabular_output.output_formatter import MISSING_VALUE as DEFAULT_MISSING_VALUE
from cli_helpers.utils import strip_ansi
import click
from configobj import ConfigObj
import prompt_toolkit
from prompt_toolkit.formatted_text import (
    ANSI,
    HTML,
    AnyFormattedText,
    FormattedText,
    to_formatted_text,
    to_plain_text,
)
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles.style import _MergedStyle
from pygments.style import Style as PygmentsStyle
from pymysql.cursors import Cursor

from mycli.compat import WIN
from mycli.constants import DEFAULT_HEIGHT, DEFAULT_WIDTH
import mycli.main_modes.repl as repl_mode
from mycli.packages import special
from mycli.packages.sqlresult import SQLResult
from mycli.packages.tabular_output import sql_format
from mycli.sqlexecute import FIELD_TYPES


class MyCliState(Protocol):
    # Provided by OutputMixin itself; declared so cross-method calls type-check.
    def log_output(self, output: str | AnyFormattedText) -> None: ...
    def get_output_margin(self, status: str | None = None) -> int: ...
    def get_reserved_space(self) -> int: ...


class OutputMixin(MyCliState):
    prompt_lines: int
    multiline_continuation_char: str
    multiplex_pane_title_format: str
    multiplex_window_title_format: str
    terminal_tab_title_format: str
    terminal_window_title_format: str
    toolbar_format: str
    explorer_formatter: TabularOutputFormatter
    explorer_command: str
    explorer_trim_footer: bool
    redirect_formatter: TabularOutputFormatter
    config: ConfigObj
    logfile: TextIOWrapper | Literal[False] | None
    prompt_session: PromptSession | None
    prompt_format: str
    explicit_pager: bool
    ptoolkit_style: _MergedStyle
    helpers_style: PygmentsStyle
    helpers_warnings_style: PygmentsStyle
    main_formatter: TabularOutputFormatter

    def output_timing(self, timing: str, is_warnings_style: bool = False) -> None:
        self.log_output(timing)
        add_style = 'class:warnings.timing' if is_warnings_style else 'class:output.timing'
        formatted_timing = FormattedText([('', timing)])
        styled_timing = to_formatted_text(formatted_timing, style=add_style)
        prompt_toolkit.print_formatted_text(styled_timing, style=self.ptoolkit_style)

    def log_query(self, query: str) -> None:
        if isinstance(self.logfile, TextIOWrapper):
            self.logfile.write(f"\n# {datetime.now()}\n")
            self.logfile.write(query)
            self.logfile.write("\n")

    def log_output(self, output: str | AnyFormattedText) -> None:
        """Log the output in the audit log, if it's enabled."""
        if isinstance(output, (ANSI, HTML, FormattedText)):
            output = to_plain_text(output)
        if isinstance(self.logfile, TextIOWrapper):
            click.echo(output, file=self.logfile)

    def echo(self, s: str, **kwargs) -> None:
        """Print a message to stdout."""
        self.log_output(s)
        click.secho(s, **kwargs)

    def get_output_margin(self, status: str | None = None) -> int:
        """Get the output margin for prompt, footer, timing, and status."""
        if not self.prompt_lines:
            if self.prompt_session and self.prompt_session.app:
                render_counter = self.prompt_session.app.render_counter
            else:
                render_counter = 0
            prompt_string = repl_mode.render_prompt_string(self, self.prompt_format, render_counter)
            self.prompt_lines = to_plain_text(prompt_string).count('\n') + 1
        margin = self.get_reserved_space() + self.prompt_lines
        if special.is_timing_enabled():
            margin += 1
        if status:
            margin += 1 + status.count("\n")

        return margin

    def output(
        self,
        output: itertools.chain[str],
        result: SQLResult,
        is_warnings_style: bool = False,
    ) -> None:
        """Output text to stdout or a pager command."""
        if output:
            if self.prompt_session is not None:
                size = self.prompt_session.output.get_size()
                size_columns = size.columns
                size_rows = size.rows
            else:
                size_columns = DEFAULT_WIDTH
                size_rows = DEFAULT_HEIGHT

            margin = self.get_output_margin(result.status_plain)

            fits = True
            buf = []
            output_via_pager = self.explicit_pager and special.is_pager_enabled()
            for i, line in enumerate(output, 1):
                self.log_output(line)
                special.write_tee(line)
                special.write_once(line)
                special.write_pipe_once(line)

                if special.is_redirected():
                    pass
                elif special.is_explorer_output():
                    buf.append(line)
                elif fits or output_via_pager:
                    buf.append(line)
                    if len(line) > size_columns or i > (size_rows - margin):
                        fits = False
                        if not self.explicit_pager and special.is_pager_enabled():
                            output_via_pager = True

                        if not output_via_pager:
                            for buf_line in buf:
                                click.secho(buf_line)
                            buf = []
                else:
                    click.secho(line)

            if buf:

                def newlinewrapper(text: list[str]) -> Generator[str, None, None]:
                    for line in text:
                        yield line + "\n"

                if special.is_explorer_output():
                    if self.explorer_exists() or not self.explorer_command:
                        old_pager = os.environ.get('PAGER')
                        os.environ['PAGER'] = self.explorer_command or old_pager or 'less'
                        click.echo_via_pager(newlinewrapper(buf))
                        if old_pager:
                            os.environ['PAGER'] = old_pager
                        else:
                            del os.environ['PAGER']
                    else:
                        click.secho(f'Configured explorer command not found: {self.explorer_command}.', err=True, fg='red')
                elif output_via_pager:
                    click.echo_via_pager(newlinewrapper(buf))
                else:
                    for line in buf:
                        click.secho(line)

        if result.status:
            self.log_output(result.status_plain)
            add_style = 'class:warnings.status' if is_warnings_style else 'class:output.status'
            if isinstance(result.status, FormattedText):
                status = result.status
            else:
                status = FormattedText([('', result.status_plain)])
            styled_status = to_formatted_text(status, style=add_style)
            prompt_toolkit.print_formatted_text(styled_status, style=self.ptoolkit_style)

    def configure_pager(self) -> None:
        if not os.environ.get("LESS"):
            os.environ["LESS"] = "-RXF"

        config_pager = self.config["main"]["pager"]

        if WIN and config_pager == 'less' and not shutil.which(config_pager):
            config_pager = 'more'

        if config_pager:
            special.set_pager(config_pager)
            self.explicit_pager = True
        else:
            self.explicit_pager = False

        if not self.config["main"].as_bool("enable_pager"):
            special.disable_pager()

    def explorer_exists(self) -> bool:
        if cmd := shlex.split(self.explorer_command or ''):
            return bool(shutil.which(cmd[0]))
        return False

    def format_sqlresult(
        self,
        result,
        is_expanded: bool = False,
        is_redirected: bool = False,
        null_string: str | None = None,
        numeric_alignment: str = 'right',
        binary_display: str | None = None,
        max_width: int | None = None,
        is_warnings_style: bool = False,
    ) -> itertools.chain[str]:
        if is_redirected:
            use_formatter = self.redirect_formatter
        elif special.is_explorer_output():
            use_formatter = self.explorer_formatter
        else:
            use_formatter = self.main_formatter

        is_expanded = is_expanded or use_formatter.format_name == "vertical"
        output: itertools.chain[str] = itertools.chain()

        output_kwargs = {
            "dialect": "unix",
            "disable_numparse": True,
            "preserve_whitespace": True,
            "style": self.helpers_warnings_style if is_warnings_style else self.helpers_style,
        }
        default_kwargs = use_formatter._output_formats[use_formatter.format_name].formatter_args

        if null_string is not None and default_kwargs.get('missing_value') == DEFAULT_MISSING_VALUE:
            output_kwargs['missing_value'] = null_string

        if use_formatter.format_name not in sql_format.supported_formats and binary_display != 'utf8':
            output_kwargs["preprocessors"] = (preprocessors.convert_to_undecoded_string,)

        if result.preamble:
            output = itertools.chain(output, [result.preamble])

        if result.header or (result.rows and result.preamble):
            column_types = None
            colalign = None
            if isinstance(result.rows, Cursor):

                def get_col_type(col) -> type:
                    col_type = FIELD_TYPES.get(col[1], str)
                    return col_type if type(col_type) is type else str

                if result.rows.rowcount > 0:
                    column_types = [get_col_type(tup) for tup in result.rows.description]
                    colalign = [numeric_alignment if x in (int, float, Decimal) else 'left' for x in column_types]
                else:
                    column_types, colalign = [], []

            if max_width is not None and isinstance(result.rows, Cursor):
                result_rows = list(result.rows)
            else:
                result_rows = result.rows

            formatted = use_formatter.format_output(
                result_rows,
                result.header or [],
                format_name="vertical" if is_expanded else None,
                column_types=column_types,
                colalign=colalign,
                **output_kwargs,
            )

            if isinstance(formatted, str):
                formatted = formatted.splitlines()

            if special.is_explorer_output() and self.explorer_trim_footer:
                formatted = list(formatted)
                formatted.pop()

            formatted = iter(formatted)

            if not is_expanded and max_width and result.header and result_rows:
                first_line = next(formatted)
                if len(strip_ansi(first_line)) > max_width:
                    formatted = use_formatter.format_output(
                        result_rows,
                        result.header,
                        format_name="vertical",
                        column_types=column_types,
                        **output_kwargs,
                    )
                    if isinstance(formatted, str):
                        formatted = iter(formatted.splitlines())
                else:
                    formatted = itertools.chain([first_line], formatted)

            output = itertools.chain(output, formatted)

        if result.postamble:
            output = itertools.chain(output, [result.postamble])

        return output

    def get_reserved_space(self) -> int:
        """Get the number of lines to reserve for the completion menu."""
        reserved_space_ratio = 0.45
        max_reserved_space = 8
        _, height = shutil.get_terminal_size()
        return min(int(round(height * reserved_space_ratio)), max_reserved_space)

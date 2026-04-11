from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import functools
from functools import partial
from importlib import resources
import os
import random
import re
import subprocess
import sys
import time
import traceback
from typing import TYPE_CHECKING, Any, Generator

import click
import prompt_toolkit
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, ThreadedAutoSuggest
from prompt_toolkit.completion import DynamicCompleter
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.filters import Condition, has_focus, is_done
from prompt_toolkit.formatted_text import (
    ANSI,
)
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.processors import ConditionalProcessor, HighlightMatchingBracketProcessor
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.shortcuts import CompleteStyle, PromptSession
import pymysql
from pymysql.cursors import Cursor

import mycli as mycli_package
from mycli.clibuffer import cli_is_multiline
from mycli.clistyle import style_factory_ptoolkit
from mycli.clitoolbar import create_toolbar_tokens_func
from mycli.constants import (
    DEFAULT_HOST,
    DEFAULT_WIDTH,
    ER_MUST_CHANGE_PASSWORD,
    HOME_URL,
    ISSUES_URL,
)
from mycli.key_bindings import mycli_bindings
from mycli.lexer import MyCliLexer
from mycli.packages import special
from mycli.packages.filepaths import dir_path_exists
from mycli.packages.hybrid_redirection import get_redirect_components, is_redirect_command
from mycli.packages.interactive_utils import confirm, confirm_destructive_query
from mycli.packages.key_binding_utils import (
    handle_clip_command,
    handle_editor_command,
)
from mycli.packages.ptoolkit.history import FileHistoryWithTimestamp
from mycli.packages.special.utils import format_uptime, get_ssl_version, get_uptime, get_warning_count
from mycli.packages.sql_utils import (
    extract_new_password,
    is_dropping_database,
    is_mutating,
    is_password_change,
    is_sandbox_allowed,
    is_select,
    need_completion_refresh,
    need_completion_reset,
)
from mycli.packages.sqlresult import SQLResult
from mycli.packages.string_utils import sanitize_terminal_title
from mycli.sqlexecute import SQLExecute
from mycli.types import Query

if TYPE_CHECKING:
    from prompt_toolkit.formatted_text import AnyFormattedText

    from mycli.main import MyCli


SUPPORT_INFO = f"Home: {HOME_URL}\nBug tracker: {ISSUES_URL}"
MIN_COMPLETION_TRIGGER = 1
_PROMPT_TARGETS: dict[int, 'MyCli'] = {}


@dataclass(slots=True)
class ReplState:
    iterations: int = 0
    mutating: bool = False


@Condition
def complete_while_typing_filter() -> bool:
    """Whether enough characters have been typed to trigger completion.

    Written in a verbose way, with a string slice, for efficiency."""
    if MIN_COMPLETION_TRIGGER <= 1:
        return True
    app = get_app()
    text = app.current_buffer.text.lstrip()
    text_len = len(text)
    if text_len < MIN_COMPLETION_TRIGGER:
        return False
    last_word = text[-MIN_COMPLETION_TRIGGER:]
    if len(last_word) == text_len:
        return text_len >= MIN_COMPLETION_TRIGGER
    if text[:6].lower() in ['source', r'\.']:
        # Different word characters for paths; see comment below.
        # In fact, it might be nice if paths had a different threshold.
        return not bool(re.search(r'[\s!-,:-@\[-^\{\}-]', last_word))
    else:
        # This is "whitespace and all punctuation except underscore and backtick"
        # acting as word breaks, but it would be neat if we could complete differently
        # when inside a backtick, accepting all legal characters towards the trigger
        # limit. We would have to parse the statement, or at least go back more
        # characters, costing performance. This still works within a backtick! So
        # long as there are three trailing non-punctuation characters.
        return not bool(re.search(r'[\s!-/:-@\[-^\{-~]', last_word))


def _create_history(mycli: 'MyCli') -> FileHistoryWithTimestamp | None:
    history_file = os.path.expanduser(os.environ.get('MYCLI_HISTFILE', mycli.config.get('history_file', '~/.mycli-history')))
    if dir_path_exists(history_file):
        return FileHistoryWithTimestamp(history_file)

    mycli.echo(
        f'Error: Unable to open the history file "{history_file}". Your query history will not be saved.',
        err=True,
        fg='red',
    )
    return None


def _show_startup_banner(
    mycli: 'MyCli',
    sqlexecute: SQLExecute,
) -> None:
    if mycli.less_chatty:
        return

    if sqlexecute.server_info is not None:
        print(sqlexecute.server_info)
    print('mycli', mycli_package.__version__)
    print(SUPPORT_INFO)
    if random.random() <= 0.25:
        print('Thanks to the sponsor —', _sponsors_picker())
    elif random.random() <= 0.5:
        print('Thanks to the contributor —', _contributors_picker())
    else:
        print('Tip —', _tips_picker())


def set_all_external_titles(mycli: 'MyCli') -> None:
    set_external_terminal_tab_title(mycli)
    set_external_terminal_window_title(mycli)
    set_external_multiplex_window_title(mycli)
    set_external_multiplex_pane_title(mycli)


def set_external_terminal_tab_title(mycli: 'MyCli') -> None:
    if not mycli.terminal_tab_title_format:
        return
    if not mycli.prompt_session:
        return
    if not sys.stderr.isatty():
        return
    title = sanitize_terminal_title(get_prompt(mycli, mycli.terminal_tab_title_format, mycli.prompt_session.app.render_counter))
    print(f'\x1b]1;{title}\a', file=sys.stderr, end='')
    sys.stderr.flush()


def set_external_terminal_window_title(mycli: 'MyCli') -> None:
    if not mycli.terminal_window_title_format:
        return
    if not mycli.prompt_session:
        return
    if not sys.stderr.isatty():
        return
    title = sanitize_terminal_title(get_prompt(mycli, mycli.terminal_window_title_format, mycli.prompt_session.app.render_counter))
    print(f'\x1b]2;{title}\a', file=sys.stderr, end='')
    sys.stderr.flush()


def set_external_multiplex_window_title(mycli: 'MyCli') -> None:
    if not mycli.multiplex_window_title_format:
        return
    if not os.getenv('TMUX'):
        return
    if not mycli.prompt_session:
        return
    title = sanitize_terminal_title(get_prompt(mycli, mycli.multiplex_window_title_format, mycli.prompt_session.app.render_counter))
    try:
        subprocess.run(
            ['tmux', 'rename-window', title],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


def set_external_multiplex_pane_title(mycli: 'MyCli') -> None:
    if not mycli.multiplex_pane_title_format:
        return
    if not os.getenv('TMUX'):
        return
    if not mycli.prompt_session:
        return
    if not sys.stderr.isatty():
        return
    title = sanitize_terminal_title(get_prompt(mycli, mycli.multiplex_pane_title_format, mycli.prompt_session.app.render_counter))
    print(f'\x1b]2;{title}\x1b\\', file=sys.stderr, end='')
    sys.stderr.flush()


def get_custom_toolbar(
    mycli: 'MyCli',
    toolbar_format: str,
) -> ANSI:
    if not mycli.prompt_session:
        return ANSI('')
    if not mycli.prompt_session.app:
        return ANSI('')
    if mycli.prompt_session.app.current_buffer.text:
        return mycli.last_custom_toolbar_message
    toolbar = get_prompt(mycli, toolbar_format, mycli.prompt_session.app.render_counter)
    toolbar = toolbar.replace('\\x1b', '\x1b')
    mycli.last_custom_toolbar_message = ANSI(toolbar)
    return mycli.last_custom_toolbar_message


@functools.lru_cache(maxsize=256)
def get_prompt(
    mycli: 'MyCli',
    string: str,
    _render_counter: int,
) -> str:
    sqlexecute = mycli.sqlexecute
    assert sqlexecute is not None
    if mycli.login_path and mycli.login_path_as_host:
        prompt_host = mycli.login_path
    elif sqlexecute.host is not None:
        prompt_host = sqlexecute.host
    else:
        prompt_host = DEFAULT_HOST
    short_prompt_host, _, _ = prompt_host.partition('.')
    if re.match(r'^[\d\.]+$', short_prompt_host):
        short_prompt_host = prompt_host
    now = datetime.now()
    backslash_placeholder = '\ufffc_backslash'
    string = string.replace('\\\\', backslash_placeholder)
    string = string.replace('\\u', sqlexecute.user or '(none)')
    string = string.replace('\\h', prompt_host or '(none)')
    string = string.replace('\\H', short_prompt_host or '(none)')
    string = string.replace('\\d', sqlexecute.dbname or '(none)')
    species_name = sqlexecute.server_info.species.name if sqlexecute.server_info and sqlexecute.server_info.species else 'MySQL'
    string = string.replace('\\t', species_name)
    string = string.replace('\\n', '\n')
    string = string.replace('\\D', now.strftime('%a %b %d %H:%M:%S %Y'))
    string = string.replace('\\m', now.strftime('%M'))
    string = string.replace('\\P', now.strftime('%p'))
    string = string.replace('\\R', now.strftime('%H'))
    string = string.replace('\\r', now.strftime('%I'))
    string = string.replace('\\s', now.strftime('%S'))
    string = string.replace('\\p', str(sqlexecute.port))
    string = string.replace('\\j', os.path.basename(sqlexecute.socket or '(none)'))
    string = string.replace('\\J', sqlexecute.socket or '(none)')
    string = string.replace('\\k', os.path.basename(sqlexecute.socket or str(sqlexecute.port)))
    string = string.replace('\\K', sqlexecute.socket or str(sqlexecute.port))
    string = string.replace('\\A', mycli.dsn_alias or '(none)')
    string = string.replace('\\_', ' ')
    string = string.replace(backslash_placeholder, '\\')

    if hasattr(sqlexecute, 'conn') and sqlexecute.conn is not None:
        if '\\y' in string:
            with sqlexecute.conn.cursor() as cur:
                string = string.replace('\\y', str(get_uptime(cur)) or '(none)')
        if '\\Y' in string:
            with sqlexecute.conn.cursor() as cur:
                string = string.replace('\\Y', format_uptime(str(get_uptime(cur))) or '(none)')
    else:
        string = string.replace('\\y', '(none)')
        string = string.replace('\\Y', '(none)')

    if hasattr(sqlexecute, 'conn') and sqlexecute.conn is not None:
        if '\\T' in string:
            with sqlexecute.conn.cursor() as cur:
                string = string.replace('\\T', get_ssl_version(cur) or '(none)')
    else:
        string = string.replace('\\T', '(none)')

    if hasattr(sqlexecute, 'conn') and sqlexecute.conn is not None:
        if '\\w' in string:
            with sqlexecute.conn.cursor() as cur:
                string = string.replace('\\w', str(get_warning_count(cur) or '(none)'))
    else:
        string = string.replace('\\w', '(none)')
    if hasattr(sqlexecute, 'conn') and sqlexecute.conn is not None:
        if '\\W' in string:
            with sqlexecute.conn.cursor() as cur:
                string = string.replace('\\W', str(get_warning_count(cur) or ''))
    else:
        string = string.replace('\\W', '')

    return string


def _get_prompt_message(
    mycli: 'MyCli',
    app: prompt_toolkit.application.application.Application,
) -> ANSI:
    if app.current_buffer.text:
        return mycli.last_prompt_message

    prompt = get_prompt(mycli, mycli.prompt_format, app.render_counter)
    if mycli.prompt_format == mycli.default_prompt and len(prompt) > mycli.max_len_prompt:
        prompt = get_prompt(mycli, mycli.default_prompt_splitln, app.render_counter)
        mycli.prompt_lines = prompt.count('\n') + 1
    prompt = prompt.replace('\\x1b', '\x1b')
    if not mycli.prompt_lines:
        mycli.prompt_lines = prompt.count('\n') + 1
    mycli.last_prompt_message = ANSI(prompt)
    return mycli.last_prompt_message


def _get_continuation(
    mycli: 'MyCli',
    width: int,
    _two: int,
    _three: int,
) -> AnyFormattedText:
    if mycli.multiline_continuation_char == '':
        continuation = ''
    elif mycli.multiline_continuation_char:
        left_padding = width - len(mycli.multiline_continuation_char)
        continuation = ' ' * max((left_padding - 1), 0) + mycli.multiline_continuation_char + ' '
    else:
        continuation = ' '
    return [('class:continuation', continuation)]


def _output_results(
    mycli: 'MyCli',
    state: ReplState,
    results: Generator[SQLResult],
    start: float,
) -> None:
    sqlexecute = mycli.sqlexecute
    assert sqlexecute is not None

    result_count = 0
    watch_count = 0
    for result in results:
        mycli.logger.debug('preamble: %r', result.preamble)
        mycli.logger.debug('header: %r', result.header)
        mycli.logger.debug('rows: %r', result.rows)
        mycli.logger.debug('status: %r', result.status)
        mycli.logger.debug('command: %r', result.command)
        threshold = 1000
        if result.command is not None and result.command['name'] == 'watch':
            if watch_count > 0:
                try:
                    watch_seconds = float(result.command['seconds'])
                    start += watch_seconds
                except ValueError as e:
                    mycli.echo(f'Invalid watch sleep time provided ({e}).', err=True, fg='red')
                    sys.exit(1)
            else:
                watch_count += 1

        if is_select(result.status_plain) and isinstance(result.rows, Cursor) and result.rows.rowcount > threshold:
            mycli.echo(
                f'The result set has more than {threshold} rows.',
                fg='red',
            )
            if not confirm('Do you want to continue?'):
                mycli.echo('Aborted!', err=True, fg='red')
                break

        if mycli.auto_vertical_output:
            if mycli.prompt_session is not None:
                max_width = mycli.prompt_session.output.get_size().columns
            else:
                max_width = DEFAULT_WIDTH
        else:
            max_width = None

        formatted = mycli.format_sqlresult(
            result,
            is_expanded=special.is_expanded_output(),
            is_redirected=special.is_redirected(),
            null_string=mycli.null_string,
            numeric_alignment=mycli.numeric_alignment,
            binary_display=mycli.binary_display,
            max_width=max_width,
        )

        duration = time.time() - start
        try:
            if result_count > 0:
                mycli.echo('')
            try:
                mycli.output(formatted, result)
            except KeyboardInterrupt:
                pass
            if mycli.beep_after_seconds > 0 and duration >= mycli.beep_after_seconds:
                assert mycli.prompt_session is not None
                mycli.prompt_session.output.bell()
            if special.is_timing_enabled():
                mycli.output_timing(f'Time: {duration:0.03f}s')
        except KeyboardInterrupt:
            pass

        start = time.time()
        result_count += 1
        state.mutating = state.mutating or is_mutating(result.status_plain)

        if special.is_show_warnings_enabled() and isinstance(result.rows, Cursor) and result.rows.warning_count > 0:
            warnings = sqlexecute.run('SHOW WARNINGS')
            warnings_duration = time.time() - start
            saw_warning = False
            for warning in warnings:
                saw_warning = True
                formatted = mycli.format_sqlresult(
                    warning,
                    is_expanded=special.is_expanded_output(),
                    is_redirected=special.is_redirected(),
                    null_string=mycli.null_string,
                    numeric_alignment=mycli.numeric_alignment,
                    binary_display=mycli.binary_display,
                    max_width=max_width,
                    is_warnings_style=True,
                )
                mycli.echo('')
                mycli.output(formatted, warning, is_warnings_style=True)

            if saw_warning and special.is_timing_enabled():
                mycli.output_timing(f'Time: {warnings_duration:0.03f}s', is_warnings_style=True)


def _keepalive_hook(
    mycli: 'MyCli',
    _context: Any,
) -> None:
    if mycli.keepalive_ticks is None:
        return
    if mycli.keepalive_ticks < 1:
        return

    mycli._keepalive_counter += 1
    if mycli._keepalive_counter > mycli.keepalive_ticks:
        mycli._keepalive_counter = 0
        mycli.logger.debug('keepalive ping')
        try:
            assert mycli.sqlexecute is not None
            assert mycli.sqlexecute.conn is not None
            mycli.sqlexecute.conn.ping(reconnect=False)
        except Exception as e:
            mycli.logger.debug('keepalive ping error %r', e)


def _build_prompt_session(
    mycli: 'MyCli',
    state: ReplState,
    history: FileHistoryWithTimestamp | None,
    key_bindings: KeyBindings,
) -> None:
    if mycli.toolbar_format.lower() == 'none':
        get_toolbar_tokens = None
    else:
        get_toolbar_tokens = create_toolbar_tokens_func(
            mycli,
            lambda: state.iterations == 0,
            mycli.toolbar_format,
            partial(get_custom_toolbar, mycli),
        )

    if mycli.wider_completion_menu:
        complete_style = CompleteStyle.MULTI_COLUMN
    else:
        complete_style = CompleteStyle.COLUMN

    with mycli._completer_lock:
        if mycli.key_bindings == 'vi':
            editing_mode = EditingMode.VI
        else:
            editing_mode = EditingMode.EMACS

        mycli.prompt_session = PromptSession(
            color_depth=ColorDepth.DEPTH_24_BIT if 'truecolor' in os.getenv('COLORTERM', '').lower() else None,
            lexer=PygmentsLexer(MyCliLexer),
            reserve_space_for_menu=mycli.get_reserved_space(),
            prompt_continuation=lambda width, two, three: _get_continuation(mycli, width, two, three),
            bottom_toolbar=get_toolbar_tokens,
            complete_style=complete_style,
            input_processors=[
                ConditionalProcessor(
                    processor=HighlightMatchingBracketProcessor(chars='[](){}'),
                    filter=has_focus(DEFAULT_BUFFER) & ~is_done,
                )
            ],
            tempfile_suffix='.sql',
            completer=DynamicCompleter(lambda: mycli.completer),
            complete_in_thread=True,
            history=history,
            auto_suggest=ThreadedAutoSuggest(AutoSuggestFromHistory()),
            complete_while_typing=complete_while_typing_filter,
            multiline=cli_is_multiline(mycli),
            style=style_factory_ptoolkit(mycli.syntax_style, mycli.cli_style),
            include_default_pygments_style=False,
            key_bindings=key_bindings,
            enable_open_in_editor=True,
            enable_system_prompt=True,
            enable_suspend=True,
            editing_mode=editing_mode,
            search_ignore_case=True,
        )

        if mycli.key_bindings == 'vi':
            mycli.prompt_session.app.ttimeoutlen = mycli.vi_ttimeoutlen
        else:
            mycli.prompt_session.app.ttimeoutlen = mycli.emacs_ttimeoutlen


def _one_iteration(
    mycli: 'MyCli',
    state: ReplState,
    text: str | None = None,
) -> None:
    sqlexecute = mycli.sqlexecute
    assert sqlexecute is not None

    inputhook = partial(_keepalive_hook, mycli) if mycli.keepalive_ticks and mycli.keepalive_ticks >= 1 else None

    if text is None:
        try:
            assert mycli.prompt_session is not None
            loaded_message_fn = partial(_get_prompt_message, mycli, mycli.prompt_session.app)
            text = mycli.prompt_session.prompt(
                inputhook=inputhook,
                message=loaded_message_fn,
            )
        except KeyboardInterrupt:
            return

        special.set_expanded_output(False)
        special.set_forced_horizontal_output(False)

        try:
            text = handle_editor_command(
                mycli,
                text,
                inputhook,
                loaded_message_fn,
            )
        except RuntimeError as e:
            mycli.logger.error('sql: %r, error: %r', text, e)
            mycli.logger.error('traceback: %r', traceback.format_exc())
            mycli.echo(str(e), err=True, fg='red')
            return

        try:
            if handle_clip_command(mycli, text):
                return
        except RuntimeError as e:
            mycli.logger.error('sql: %r, error: %r', text, e)
            mycli.logger.error('traceback: %r', traceback.format_exc())
            mycli.echo(str(e), err=True, fg='red')
            return

        while special.is_llm_command(text):
            start = time.time()
            try:
                assert sqlexecute.conn is not None
                cur = sqlexecute.conn.cursor()
                context, sql, duration = special.handle_llm(
                    text,
                    cur,
                    sqlexecute.dbname or '',
                    mycli.llm_prompt_field_truncate,
                    mycli.llm_prompt_section_truncate,
                )
                if context:
                    click.echo('LLM Response:')
                    click.echo(context)
                    click.echo('---')
                if special.is_timing_enabled():
                    mycli.output_timing(f'Time: {duration:.2f} seconds')
                assert mycli.prompt_session is not None
                text = mycli.prompt_session.prompt(
                    default=sql or '',
                    inputhook=inputhook,
                    message=loaded_message_fn,
                )
            except KeyboardInterrupt:
                return
            except special.FinishIteration as e:
                if e.results:
                    _output_results(mycli, state, e.results, start)
                return
            except RuntimeError as e:
                mycli.logger.error('sql: %r, error: %r', text, e)
                mycli.logger.error('traceback: %r', traceback.format_exc())
                mycli.echo(str(e), err=True, fg='red')
                return

    text = text.strip()
    if not text:
        return

    if is_redirect_command(text):
        sql_part, command_part, file_operator_part, file_part = get_redirect_components(text)
        text = sql_part or ''
        try:
            special.set_redirect(command_part, file_operator_part, file_part)
        except (FileNotFoundError, OSError, RuntimeError) as e:
            mycli.logger.error('sql: %r, error: %r', text, e)
            mycli.logger.error('traceback: %r', traceback.format_exc())
            mycli.echo(str(e), err=True, fg='red')
            return

    if mycli.sandbox_mode and not is_sandbox_allowed(text):
        mycli.echo(
            "ERROR 1820: You must reset your password using ALTER USER or SET PASSWORD before executing this statement.",
            err=True,
            fg='red',
        )
        return

    if mycli.destructive_warning:
        destroy = confirm_destructive_query(mycli.destructive_keywords, text)
        if destroy is None:
            pass
        elif destroy is True:
            mycli.echo('Your call!')
        else:
            mycli.echo('Wise choice!')
            return

    successful = False
    try:
        mycli.logger.debug('sql: %r', text)
        special.write_tee(mycli.last_prompt_message, nl=False)
        special.write_tee(text)
        mycli.log_query(text)

        start = time.time()
        results = sqlexecute.run(text)
        mycli.main_formatter.query = text
        mycli.redirect_formatter.query = text
        successful = True
        _output_results(mycli, state, results, start)
        special.unset_once_if_written(mycli.post_redirect_command)
        special.flush_pipe_once_if_written(mycli.post_redirect_command)
    except pymysql.err.InterfaceError:
        if not mycli.reconnect():
            return
        _one_iteration(mycli, state, text)
        return
    except EOFError as e:
        raise e
    except KeyboardInterrupt:
        connection_id_to_kill = sqlexecute.connection_id or 0
        if connection_id_to_kill > 0:
            mycli.logger.debug('connection id to kill: %r', connection_id_to_kill)
            try:
                sqlexecute.connect()
                for kill_result in sqlexecute.run(f'kill {connection_id_to_kill}'):
                    status_str = str(kill_result.status_plain).lower()
                    if status_str.find('ok') > -1:
                        mycli.logger.debug('cancelled query, connection id: %r, sql: %r', connection_id_to_kill, text)
                        mycli.echo(f'Cancelled query id: {connection_id_to_kill}', err=True, fg='blue')
                    else:
                        mycli.logger.debug(
                            'Failed to confirm query cancellation, connection id: %r, sql: %r',
                            connection_id_to_kill,
                            text,
                        )
                        mycli.echo(f'Failed to confirm query cancellation, id: {connection_id_to_kill}', err=True, fg='red')
            except Exception as e2:
                mycli.echo(f'Encountered error while cancelling query: {e2}', err=True, fg='red')
        else:
            mycli.logger.debug('Did not get a connection id, skip cancelling query')
            mycli.echo('Did not get a connection id, skip cancelling query', err=True, fg='red')
    except NotImplementedError:
        mycli.echo('Not Yet Implemented.', fg='yellow')
    except pymysql.OperationalError as e1:
        mycli.logger.debug('Exception: %r', e1)
        if e1.args[0] == ER_MUST_CHANGE_PASSWORD:
            mycli.sandbox_mode = True
            mycli.echo(
                "ERROR 1820: You must reset your password using ALTER USER or SET PASSWORD before executing this statement.",
                err=True,
                fg='red',
            )
        elif e1.args[0] in (2003, 2006, 2013):
            if not mycli.reconnect():
                return
            _one_iteration(mycli, state, text)
            return
        else:
            mycli.logger.error('sql: %r, error: %r', text, e1)
            mycli.logger.error('traceback: %r', traceback.format_exc())
            mycli.echo(str(e1), err=True, fg='red')
    except Exception as e:
        mycli.logger.error('sql: %r, error: %r', text, e)
        mycli.logger.error('traceback: %r', traceback.format_exc())
        mycli.echo(str(e), err=True, fg='red')
    else:
        if mycli.sandbox_mode and is_password_change(text):
            new_password = extract_new_password(text)
            if new_password is not None:
                sqlexecute.password = new_password
            try:
                sqlexecute.connect()
                mycli.sandbox_mode = False
                mycli.echo("Password changed successfully. Reconnected.", err=True, fg='green')
                mycli.refresh_completions()
            except Exception as e:
                mycli.sandbox_mode = False
                mycli.echo(
                    f"Password changed but reconnection failed: {e}\nPlease restart mycli with your new password.",
                    err=True,
                    fg='yellow',
                )

        if is_dropping_database(text, sqlexecute.dbname):
            sqlexecute.dbname = None
            sqlexecute.connect()

        if need_completion_refresh(text):
            mycli.refresh_completions(reset=need_completion_reset(text))
    finally:
        if mycli.logfile is False:
            mycli.echo('Warning: This query was not logged.', err=True, fg='red')

    query = Query(text, successful, state.mutating)
    mycli.query_history.append(query)


def _contributors_picker() -> str:
    lines: str = ""

    try:
        with resources.files(mycli_package).joinpath("AUTHORS").open('r') as f:
            lines += f.read()
    except FileNotFoundError:
        pass

    contents = []
    for line in lines.split("\n"):
        if m := re.match(r"^ *\* (.*)", line):
            contents.append(m.group(1))
    return random.choice(contents) if contents else 'our contributors'


def _sponsors_picker() -> str:
    lines: str = ""

    try:
        with resources.files(mycli_package).joinpath("SPONSORS").open('r') as f:
            lines += f.read()
    except FileNotFoundError:
        pass

    contents = []
    for line in lines.split("\n"):
        if m := re.match(r"^ *\* (.*)", line):
            contents.append(m.group(1))
    return random.choice(contents) if contents else 'our sponsors'


def _tips_picker() -> str:
    tips = []

    try:
        with resources.files(mycli_package).joinpath('TIPS').open('r') as f:
            for line in f:
                if line.startswith("#"):
                    continue
                if tip := line.strip():
                    tips.append(tip)
    except FileNotFoundError:
        pass

    return random.choice(tips) if tips else r'\? or "help" for help!'


def main_repl(mycli: 'MyCli') -> None:
    sqlexecute = mycli.sqlexecute
    assert sqlexecute is not None
    state = ReplState()

    mycli.configure_pager()
    if mycli.smart_completion and not mycli.sandbox_mode:
        mycli.refresh_completions()

    history = _create_history(mycli)
    key_bindings = mycli_bindings(mycli)
    _show_startup_banner(mycli, sqlexecute)
    _build_prompt_session(mycli, state, history, key_bindings)
    set_all_external_titles(mycli)

    try:
        while True:
            _one_iteration(mycli, state)
            state.iterations += 1
    except EOFError:
        special.close_tee()
        if not mycli.less_chatty:
            mycli.echo('Goodbye!')

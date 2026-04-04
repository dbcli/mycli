from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from prompt_toolkit.shortcuts import PromptSession
import sqlglot

from mycli.packages import special
from mycli.sqlexecute import SQLExecute

if TYPE_CHECKING:
    from mycli.main import MyCli


def server_date(sqlexecute: SQLExecute, quoted: bool = False) -> str:
    server_date_str = sqlexecute.now().strftime('%Y-%m-%d')
    if quoted:
        return f"'{server_date_str}'"
    else:
        return server_date_str


def server_datetime(sqlexecute: SQLExecute, quoted: bool = False) -> str:
    server_datetime_str = sqlexecute.now().strftime('%Y-%m-%d %H:%M:%S')
    if quoted:
        return f"'{server_datetime_str}'"
    else:
        return server_datetime_str


# todo: maybe these handlers belong in a repl_handlers.py (which does not exist yet)
# \clip doesn't even have a keybinding
def handle_clip_command(mycli: 'MyCli', text: str) -> bool:
    r"""A clip command is any query that is prefixed or suffixed by a
    '\clip'.

    :param text: Document
    :return: Boolean

    """

    if special.clip_command(text):
        query = special.get_clip_query(text) or mycli.get_last_query()
        message = special.copy_query_to_clipboard(sql=query)
        if message:
            raise RuntimeError(message)
        return True
    return False


def handle_editor_command(
    mycli: 'MyCli',
    text: str,
    inputhook: Callable | None,
    loaded_message_fn: Callable,
) -> str:
    r"""Editor command is any query that is prefixed or suffixed by a '\e'.
    The reason for a while loop is because a user might edit a query
    multiple times. For eg:

    "select * from \e"<enter> to edit it in vim, then come
    back to the prompt with the edited query "select * from
    blah where q = 'abc'\e" to edit it again.
    :param text: Document
    :return: Document

    """

    while special.editor_command(text):
        filename = special.get_filename(text)
        query = special.get_editor_query(text) or mycli.get_last_query()
        sql, message = special.open_external_editor(filename=filename, sql=query)
        if message:
            # Something went wrong. Raise an exception and bail.
            raise RuntimeError(message)
        while True:
            try:
                assert isinstance(mycli.prompt_session, PromptSession)
                text = mycli.prompt_session.prompt(
                    default=sql,
                    inputhook=inputhook,
                    message=loaded_message_fn,
                )
                break
            except KeyboardInterrupt:
                sql = ""

        continue
    return text


def handle_prettify_binding(
    mycli: 'MyCli',
    text: str,
) -> str:
    if not text:
        return ''
    try:
        statements = sqlglot.parse(text, read='mysql')
    except Exception:
        statements = []
    if len(statements) == 1 and statements[0]:
        parse_succeeded = True
        pretty_text = statements[0].sql(pretty=True, pad=4, dialect='mysql')
    else:
        parse_succeeded = False
        pretty_text = text.rstrip(';')
        mycli.toolbar_error_message = 'Prettify failed to parse single statement'
    if pretty_text and parse_succeeded:
        pretty_text = pretty_text + ';'
    return pretty_text


def handle_unprettify_binding(
    mycli: 'MyCli',
    text: str,
) -> str:
    if not text:
        return ''
    try:
        statements = sqlglot.parse(text, read='mysql')
    except Exception:
        statements = []
    if len(statements) == 1 and statements[0]:
        parse_succeeded = True
        unpretty_text = statements[0].sql(pretty=False, dialect='mysql')
    else:
        parse_succeeded = False
        unpretty_text = text.rstrip(';')
        mycli.toolbar_error_message = 'Unprettify failed to parse single statement'
    if unpretty_text and parse_succeeded:
        unpretty_text = unpretty_text + ';'
    return unpretty_text

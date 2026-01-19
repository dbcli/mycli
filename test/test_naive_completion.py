# type: ignore

from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
import pytest


@pytest.fixture
def completer():
    import mycli.sqlcompleter as sqlcompleter

    return sqlcompleter.SQLCompleter(smart_completion=False)


@pytest.fixture
def complete_event():
    from unittest.mock import Mock

    return Mock()


def test_empty_string_completion(completer, complete_event):
    text = ""
    position = 0
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(map(Completion, completer.all_completions))


def test_select_keyword_completion(completer, complete_event):
    text = "SEL"
    position = len("SEL")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == [Completion(text="SELECT", start_position=-3)]


def test_function_name_completion(completer, complete_event):
    text = "SELECT MA"
    position = len("SELECT MA")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert sorted(x.text for x in result) == [
        'MAKEDATE',
        'MAKETIME',
        'MAKE_SET',
        'MASTER',
        'MASTER_AUTO_POSITION',
        'MASTER_BIND',
        'MASTER_COMPRESSION_ALGORITHMS',
        'MASTER_CONNECT_RETRY',
        'MASTER_DELAY',
        'MASTER_HEARTBEAT_PERIOD',
        'MASTER_HOST',
        'MASTER_LOG_FILE',
        'MASTER_LOG_POS',
        'MASTER_PASSWORD',
        'MASTER_PORT',
        'MASTER_POS_WAIT',
        'MASTER_PUBLIC_KEY_PATH',
        'MASTER_RETRY_COUNT',
        'MASTER_SSL',
        'MASTER_SSL_CA',
        'MASTER_SSL_CAPATH',
        'MASTER_SSL_CERT',
        'MASTER_SSL_CIPHER',
        'MASTER_SSL_CRL',
        'MASTER_SSL_CRLPATH',
        'MASTER_SSL_KEY',
        'MASTER_SSL_VERIFY_SERVER_CERT',
        'MASTER_TLS_CIPHERSUITES',
        'MASTER_TLS_VERSION',
        'MASTER_USER',
        'MASTER_ZSTD_COMPRESSION_LEVEL',
        'MATCH',
        'MAX',
        'MAXVALUE',
        'MAX_CONNECTIONS_PER_HOUR',
        'MAX_QUERIES_PER_HOUR',
        'MAX_ROWS',
        'MAX_SIZE',
        'MAX_UPDATES_PER_HOUR',
        'MAX_USER_CONNECTIONS',
    ]


def test_column_name_completion(completer, complete_event):
    text = "SELECT  FROM users"
    position = len("SELECT ")
    result = list(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    assert result == list(map(Completion, completer.all_completions))


def test_special_name_completion(completer, complete_event):
    text = "\\"
    position = len("\\")
    result = set(completer.get_completions(Document(text=text, cursor_position=position), complete_event))
    # Special commands will NOT be suggested during naive completion mode.
    assert result == set()

import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document


@pytest.fixture
def completer():
    import mycli.sqlcompleter as sqlcompleter
    return sqlcompleter.SQLCompleter(smart_completion=False)


@pytest.fixture
def complete_event():
    from mock import Mock
    return Mock()


def test_empty_string_completion(completer, complete_event):
    text = ''
    position = 0
    result = list(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == list(map(Completion, sorted(completer.all_completions)))


def test_select_keyword_completion(completer, complete_event):
    text = 'SEL'
    position = len('SEL')
    result = list(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == list([Completion(text='SELECT', start_position=-3)])


def test_function_name_completion(completer, complete_event):
    text = 'SELECT MA'
    position = len('SELECT MA')
    result = list(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == list([
        Completion(text='MAKEDATE', start_position=-2),
        Completion(text='MAKETIME', start_position=-2),
        Completion(text='MAKE_SET', start_position=-2),
        Completion(text='MASTER', start_position=-2),
        Completion(text='MASTER_AUTO_POSITION', start_position=-2),
        Completion(text='MASTER_BIND', start_position=-2),
        Completion(text='MASTER_COMPRESSION_ALGORITHMS', start_position=-2),
        Completion(text='MASTER_CONNECT_RETRY', start_position=-2),
        Completion(text='MASTER_DELAY', start_position=-2),
        Completion(text='MASTER_HEARTBEAT_PERIOD', start_position=-2),
        Completion(text='MASTER_HOST', start_position=-2),
        Completion(text='MASTER_LOG_FILE', start_position=-2),
        Completion(text='MASTER_LOG_POS', start_position=-2),
        Completion(text='MASTER_PASSWORD', start_position=-2),
        Completion(text='MASTER_PORT', start_position=-2),
        Completion(text='MASTER_POS_WAIT', start_position=-2),
        Completion(text='MASTER_PUBLIC_KEY_PATH', start_position=-2),
        Completion(text='MASTER_RETRY_COUNT', start_position=-2),
        Completion(text='MASTER_SERVER_ID', start_position=-2),
        Completion(text='MASTER_SSL', start_position=-2),
        Completion(text='MASTER_SSL_CA', start_position=-2),
        Completion(text='MASTER_SSL_CAPATH', start_position=-2),
        Completion(text='MASTER_SSL_CERT', start_position=-2),
        Completion(text='MASTER_SSL_CIPHER', start_position=-2),
        Completion(text='MASTER_SSL_CRL', start_position=-2),
        Completion(text='MASTER_SSL_CRLPATH', start_position=-2),
        Completion(text='MASTER_SSL_KEY', start_position=-2),
        Completion(text='MASTER_SSL_VERIFY_SERVER_CERT', start_position=-2),
        Completion(text='MASTER_TLS_CIPHERSUITES', start_position=-2),
        Completion(text='MASTER_TLS_VERSION', start_position=-2),
        Completion(text='MASTER_USER', start_position=-2),
        Completion(text='MASTER_ZSTD_COMPRESSION_LEVEL', start_position=-2),
        Completion(text='MATCH', start_position=-2),
        Completion(text='MAX', start_position=-2),
        Completion(text='MAXVALUE', start_position=-2),
        Completion(text='MAX_CONNECTIONS_PER_HOUR', start_position=-2),
        Completion(text='MAX_QUERIES_PER_HOUR', start_position=-2),
        Completion(text='MAX_ROWS', start_position=-2),
        Completion(text='MAX_SIZE', start_position=-2),
        Completion(text='MAX_UPDATES_PER_HOUR', start_position=-2),
        Completion(text='MAX_USER_CONNECTIONS', start_position=-2)])


def test_column_name_completion(completer, complete_event):
    text = 'SELECT  FROM users'
    position = len('SELECT ')
    result = list(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == list(map(Completion, sorted(completer.all_completions)))


def test_special_name_completion(completer, complete_event):
    text = '\\'
    position = len('\\')
    result = set(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    # Special commands will NOT be suggested during naive completion mode.
    assert result == set()

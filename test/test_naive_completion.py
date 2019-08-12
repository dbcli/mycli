from __future__ import unicode_literals
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
        Completion(text='MASTER', start_position=-2),
        Completion(text='MAX', start_position=-2)])


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

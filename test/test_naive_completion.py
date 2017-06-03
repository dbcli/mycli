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
    result = set(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == set(map(Completion, completer.all_completions))


def test_select_keyword_completion(completer, complete_event):
    text = 'SEL'
    position = len('SEL')
    result = set(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == set([Completion(text='SELECT', start_position=-3)])


def test_function_name_completion(completer, complete_event):
    text = 'SELECT MA'
    position = len('SELECT MA')
    result = set(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == set([
        Completion(text='MAX', start_position=-2),
        Completion(text='MASTER', start_position=-2)])


def test_column_name_completion(completer, complete_event):
    text = 'SELECT  FROM users'
    position = len('SELECT ')
    result = set(completer.get_completions(
        Document(text=text, cursor_position=position),
        complete_event))
    assert result == set(map(Completion, completer.all_completions))

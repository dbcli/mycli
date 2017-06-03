import time
import pytest
from mock import Mock, patch


@pytest.fixture
def refresher():
    from mycli.completion_refresher import CompletionRefresher
    return CompletionRefresher()


def test_ctor(refresher):
    """Refresher object should contain a few handlers.

    :param refresher:
    :return:

    """
    assert len(refresher.refreshers) > 0
    actual_handlers = list(refresher.refreshers.keys())
    expected_handlers = ['databases', 'schemata', 'tables', 'users', 'functions',
                         'special_commands', 'show_commands']
    assert expected_handlers == actual_handlers


def test_refresh_called_once(refresher):
    """

    :param refresher:
    :return:
    """
    callbacks = Mock()
    sqlexecute = Mock()

    with patch.object(refresher, '_bg_refresh') as bg_refresh:
        actual = refresher.refresh(sqlexecute, callbacks)
        time.sleep(1)  # Wait for the thread to work.
        assert len(actual) == 1
        assert len(actual[0]) == 4
        assert actual[0][3] == 'Auto-completion refresh started in the background.'
        bg_refresh.assert_called_with(sqlexecute, callbacks, {})


def test_refresh_called_twice(refresher):
    """If refresh is called a second time, it should be restarted.

    :param refresher:
    :return:

    """
    callbacks = Mock()

    sqlexecute = Mock()

    def dummy_bg_refresh(*args):
        time.sleep(3)  # seconds

    refresher._bg_refresh = dummy_bg_refresh

    actual1 = refresher.refresh(sqlexecute, callbacks)
    time.sleep(1)  # Wait for the thread to work.
    assert len(actual1) == 1
    assert len(actual1[0]) == 4
    assert actual1[0][3] == 'Auto-completion refresh started in the background.'

    actual2 = refresher.refresh(sqlexecute, callbacks)
    time.sleep(1)  # Wait for the thread to work.
    assert len(actual2) == 1
    assert len(actual2[0]) == 4
    assert actual2[0][3] == 'Auto-completion refresh restarted.'


def test_refresh_with_callbacks(refresher):
    """Callbacks must be called.

    :param refresher:

    """
    callbacks = [Mock()]
    sqlexecute_class = Mock()
    sqlexecute = Mock()

    with patch('mycli.completion_refresher.SQLExecute', sqlexecute_class):
        # Set refreshers to 0: we're not testing refresh logic here
        refresher.refreshers = {}
        refresher.refresh(sqlexecute, callbacks)
        time.sleep(1)  # Wait for the thread to work.
        assert (callbacks[0].call_count == 1)

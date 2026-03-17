# type: ignore

from prompt_toolkit.shortcuts import PromptSession

from mycli.clitoolbar import create_toolbar_tokens_func
from mycli.main import MyCli
from mycli.sqlexecute import SQLExecute
from test.utils import HOST, PASSWORD, PORT, USER, dbtest


@dbtest
def test_create_toolbar_tokens_func_initial():
    m = MyCli()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    m.prompt_app = PromptSession()
    iteration = 0
    f = create_toolbar_tokens_func(m, lambda: iteration == 0, m.toolbar_format)
    result = f()
    m.close()
    assert any("right-arrow accepts full-line suggestion" in token for token in result)


@dbtest
def test_create_toolbar_tokens_func_short():
    m = MyCli()
    m.sqlexecute = SQLExecute(
        None,
        USER,
        PASSWORD,
        HOST,
        PORT,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    m.prompt_app = PromptSession()
    iteration = 1
    f = create_toolbar_tokens_func(m, lambda: iteration == 0, m.toolbar_format)
    result = f()
    m.close()
    assert not any("right-arrow accepts full-line suggestion" in token for token in result)

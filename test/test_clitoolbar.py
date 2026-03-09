from prompt_toolkit.shortcuts import PromptSession

from mycli.clitoolbar import create_toolbar_tokens_func
from mycli.main import MyCli


def test_create_toolbar_tokens_func_initial():
    m = MyCli()
    m.prompt_app = PromptSession()
    iteration = 0
    f = create_toolbar_tokens_func(m, lambda: iteration == 0, m.toolbar_format)
    result = f()
    assert any("right-arrow accepts full-line suggestion" in token for token in result)


def test_create_toolbar_tokens_func_short():
    m = MyCli()
    m.prompt_app = PromptSession()
    iteration = 1
    f = create_toolbar_tokens_func(m, lambda: iteration == 0, m.toolbar_format)
    result = f()
    assert not any("right-arrow accepts full-line suggestion" in token for token in result)

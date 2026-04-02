# type: ignore

"""Tests for the mycli.clistyle module."""

from types import SimpleNamespace

from prompt_toolkit.styles import Style as PromptStyle
from pygments.style import Style as PygmentsStyle
from pygments.token import Token
from pygments.util import ClassNotFound

from mycli import clistyle


def test_parse_pygments_style_handles_style_classes_instances_and_dict_values() -> None:
    class DemoStyle(PygmentsStyle):
        default_style = ''
        styles = {
            Token.Name: 'bold',
            Token.String: 'ansired',
        }

    token_type, style_value = clistyle.parse_pygments_style(
        'Token.String',
        DemoStyle,
        {'Token.String': 'Token.Name'},
    )
    assert token_type == Token.String
    assert style_value == 'bold'

    token_type, style_value = clistyle.parse_pygments_style(
        'Token.String',
        DemoStyle(),
        {'Token.String': 'Token.Name'},
    )
    assert token_type == Token.String
    assert style_value == 'bold'

    token_type, style_value = clistyle.parse_pygments_style(
        'Token.String',
        'unused',
        {'Token.String': 'ansiblue'},
    )
    assert token_type == Token.String
    assert style_value == 'ansiblue'


def test_is_valid_pygments_returns_true_and_false(monkeypatch) -> None:
    assert clistyle.is_valid_pygments('ansired') is True

    class FailingPygmentsStyle:
        def __init_subclass__(cls, **kwargs) -> None:
            raise AssertionError('bad style')

    monkeypatch.setattr(clistyle, 'PygmentsStyle', FailingPygmentsStyle)

    assert clistyle.is_valid_pygments('invalid') is False


def test_is_valid_ptoolkit_returns_true_and_false(monkeypatch) -> None:
    assert clistyle.is_valid_ptoolkit('bold') is True

    class FailingPromptStyle:
        def __init__(self, _rules) -> None:
            raise ValueError('bad style')

    monkeypatch.setattr(clistyle, 'Style', FailingPromptStyle)

    assert clistyle.is_valid_ptoolkit('invalid') is False


def test_style_factory_ptoolkit_builds_styles_and_falls_back(monkeypatch, caplog) -> None:
    calls: list[str] = []
    native_style = object()

    def fake_get_style_by_name(name: str):
        calls.append(name)
        if name == 'missing':
            raise ClassNotFound('missing')
        if name == 'native':
            return native_style
        raise AssertionError(f'unexpected style {name}')

    class FakeStyle:
        def __init__(self, rules) -> None:
            self.rules = list(rules)

    monkeypatch.setattr(clistyle.pygments.styles, 'get_style_by_name', fake_get_style_by_name)
    monkeypatch.setattr(
        clistyle,
        'parse_pygments_style',
        lambda token, style, cli_style: {
            'Token.Prompt': (Token.Prompt, 'token-valid'),
            'Token.Toolbar': (Token.Toolbar, 'token-invalid'),
            'Token.Name': (Token.Name, 'token-invalid'),
        }[token],
    )
    monkeypatch.setattr(clistyle, 'is_valid_ptoolkit', lambda value: value in {'token-valid', 'prompt-valid'})
    monkeypatch.setattr(clistyle, 'Style', FakeStyle)
    monkeypatch.setattr(clistyle, 'style_from_pygments_cls', lambda style: ('pygments-style', style))
    monkeypatch.setattr(clistyle, 'merge_styles', lambda styles: styles)

    cli_style = {
        'Token.Prompt': 'Token.Name',
        'Token.Toolbar': 'Token.Name',
        'Token.Name': 'ignored',
        'prompt': 'prompt-valid',
        'search': 'prompt-invalid',
    }

    with caplog.at_level('ERROR', logger='mycli.clistyle'):
        styles = clistyle.style_factory_ptoolkit('missing', cli_style)

    assert calls == ['missing', 'native']
    assert styles[0] == ('pygments-style', native_style)
    assert styles[1].rules == [('bottom-toolbar', 'noreverse')]
    assert styles[2].rules == [
        ('prompt', 'token-valid'),
        ('prompt', 'prompt-valid'),
    ]
    assert ('bottom-toolbar', 'token-invalid') not in styles[2].rules
    assert ('search', 'prompt-invalid') not in styles[2].rules
    assert 'Unhandled style / class name: Token.Name' in caplog.text


def test_style_factory_helpers_updates_known_tokens(monkeypatch, caplog) -> None:
    base_styles = {Token.Output.Header: 'ansiyellow'}
    style_class = SimpleNamespace(styles=base_styles)

    monkeypatch.setattr(clistyle.pygments.styles, 'get_style_by_name', lambda name: style_class)
    monkeypatch.setattr(
        clistyle,
        'parse_pygments_style',
        lambda token, style, cli_style: {
            'Token.Prompt': (Token.Prompt, 'ansiblue'),
            'Token.Toolbar': (Token.Toolbar, 'skip-me'),
        }[token],
    )
    monkeypatch.setattr(clistyle, 'is_valid_pygments', lambda value: value != 'skip-me')

    cli_style = {
        'Token.Prompt': 'Token.Name',
        'Token.Toolbar': 'Token.Name',
        'search': 'ansigreen',
        'search.current': 'skip-me',
        'sql.keyword': 'ansired',
        'sql.string': 'skip-me',
        'unknown': 'skip-me',
    }

    with caplog.at_level('ERROR', logger='mycli.clistyle'):
        output_style = clistyle.style_factory_helpers('native', cli_style)

    assert output_style.styles[Token.Prompt] == 'ansiblue'
    assert output_style.styles[Token.SearchMatch] == 'ansigreen'
    assert Token.SearchMatch.Current not in output_style.styles
    assert output_style.styles[Token.Keyword] == 'ansired'
    assert output_style.styles[Token.Output.Header] == 'ansiyellow'
    assert Token.Toolbar not in output_style.styles
    assert output_style.styles[Token.String] != 'skip-me'
    assert 'Unhandled style / class name: unknown' in caplog.text


def test_style_factory_helpers_falls_back_and_copies_warning_styles(monkeypatch) -> None:
    native_styles = {
        Token.Text: 'ansiblack',
        Token.Warnings.Header: 'ansimagenta',
        Token.Warnings.Status: 'ansicyan',
    }

    def fake_get_style_by_name(name: str):
        if name == 'missing':
            raise ClassNotFound('missing')
        if name == 'native':
            return SimpleNamespace(styles=native_styles.copy())
        raise AssertionError(f'unexpected style {name}')

    monkeypatch.setattr(clistyle.pygments.styles, 'get_style_by_name', fake_get_style_by_name)

    output_style = clistyle.style_factory_helpers('missing', {}, warnings=True)

    assert output_style.styles[Token.Warnings.Header] == 'ansimagenta'
    assert output_style.styles[Token.Warnings.Status] == 'ansicyan'
    assert output_style.styles[Token.Output.Header] == 'ansimagenta'
    assert output_style.styles[Token.Output.Status] == 'ansicyan'


def test_style_factory_ptoolkit_returns_merged_style_object() -> None:
    style = clistyle.style_factory_ptoolkit('native', {'prompt': 'bold'})

    assert style.get_attrs_for_style_str('class:prompt') == PromptStyle([('prompt', 'bold')]).get_attrs_for_style_str('class:prompt')

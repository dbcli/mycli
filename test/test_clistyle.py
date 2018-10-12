# -*- coding: utf-8 -*-
"""Test the mycli.clistyle module."""

from pygments.style import Style
from pygments.token import Token

from mycli.clistyle import style_factory


def test_style_factory():
    """Test that a Pygments Style class is created."""
    header = 'bold underline #ansired'
    cli_style = {'Token.Output.Header': header}
    style = style_factory('default', cli_style)

    assert isinstance(style(), Style)
    assert Token.Output.Header in style.styles
    assert header == style.styles[Token.Output.Header]


def test_style_factory_unknown_name():
    """Test that an unrecognized name will not throw an error."""
    style = style_factory('foobar', {})

    assert isinstance(style(), Style)

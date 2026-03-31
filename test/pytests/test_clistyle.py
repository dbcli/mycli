# type: ignore

"""Test the mycli.clistyle module."""

from pygments.style import Style
from pygments.token import Token
import pytest

from mycli.clistyle import style_factory_ptoolkit


@pytest.mark.skip(reason="incompatible with new prompt toolkit")
def test_style_factory_ptoolkit():
    """Test that a Pygments Style class is created."""
    header = "bold underline #ansired"
    cli_style = {"Token.Output.Header": header}
    style = style_factory_ptoolkit("default", cli_style)

    assert isinstance(style(), Style)
    assert Token.Output.Header in style.styles
    assert header == style.styles[Token.Output.Header]


@pytest.mark.skip(reason="incompatible with new prompt toolkit")
def test_style_factory_ptoolkit_unknown_name():
    """Test that an unrecognized name will not throw an error."""
    style = style_factory_ptoolkit("foobar", {})

    assert isinstance(style(), Style)

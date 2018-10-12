import pygments.style
import pygments.styles
from pygments.token import string_to_tokentype
from pygments.util import ClassNotFound


def style_factory(name, cli_style):
    """Create a Pygments Style class based on the user's preferences.

    :param str name: The name of a built-in Pygments style.
    :param dict cli_style: The user's token-type style preferences.

    """
    try:
        style = pygments.styles.get_style_by_name(name)
    except ClassNotFound:
        style = pygments.styles.get_style_by_name('native')

    style_tokens = {}
    style_tokens.update(style.styles)
    custom_styles = {string_to_tokentype(x): y for x, y in cli_style.items()}
    style_tokens.update(custom_styles)

    class MycliStyle(pygments.style.Style):
        default_styles = ''
        styles = style_tokens

    return MycliStyle

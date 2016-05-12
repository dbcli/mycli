from pygments.token import string_to_tokentype
from pygments.util import ClassNotFound
from prompt_toolkit.styles import default_style_extensions, style_from_dict
import pygments.styles


def style_factory(name, cli_style):
    try:
        style = pygments.styles.get_style_by_name(name)
    except ClassNotFound:
        style = pygments.styles.get_style_by_name('native')

    styles = {}
    styles.update(style.styles)
    styles.update(default_style_extensions)
    custom_styles = dict([(string_to_tokentype(x), y) for x, y in cli_style.items()])
    styles.update(custom_styles)

    return style_from_dict(styles)

from pygments.token import Token
from pygments.style import Style
from pygments.util import ClassNotFound
from prompt_toolkit.styles import default_style_extensions
import pygments.styles


def style_factory(name):
    try:
        style = pygments.styles.get_style_by_name(name)
    except ClassNotFound:
        style = pygments.styles.get_style_by_name('native')

    class CLIStyle(Style):
        styles = {}

        styles.update(style.styles)
        styles.update(default_style_extensions)
        styles.update({
            # Completion menus.
            Token.Menu.Completions.Completion.Current: 'bg:#00aaaa #000000',
            Token.Menu.Completions.Completion: 'bg:#008888 #ffffff',
            Token.Menu.Completions.MultiColumnMeta: 'bg:#aaffff #000000',
            Token.Menu.Completions.ProgressButton: 'bg:#003333',
            Token.Menu.Completions.ProgressBar: 'bg:#00aaaa',

            # Selected text.
            Token.SelectedText: '#ffffff bg:#6666aa',

            # Search matches. (reverse-i-search)
            Token.SearchMatch: '#ffffff bg:#4444aa',
            Token.SearchMatch.Current: '#ffffff bg:#44aa44',

            # The bottom toolbar.
            Token.Toolbar: 'bg:#440044 #ffffff',
            Token.Toolbar: 'bg:#222222 #aaaaaa',
            Token.Toolbar.Off: 'bg:#222222 #888888',
            Token.Toolbar.On: 'bg:#222222 #ffffff',

            # Search/arg/system toolbars.
            Token.Toolbar.Search: 'noinherit bold',
            Token.Toolbar.Search.Text: 'nobold',
            Token.Toolbar.System: 'noinherit bold',
            Token.Toolbar.Arg: 'noinherit bold',
            Token.Toolbar.Arg.Text: 'nobold',
        })

    return CLIStyle

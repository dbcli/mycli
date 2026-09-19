# Key Bindings

Most key bindings are simply inherited from [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/en/master/index.html).

The following key bindings are special to mycli:

## <kbd>F1</kbd>

Open documentation index in a browser tab.

## <kbd>F2</kbd>

Enable/Disable SmartCompletion Mode.

## <kbd>F3</kbd>

Enable/Disable Multiline Mode.

## <kbd>F4</kbd>

Toggle between Vi and Emacs mode.

## <kbd>Tab</kbd>

Force autocompletion at cursor.

## <kbd>C-space</kbd>

Initialize autocompletion at cursor.

If the autocompletion menu is not showing, display it with the appropriate completions for the context.

If the menu is showing, select the next completion.

## <kbd>ESC</kbd> <kbd>Enter</kbd>

Introduce a line break in multi-line mode, or dispatch the command in single-line mode.

The sequence ESC-Enter is often sent by Alt-Enter.

## <kbd>C-x</kbd> <kbd>p</kbd> _(Emacs-mode)_

Prettify and indent current statement, usually into multiple lines.

Only accepts buffers containing single SQL statements.

## <kbd>C-x</kbd> <kbd>u</kbd> _(Emacs-mode)_

Unprettify and dedent current statement, usually into one line.

Only accepts buffers containing single SQL statements.

## <kbd>C-o</kbd> <kbd>d</kbd> _(Emacs-mode)_

Insert the current date at cursor, defined by `NOW()` on the server.

## <kbd>C-o</kbd> <kbd>C-d</kbd> _(Emacs-mode)_

Insert the quoted current date at cursor.

## <kbd>C-o</kbd> <kbd>t</kbd> _(Emacs-mode)_

Insert the current datetime at cursor.

## <kbd>C-o</kbd> <kbd>C-t</kbd> _(Emacs-mode)_

Insert the quoted current datetime at cursor.

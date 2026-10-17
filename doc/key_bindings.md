# Key Bindings

There are two major editing modes available: Emacs mode and Vi mode.  The mode
can be changed via the `key_bindings` property in the config file (`~/.myclirc`) or
toggled via the <kbd>F4</kbd> key.

Emacs mode is the default. In Emacs mode you can type <kbd>Control-a</kbd> to go
to the beginning of a line, <kbd>Control-e</kbd> to go to the end of a line,
with many more options for navigation, similar to the defaults of the [readline](https://tiswww.case.edu/php/chet/readline/rluserman.html)
library.

When Vi mode is enabled you can use vi-style navigation, along with modal
editing features offered by Vim in the REPL, including text objects.

Most key bindings are simply inherited from [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/en/master/index.html).

Mycli also adds some custom keybindings which are summarized here along with
completion navigation.

## The Basics: Custom Bindings and Completion Navigation

### <kbd>F1</kbd>

Open the web documentation index in a browser tab.

### <kbd>F2</kbd>

Toggle smart completions.

### <kbd>F3</kbd>

Toggle multi-line mode.

### <kbd>F4</kbd>

Toggle Emacs/Vi editing modes.

### <kbd>Tab</kbd>

Summon completions + always advance in candidates (configurable).

### <kbd>Control-space</kbd>

Summon completions or advance in candidates if present (configurable).

### <kbd>Enter</kbd>

Choose a completion candidate.

### <kbd>Esc</kbd>

Cancel the completions popup.

### <kbd>Control-g</kbd>

Cancel the completions popup.

### <kbd>Control-r</kbd>

Search the query history with [fzf](https://github.com/junegunn/fzf) if available, or use
[prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/en/master/index.html)'s
`reverse-i-search` as a fallback (configurable).

### <kbd>Alt-Enter</kbd>

Introduce a line break in multi-line mode, or dispatch the current query in
single-line mode.

The keyboard combination <kbd>Alt-Enter</kbd> usually sends the sequence
`ESC`,`Enter` on the wire, and it may also be possible to use the <kbd>ESC</kbd>,<kbd>Enter</kbd>
key sequence.

### Arrow keys

Completion navigation (when popup is present).

### Right-arrow

Accept full-line history suggestion (when suggestion is visible).

### <kbd>Control-d</kbd>

Exit the REPL (configurable).

## In Emacs Mode Only

A comma indicates a sequence of multiple keystrokes.

### <kbd>Control-x</kbd>, <kbd>p</kbd>

Prettify and indent the current statement, usually into multiple lines.

Only works for buffers containing single SQL statements.

### <kbd>Control-x</kbd>, <kbd>u</kbd>

Unprettify and dedent the current statement, usually into one line.

Only works for buffers containing single SQL statements.

### <kbd>Control-o</kbd>, <kbd>d</kbd>

Insert the current literal date at the cursor, as defined by `NOW()` on the
server.

### <kbd>Control-o</kbd>, <kbd>t</kbd>

Insert the current literal datetime at the cursor, as defined by `NOW()` on
the server.

### <kbd>Control-o</kbd>, <kbd>Control-d</kbd>

Insert the _quoted_ current literal date at the cursor, as defined by `NOW()`
on the server.

### <kbd>Control-o</kbd>, <kbd>Control-t</kbd>

Insert the _quoted_ current literal datetime at the cursor, as defined by
`NOW()` on the server.

### <kbd>Control-o</kbd>, <kbd>u</kbd>

Insert the current literal Unix timestamp at the cursor, in seconds, as defined
by `time.time()` on the client.

### <kbd>Control-o</kbd>, <kbd>Control-u</kbd>

Insert the current literal Unix timestamp at the cursor, in microseconds, as
defined by `time.time()` on the client.

### <kbd>Alt-r</kbd>

Search query history with [fzf](https://github.com/junegunn/fzf) even if `~/.myclirc`
is configured not to use fuzzy search on the default key <kbd>Control-r</kbd>.

## Advanced

Since <kbd>Alt</kbd> key combinations usually work by sending a series of characters
on the wire, there is sometimes an ambiguity with regard to which characters were
physically typed.  A timeout heuristic is used to resolve this.

Advanced users, and those on slow connections, may want to consult the following
settings in `~/.myclirc` to adjust the timeout heuristic.  The threshold is separate
for Emacs and Vi edit modes:

```ini
[keys]
# How long to wait for an Escape key sequence in vi mode.
# 0.5 seconds is the prompt_toolkit default, but vi users may find that too long.
# Shorter values mean that "Escape" alone is recognized more quickly.
vi_ttimeoutlen = 0.1

# How long to wait for an Escape key sequence in Emacs mode.
emacs_ttimeoutlen = 0.5
```

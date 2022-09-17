*************
Key Bindings:
*************

Most key bindings are simply inherited from `prompt-toolkit <https://python-prompt-toolkit.readthedocs.io/en/master/index.html>`_ .

The following key bindings are special to mycli:

###
F2
###

Enable/Disable SmartCompletion Mode.

###
F3
###

Enable/Disable Multiline Mode.

###
F4
###

Toggle between Vi and Emacs mode.

###
Tab
###

Force autocompletion at cursor.

#######
C-space
#######

Initialize autocompletion at cursor.

If the autocompletion menu is not showing, display it with the appropriate completions for the context.

If the menu is showing, select the next completion.

#########
ESC Enter
#########

Introduce a line break in multi-line mode, or dispatch the command in single-line mode.

The sequence ESC-Enter is often sent by Alt-Enter.

##################
C-x p (Emacs-mode)
##################

Prettify and indent current statement, usually into multiple lines.

Only accepts buffers containing single SQL statements.

##################
C-x u (Emacs-mode)
##################

Unprettify and dedent current statement, usually into one line.

Only accepts buffers containing single SQL statements.

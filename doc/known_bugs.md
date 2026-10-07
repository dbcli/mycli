# Known Bugs

These are known bugs or limitations in mycli which it would be welcome to
fix.

## custom delimiters

A custom delimiter (query terminator) string may be set with the `/delimiter`
special command, but the custom delimiter is not respected in all parts of
mycli's code.

## completions after backtick

Completions after a backtick character are too exuberant.  Example:

```sql
SELECT `<tab>
```

will offer more completions than

```sql
SELECT <tab>
```

## Windows limitations

Mycli is only partially tested on Windows, and several features such as
filename completion after `/source` may not work as expected.

## double-dash with shell redirections

The interpretation of `--` may not be consistent with `$|`.  The double-dahs
is inherently ambiguous, being either a SQL comment initiator, or a common
part of a shell command.  The rules for resolving the ambiguity should be
simple, and better documented.

## enum completions

Completions on enum values may fail if the values contain spaces.

## keyring support

If "Always Allow" is chosen on Mac, then all Python applications will have
access to the credential.

When making connections via a kubectl tunnel, the keyring is disabled, because
the Kubernetes context is not known.

## explorer

There is a trailing blank line in the explorer choices.

## prompt efficiency

The prompt and toolbar are updated more often than needed, even with caching.

## history search preview highlighting

When syntax highlighting with `pygmentize` is enabled for history search previews,
the colors do not match the user's preferences in `~/.myclirc`.

## favorite queries

Favorite queries are triple-quoted on save in `~/.myclirc`.  If the text of the SQL
in the favorite query contains both possible triple-quote delimiters, this fails.

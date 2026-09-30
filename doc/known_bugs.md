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

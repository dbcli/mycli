# Cookbook

Recipes for configuring and using mycli.

## faster table rendering

A substantial amount of time is spent rendering tables in `tabulate` when
the number of rows returned is say 100K or more.  The reason is that
`tabulate` scans every row in pure Python to determine cell width.

One workaround for faster viewing of large results is to configure the output
format to CSV in `~/.myclirc`:

```ini
[main]
table_format = csv
```

and to configure the pager to a fast CSV viewer such as [csvlens](https://github.com/ys-l/csvlens):

```ini
[main]
pager = csvlens
```

which has the effect of moving cell-width calculations from Python to Rust.

## keyring

Use of the system keyring was left disabled in the default `~/.myclirc` to avoid
silently changing default behaviors.  But it is recommended to enable it!

```ini
[main]
use_keyring = auto
```

Sources eligible for the keyring can also be configured with

```ini
[main]
keyring_sources = prompt, literal, file, environment, dsn, login_path, fallback
```

## completions trigger

Mycli's default completions trigger the display of candidates at the first
character, which might be distracting for some.

For more of an industry-standard experience, in which completions are deferred
until more information is typed, set `min_completion_trigger` to a small value
in `~/.myclirc`:

```ini
[main]
min_completion_trigger = 3
```

## DSN environment variables

If using a tool such as [mise](https://github.com/jdx/mise) or [direnv](https://github.com/direnv/direnv) to manage
environment variables, it may be convenient to enable this setting in
`~/.myclirc`:

```ini
[main]
expand_dsn_alias_env_vars = True
```

which allows environment variables in the form `${VAR}` to be substituted
in DSNs.

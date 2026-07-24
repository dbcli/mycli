# Transforms, Plots, and Parquets with Polars Dataframes

## Installing

Install mycli with dataframe support using:

```bash
pip install --upgrade 'mycli[dataframe]'
```

or install these libraries separately:

 * [`polars`](https://pypi.org/project/polars/)
 * [`altair`](https://pypi.org/project/altair/)
 * [`vl-convert-python`](https://pypi.org/project/vl-convert-python/)

## BETA STATUS

Dataframe transforms and plots are new and experimental.  The interface and
functionality may still change.

Here are some known limitations:

 * transforms can't be composed with `$|` shell redirection
 * multiple transform steps are not permitted
 * results from `UNION`s may be unable to be transformed
 * images cannot yet be saved
 * PNG images are static and do not support all Altair features

And there are inherent limitations to the post-processing model: the entire
SQL result must be transferred from the server and loaded into local memory.

## Transforming

In the interactive REPL, append the `.|` operator and a Python expression to a
single SQL statement.  The Python expression receives

 * `df`, a Polars `DataFrame`
 * `pl`, the Polars module
 * `alt`, the Altair module

Spaces may be required around the `.|` operator.

Transform example:

```sql
SELECT * FROM orders .| df.group_by('customer_id').len();
```

which is equivalent to this native SQL:

```sql
SELECT customer_id, COUNT(1) AS len FROM orders GROUP BY customer_id;
```

Transform expressions run with normal Python privileges, and expressions
should not be run from untrusted sources.  If the transform operation
returns a Polars `DataFrame` or `Series`, the result is rendered by mycli
as tabular output.  Most other return types will be silently ignored.

Transform expressions are useful for operations such as medians which
cannot be done (or are awkward) in SQL.  Example:

```sql
SELECT * FROM orders .| df.describe();
```

## Plotting

If the dataframe transform operation returns an Altair plot, the result can
be rendered as an inline PNG in many terminals.

Example:

```sql
SELECT * FROM orders .| df['total'].plot.hist();
```

<img src="https://raw.githubusercontent.com/dbcli/mycli/main/doc/screenshots/total_histogram.png" height=400>

Image size, display protocol, and other properties can be configured in
the `[dataframe]` section of `~/.myclirc`.

## Saving

A query result, transformed `DataFrame`, or transformed `Series` can be
written directly to a Parquet file with the `.>` operator.

Save example:

```sql
SELECT * FROM orders .> orders.parquet;
```

The `.>` operator must be last, requires a `.parquet` destination, and
overwrites any existing file.  Spaces may be required around the operator.
Destination paths containing whitespace must be quoted.  A successful write
reports its destination and row count.

When `post_redirect_command` is set in `~/.myclirc`, the given command runs
after a successful Parquet save.

`.>` cannot be combined with the `\x` or `\G` special display terminators.

## Combining

Parquet saves may be combined with dataframe transforms.  Again, `.>` must
be the last operator.

Combined transform and save example:

```sql
SELECT * FROM orders .| df.group_by('customer_id').len() .> customer_counts.parquet;
```

```sql
SELECT * FROM orders .| df['order_id'] .> order_ids.parquet;
```

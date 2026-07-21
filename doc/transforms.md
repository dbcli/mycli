# Transforms with Polars Dataframes

## Installing

Install mycli with dataframe support using:

```bash
pip install --upgrade 'mycli[dataframe]'
```

or install the Polars and Altair libraries separately.

## BETA STATUS

Dataframe transforms are new and experimental.  The interface and functionality
may still change.

Here are some known limitations:

 * transforms can't be mixed with `$|` shell redirection
 * multiple transform steps are not permitted
 * the Altair library is provided, but plots can't yet be displayed
 * results from `UNION`s may be unable to be transformed

And there are inherent limitations to the post-processing model: the entire
SQL result must be transferred from the server and loaded into local memory.

## Transforming

In the interactive REPL, append the `.|` operator and a Python expression to a
single SQL statement.  The Python expression receives

 * `df`, a Polars `DataFrame`
 * `pl`, the Polars module
 * `alt`, the Altair module

Spaces may be required around the operator.

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
as tabular output; other return types currently give a warning and cannot
be displayed.

Transform expressions are useful for operations such as medians which
cannot be done (or are simply awkward) in SQL.  Example:

```sql
SELECT * FROM orders .| df.describe();
```

## Saving

A query result, transformed `DataFrame`, or transformed `Series` can be
written directly to Parquet with the `.>` operator.

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

`.>` cannot be combined with `\x`, `\G`, or `\g` special display terminators.

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

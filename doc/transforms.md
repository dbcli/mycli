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
 * composing multiple transform operations is not supported
 * results from `UNION`s may be unable to be transformed

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
SELECT * FROM employees .| df.group_by('gender').len();
```

<img src="https://raw.githubusercontent.com/dbcli/mycli/main/doc/screenshots/polars_group_by.png">

which is equivalent to this native SQL:

```sql
SELECT gender, COUNT(1) AS count FROM employees GROUP BY gender;
```

Transform expressions run with normal Python privileges, and expressions
should not be run from untrusted sources.

If the transform operation returns a Polars `DataFrame` or `Series`, or a
Python type which can be rendered as a table, the result is rendered by mycli
as tabular output.  `None` return values will be silently ignored, and other
return types will result in a warning message.

Transform expressions are useful for operations such as median or pivots which
cannot be done (or are awkward) in MySQL.  Examples:

```sql
SELECT * FROM salaries LIMIT 10000 .| df.describe();
```

<img src="https://raw.githubusercontent.com/dbcli/mycli/main/doc/screenshots/polars_describe.png">

```sql
SELECT emp_no, salary, from_date FROM salaries ORDER BY from_date, emp_no LIMIT 40 .| df.pivot('from_date', values='salary');
```

<img src="https://raw.githubusercontent.com/dbcli/mycli/main/doc/screenshots/polars_pivot.png">

## Plotting

If the dataframe transform operation returns an Altair plot, the result can
be rendered as an inline PNG in many terminals.

Example:

```sql
SELECT salary FROM salaries LIMIT 10000 .| df['salary'].plot.hist();
```

<img src="https://raw.githubusercontent.com/dbcli/mycli/main/doc/screenshots/polars_histogram.png" height=400>

Image size, display protocol, and other properties can be configured in
the `[dataframe]` section of `~/.myclirc`.

## Saving

A query result, transformed `DataFrame`, or transformed `Series` can be
written directly to a Parquet file with the `.>` operator. An Altair plot can
also be written to a file with the same operator.

Save example:

```sql
SELECT * FROM employees WHERE last_name LIKE 'A%'.> employees_a.parquet;
```

The `.>` operator must be last, requires a `.parquet`, `.png`, `.pdf`, `.svg`,
or `.html` file extension on the destination, and overwrites any existing file.

Spaces may be required around the operator.  Destination paths containing
whitespace must be quoted.  A successful write reports its destination and row
count if appropriate.

When saving a plot, the format is deduced from the file extension.

When `post_redirect_command` is set in `~/.myclirc`, the given command runs
after a successful file save.

`.>` cannot be combined with the `\x` or `\G` special display terminators.

## Combining

Parquet saves may be combined with dataframe transforms.  Again, the save
operator `.>` must be the last operator.

Combined transform and save examples:

```sql
SELECT * FROM salaries LIMIT 10000 .| df.group_by('emp_no').len(name='raises').with_columns(pl.col('raises') - 1) .> raises_counts.parquet;
```

```sql
SELECT emp_no, MAX(salary) AS current_salary FROM salaries GROUP BY emp_no .| df['current_salary'] .> current_salaries.parquet;
```

```sql
SELECT emp_no, MIN(salary) AS starting_salary FROM salaries GROUP BY emp_no .| df['starting_salary'].plot.hist() .> starting_salaries_histogram.png;
```

## Examples Note

All examples in this document are written using the [employees](https://dev.mysql.com/doc/employee/en/) sample database,
which is provided in the mycli Dockerfile:

```bash
docker run --pull=always -it ghcr.io/dbcli/mycli:latest
```

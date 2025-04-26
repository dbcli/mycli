import re

import sqlparse


class DelimiterCommand(object):
    def __init__(self):
        self._delimiter = ";"

    def _split(self, sql):
        """Temporary workaround until sqlparse.split() learns about custom
        delimiters."""

        placeholder = "\ufffc"  # unicode object replacement character

        if self._delimiter == ";":
            return sqlparse.split(sql)

        # We must find a string that original sql does not contain.
        # Most likely, our placeholder is enough, but if not, keep looking
        while placeholder in sql:
            placeholder += placeholder[0]
        sql = sql.replace(";", placeholder)
        sql = sql.replace(self._delimiter, ";")

        split = sqlparse.split(sql)

        return [stmt.replace(";", self._delimiter).replace(placeholder, ";") for stmt in split]

    def queries_iter(self, input_str):
        """Iterate over queries in the input string."""

        queries = self._split(input_str)
        while queries:
            for sql in queries:
                delimiter = self._delimiter
                sql = queries.pop(0)
                if sql.endswith(delimiter):
                    trailing_delimiter = True
                    sql = sql.strip(delimiter)
                else:
                    trailing_delimiter = False

                yield sql

                # if the delimiter was changed by the last command,
                # re-split everything, and if we previously stripped
                # the delimiter, append it to the end
                if self._delimiter != delimiter:
                    combined_statement = " ".join([sql] + queries)
                    if trailing_delimiter:
                        combined_statement += delimiter
                    queries = self._split(combined_statement)[1:]

    def set(self, arg, **_):
        """Change delimiter.

        Since `arg` is everything that follows the DELIMITER token
        after sqlparse (it may include other statements separated by
        the new delimiter), we want to set the delimiter to the first
        word of it.

        """
        match = arg and re.search(r"[^\s]+", arg)
        if not match:
            message = "Missing required argument, delimiter"
            return [(None, None, None, message)]

        delimiter = match.group()
        if delimiter.lower() == "delimiter":
            return [(None, None, None, 'Invalid delimiter "delimiter"')]

        self._delimiter = delimiter
        return [(None, None, None, "Changed delimiter to {}".format(delimiter))]

    @property
    def current(self):
        return self._delimiter

import re
from typing import IO, Generator

import sqlglot
import sqlparse

MAX_MULTILINE_BATCH_STATEMENT = 5000

DELIMITER_RE = re.compile(r'^\s*delimiter\s+(\S+)\s*$', re.IGNORECASE)


def _has_tokens(text: str) -> bool:
    try:
        return bool(sqlglot.tokenize(text, read='mysql'))
    except sqlglot.errors.TokenError:
        return True


def statements_from_filehandle(file_h: IO) -> Generator[tuple[str, int], None, None]:
    statements = ''
    line_counter = 0
    batch_counter = 0
    delimiter = ';'
    for batch_text in file_h:
        line_counter += 1
        if line_counter > MAX_MULTILINE_BATCH_STATEMENT:
            raise ValueError(f'Saw single input statement greater than {MAX_MULTILINE_BATCH_STATEMENT} lines; assuming a parsing error.')
        # DELIMITER is a client command, as in the mysql client: switch delimiters, don't send it
        delimiter_match = DELIMITER_RE.match(batch_text)
        if delimiter_match and not _has_tokens(statements):
            delimiter = delimiter_match.group(1)
            statements = ''
            line_counter = 0
            continue
        statements += batch_text
        if delimiter != ';':
            statement = statements.rstrip()
            # A custom delimiter is only recognized at the end of a line, so
            # two statements on one line are sent together as one
            if statement.endswith(delimiter):
                yield (statement[: -len(delimiter)].strip(), batch_counter)
                batch_counter += 1
                statements = ''
                line_counter = 0
            continue
        try:
            tokens = sqlglot.tokenize(statements, read='mysql')
            if not tokens:
                continue
            if tokens[-1].text == ';':
                # The advantage of sqlparse for splitting is that it preserves the input.
                # https://github.com/tobymao/sqlglot/issues/2587#issuecomment-1823109501
                for statement in sqlparse.split(statements):
                    yield (statement, batch_counter)
                    batch_counter += 1
                statements = ''
                line_counter = 0
        except sqlglot.errors.TokenError:
            continue
    if statements:
        for statement in sqlparse.split(statements):
            yield (statement, batch_counter)
            batch_counter += 1

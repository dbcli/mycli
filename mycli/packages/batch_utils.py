from typing import IO, Generator

import sqlglot

MAX_MULTILINE_BATCH_STATEMENT = 5000


def statements_from_filehandle(file_h: IO) -> Generator[tuple[str, int], None, None]:
    statements = ''
    line_counter = 0
    batch_counter = 0
    for batch_text in file_h:
        line_counter += 1
        if line_counter > MAX_MULTILINE_BATCH_STATEMENT:
            raise ValueError(f'Saw single input statement greater than {MAX_MULTILINE_BATCH_STATEMENT} lines; assuming a parsing error.')
        statements += batch_text
        try:
            tokens = sqlglot.tokenize(statements, read='mysql')
            if not tokens:
                continue
            # we don't yet handle changing the delimiter within the batch input
            if tokens[-1].text == ';':
                yield (statements, batch_counter)
                batch_counter += 1
                statements = ''
                line_counter = 0
        except sqlglot.errors.TokenError:
            continue
    if statements:
        yield (statements, batch_counter)

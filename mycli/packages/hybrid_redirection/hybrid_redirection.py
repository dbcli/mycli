from dataclasses import dataclass
import functools
import logging
import re
import shlex

import sqlglot

from mycli.compat import WIN
from mycli.packages.special.delimitercommand import DelimiterCommand
from mycli.packages.special.source import (
    parse_source_arguments,
)

logger = logging.getLogger(__name__)
delimiter_command = DelimiterCommand()
SOURCE_COMMAND_PATTERN = re.compile(r'^([/]?source|[/\\]\.)\s+', re.IGNORECASE)
SOURCE_OPTION_PATTERN = re.compile(r'(?<!\S)--(?:special|show|page|help|throttle)(?==|\s|$)', re.IGNORECASE)
SOURCE_OPTION_TERMINATOR_PATTERN = re.compile(r'(?<!\S)--(?=\s|$)')
HYBRID_OPERATOR_PATTERN = re.compile(r'\$(?:>>?|\|)')


@dataclass(frozen=True, slots=True)
class ShellRedirect:
    command: str | None
    file_operator: str | None
    filename: str | None


def tokenize_shell_suffix(suffix: str) -> list[sqlglot.Token]:
    # Shell long options are not SQL comments; preserve offsets into the original text.
    for match in re.finditer(r'\$\s*>', suffix):
        prefix = re.sub(r'--(?=\S)', '__', suffix[: match.end()])
        try:
            tokens = sqlglot.tokenize(prefix)
        except sqlglot.errors.TokenError:
            continue
        files = find_token_indices(tokens)['angle_bracket']
        if files and tokens[files[-1]].end == match.end() - 1:
            # Only an unquoted file operator switches back to SQL comment handling.
            operand = re.sub(r'(?<=\S)--', '__', suffix[match.end() :])
            return sqlglot.tokenize(prefix + operand)
    return sqlglot.tokenize(re.sub(r'--(?=\S)', '__', suffix))


def parse_shell_redirect(suffix: str) -> ShellRedirect:
    """Parse a final shell suffix independently of the SQL or transform preceding it."""
    suffix = suffix.strip().removesuffix(delimiter_command.current).rstrip()
    tokens = tokenize_shell_suffix(suffix)
    indices = find_token_indices(tokens)
    dollars = indices['true_dollar']
    pipes = indices['pipe']
    files = indices['angle_bracket']
    if not dollars or tokens[dollars[0]].start != 0:
        raise ValueError('Shell redirection requires an operator.')
    if len(files) > 1 or (files and pipes and pipes[-1] > files[0]):
        raise ValueError('Shell file redirection must be last and occur only once.')
    if WIN and len(pipes) > 1:
        raise ValueError('Multiple shell pipes are not supported on Windows.')

    command_parts: list[str] = []
    for position, dollar in enumerate(dollars):
        operator = tokens[dollar + 1]
        next_dollar = dollars[position + 1] if position + 1 < len(dollars) else len(tokens)
        if operator.token_type == sqlglot.TokenType.PIPE:
            end = len(suffix[: tokens[next_dollar - 1].end + 1].removesuffix(delimiter_command.current).rstrip())
            last_token = next(token for token in reversed(tokens[:next_dollar]) if token.start < end)
            part = suffix[operator.end + 1 : min(last_token.end + 1, end)].strip()
            if not part:
                raise ValueError('Shell pipes require a command.')
            command_parts.append(part)

    filename = None
    file_operator = None
    if files:
        operator = tokens[files[0]]
        end = len(suffix[: tokens[-1].end + 1].removesuffix(delimiter_command.current).rstrip())
        last_token = next(token for token in reversed(tokens) if token.start < end)
        operand = suffix[operator.end + 1 : min(last_token.end + 1, end)].strip()
        file_operator = '>'
        if operand.startswith('>'):
            file_operator = '>>'
            operand = operand[1:].strip()
        filename = parse_redirect_filename(operand)
        if not filename:
            raise ValueError('Shell file redirection requires one filename; quote filenames containing spaces.')
    command = ' | '.join(command_parts) or None
    if invalid_shell_part(filename, command):
        raise ValueError('Invalid shell redirection.')
    return ShellRedirect(command, file_operator, filename)


def tokenize_command(command: str) -> list[sqlglot.Token]:
    """Tokenize a command without treating source options as SQL comments."""
    if SOURCE_COMMAND_PATTERN.match(command):
        operator_match = HYBRID_OPERATOR_PATTERN.search(command)
        source_end = operator_match.start() if operator_match is not None else len(command)
        source_part = command[:source_end]
        terminator_match = SOURCE_OPTION_TERMINATOR_PATTERN.search(source_part)
        options_end = terminator_match.start() if terminator_match is not None else len(source_part)
        masked_options = SOURCE_OPTION_PATTERN.sub(lambda match: match.group().replace('-', '_'), source_part[:options_end])
        command = masked_options + source_part[options_end:] + command[source_end:]
    return sqlglot.tokenize(command)


def find_token_indices(tokens: list[sqlglot.Token]) -> dict[str, list[int]]:
    token_indices: dict[str, list[int]] = {
        'raw_dollar': [],
        'true_dollar': [],
        'angle_bracket': [],
        'pipe': [],
    }

    for i, tok in enumerate(tokens):
        if tok.token_type == sqlglot.TokenType.VAR and tok.text == '$':
            token_indices['raw_dollar'].append(i)
            continue
        if tok.token_type == sqlglot.TokenType.GT and (i - 1) in token_indices['raw_dollar']:
            token_indices['angle_bracket'].append(i)
            continue
        if tok.token_type == sqlglot.TokenType.PIPE and (i - 1) in token_indices['raw_dollar']:
            token_indices['pipe'].append(i)
            continue

    for i in token_indices['raw_dollar']:
        if (i + 1) in token_indices['angle_bracket'] or (i + 1) in token_indices['pipe']:
            token_indices['true_dollar'].append(i)

    return token_indices


def find_sql_part(
    command: str,
    tokens: list[sqlglot.Token],
    true_dollar_indices: list[int],
):
    leftmost_dollar_pos = tokens[true_dollar_indices[0]].start
    sql_part = command[0:leftmost_dollar_pos].strip().removesuffix(delimiter_command.current).rstrip()
    if SOURCE_COMMAND_PATTERN.match(sql_part):
        source_arg_str = SOURCE_COMMAND_PATTERN.sub('', sql_part)
        try:
            filename = parse_source_arguments(source_arg_str).filename
        except ValueError:
            return ''
        if not filename:
            return ''
        return sql_part
    try:
        statements = sqlglot.parse(sql_part, read='mysql')
    except sqlglot.errors.ParseError:
        return ''
    if len(statements) != 1:
        # buglet: the statement count doesn't respect a custom delimiter
        return ''
    return sql_part


def find_command_tokens(
    tokens: list[sqlglot.Token],
    true_dollar_indices: list[int],
) -> list[sqlglot.Token]:
    command_part_tokens = []

    for i, tok in enumerate(tokens):
        if i < true_dollar_indices[0]:
            continue
        if i in true_dollar_indices:
            continue
        command_part_tokens.append(tok)

    if command_part_tokens:
        _operator = command_part_tokens.pop(0)

    return command_part_tokens


def find_file_tokens(
    tokens: list[sqlglot.Token],
    angle_bracket_indices: list[int],
) -> tuple[list[sqlglot.Token], int, str | None]:
    file_part_tokens: list[sqlglot.Token] = []
    file_part_index = len(tokens)

    if not angle_bracket_indices:
        return file_part_tokens, file_part_index, None

    file_part_tokens = tokens[angle_bracket_indices[-1] :]
    file_part_index = angle_bracket_indices[-1]

    file_operator_part = file_part_tokens.pop(0).text
    if file_operator_part == '>' and file_part_tokens[0].token_type == sqlglot.TokenType.GT:
        file_part_tokens.pop(0)
        file_operator_part = '>>'

    return file_part_tokens, file_part_index, file_operator_part


def assemble_tokens(tokens: list[sqlglot.Token]) -> str:
    assembled_string = ' ' * (tokens[-1].end + 10)
    for tok in tokens:
        if tok.token_type == sqlglot.TokenType.IDENTIFIER:
            text = f'"{tok.text}"'
            offset = 2
        elif tok.token_type == sqlglot.TokenType.STRING:
            text = f"'{tok.text}'"
            offset = 2
        else:
            text = tok.text
            offset = 0
        assembled_string = assembled_string[0 : tok.start] + text + assembled_string[tok.end + offset :]
    return assembled_string.strip().removesuffix(delimiter_command.current).rstrip()


def invalid_shell_part(
    file_part: str | None,
    command_part: str | None,
) -> bool:
    if file_part and '>' in file_part:
        return True

    if not file_part and not command_part:
        return True

    return False


def parse_redirect_filename(file_part: str | None) -> str | None:
    """Return one unquoted redirect filename, or None for an invalid operand."""
    if file_part is None or not file_part:
        return None
    if file_part[0] not in ('\'', '"'):
        return file_part if not any(character.isspace() for character in file_part) else None
    try:
        parts = shlex.split(file_part)
    except ValueError:
        return None
    return parts[0] if len(parts) == 1 else None


# todo there are still corner cases combining custom delimiters, caching, and redirection
@functools.lru_cache(maxsize=1)
def get_redirect_components(command: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Get the parts of a hybrid shell-style redirect command."""

    try:
        tokens = tokenize_command(command)
    except sqlglot.errors.TokenError:
        return None, None, None, None

    token_indices = find_token_indices(tokens)

    if not token_indices['true_dollar']:
        return None, None, None, None

    if len(token_indices['angle_bracket']) > 1:
        return None, None, None, None

    if WIN and len(token_indices['pipe']) > 1:
        # how to give better feedback here?
        return None, None, None, None

    if token_indices['angle_bracket'] and token_indices['pipe']:
        if token_indices['pipe'][-1] > token_indices['angle_bracket'][-1]:
            return None, None, None, None

    sql_part = find_sql_part(
        command,
        tokens,
        token_indices['true_dollar'],
    )
    if not sql_part:
        return None, None, None, None

    try:
        redirect = parse_shell_redirect(command[tokens[token_indices['true_dollar'][0]].start :])
    except (ValueError, sqlglot.errors.TokenError):
        return None, None, None, None
    command_part, file_operator_part, file_part = redirect.command, redirect.file_operator, redirect.filename

    logger.debug('redirect parse sql_part: "{}"'.format(sql_part))
    logger.debug('redirect parse command_part: "{}"'.format(command_part))
    logger.debug('redirect parse file_operator_part: "{}"'.format(file_operator_part))
    logger.debug('redirect parse file_part: "{}"'.format(file_part))

    return sql_part, command_part, file_operator_part, file_part


def is_redirect_command(command: str) -> bool:
    """Is this a shell-style redirect to command or file?

    :param command: string

    """
    sql_part, _command_part, _file_operator_part, _file_part = get_redirect_components(command)
    return bool(sql_part)

from __future__ import print_function
import re
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Function
from sqlparse.tokens import Keyword, DML, Punctuation

cleanup_regex = {
        # This matches only alphanumerics and underscores.
        'alphanum_underscore': re.compile(r'(\w+)$'),
        # This matches everything except spaces, parens, colon, and comma
        'many_punctuations': re.compile(r'([^():,\s]+)$'),
        # This matches everything except spaces, parens, colon, comma, and period
        'most_punctuations': re.compile(r'([^\.():,\s]+)$'),
        # This matches everything except a space.
        'all_punctuations': re.compile('([^\s]+)$'),
        }

def last_word(text, include='alphanum_underscore'):
    """
    Find the last word in a sentence.

    >>> last_word('abc')
    'abc'
    >>> last_word(' abc')
    'abc'
    >>> last_word('')
    ''
    >>> last_word(' ')
    ''
    >>> last_word('abc ')
    ''
    >>> last_word('abc def')
    'def'
    >>> last_word('abc def ')
    ''
    >>> last_word('abc def;')
    ''
    >>> last_word('bac $def')
    'def'
    >>> last_word('bac $def', include='most_punctuations')
    '$def'
    >>> last_word('bac \def', include='most_punctuations')
    '\\\\def'
    >>> last_word('bac \def;', include='most_punctuations')
    '\\\\def;'
    >>> last_word('bac::def', include='most_punctuations')
    'def'
    """

    if not text:   # Empty string
        return ''

    if text[-1].isspace():
        return ''
    else:
        regex = cleanup_regex[include]
        matches = regex.search(text)
        if matches:
            return matches.group(0)
        else:
            return ''


def find_prev_keyword(sql):
    """ Find the last sql keyword in an SQL statement

    Returns the value of the last keyword, and the text of the query with
    everything after the last keyword stripped
    """
    if not sql.strip():
        return None, ''

    parsed = sqlparse.parse(sql)[0]
    flattened = list(parsed.flatten())

    logical_operators = ('AND', 'OR', 'NOT', 'BETWEEN')

    for t in reversed(flattened):
        if t.value == '(' or (t.is_keyword and (
                              t.value.upper() not in logical_operators)):
            # Find the location of token t in the original parsed statement
            # We can't use parsed.token_index(t) because t may be a child token
            # inside a TokenList, in which case token_index thows an error
            # Minimal example:
            #   p = sqlparse.parse('select * from foo where bar')
            #   t = list(p.flatten())[-3]  # The "Where" token
            #   p.token_index(t)  # Throws ValueError: not in list
            idx = flattened.index(t)

            # Combine the string values of all tokens in the original list
            # up to and including the target keyword token t, to produce a
            # query string with everything after the keyword token removed
            text = ''.join(tok.value for tok in flattened[:idx+1])
            return t, text

    return None, ''


if __name__ == '__main__':
    sql = 'select * from (select t. from tabl t'
    print(extract_tables(sql))

from mycli.packages.completion_engine import suggest_type
from test_completion_engine import sorted_dicts

def test_u_suggests_databases():
    suggestions = suggest_type('\\u ', '\\u ')
    assert sorted_dicts(suggestions) == sorted_dicts([
            {'type': 'database'}])

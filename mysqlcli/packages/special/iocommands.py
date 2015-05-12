"""List of special commands supported by MySQL that doesn't touch the
database."""
def extract_sql_expanded(sql):
    if sql.endswith('\\G'):
        return sql.rsplit('\\G', 1)[0]
    return sql

expanded_output = False
def is_expanded_output():
    return expanded_output

def set_expanded_output(val):
    global expanded_output
    expanded_output = val

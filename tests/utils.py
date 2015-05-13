import pytest
import pymysql
from mysqlcli.main import format_output

# TODO: should this be somehow be divined from environment?
USER, HOST = 'root', 'localhost'

def db_connection(dbname=None):
    conn = pymysql.connect(user=USER, host=HOST, database=dbname)
    conn.autocommit = True
    return conn

try:
    db_connection()
    CAN_CONNECT_TO_DB = True
except:
    CAN_CONNECT_TO_DB = False

dbtest = pytest.mark.skipif(
    not CAN_CONNECT_TO_DB,
    reason="Need a mysql instance at localhost accessible by user 'root'")


def create_db(dbname):
    with db_connection().cursor() as cur:
        try:
            cur.execute('''DROP DATABASE IF EXISTS _test_db''')
            cur.execute('''CREATE DATABASE _test_db''')
        except:
            pass

def run(executor, sql, join=False):
    " Return string output for the sql to be run "
    result = []
    for title, rows, headers, status in executor.run(sql):
        result.extend(format_output(title, rows, headers, status, 'psql'))
    if join:
        result = '\n'.join(result)
    return result

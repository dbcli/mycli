from os import getenv

import pymysql
import pytest

from mycli.main import special

PASSWORD = getenv('PYTEST_PASSWORD')
USER = getenv('PYTEST_USER', 'root')
HOST = getenv('PYTEST_HOST', 'localhost')
PORT = getenv('PYTEST_PORT', 3306)
CHARSET = getenv('PYTEST_CHARSET', 'utf8')


def db_connection(dbname=None):
    conn = pymysql.connect(user=USER, host=HOST, port=PORT, database=dbname,
                           password=PASSWORD, charset=CHARSET,
                           local_infile=False)
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


def run(executor, sql, rows_as_list=True):
    """Return string output for the sql to be run."""
    result = []

    for title, rows, headers, status in executor.run(sql):
        rows = list(rows) if (rows_as_list and rows) else rows
        result.append({'title': title, 'rows': rows, 'headers': headers,
                       'status': status})

    return result


def set_expanded_output(is_expanded):
    """Pass-through for the tests."""
    return special.set_expanded_output(is_expanded)


def is_expanded_output():
    """Pass-through for the tests."""
    return special.is_expanded_output()

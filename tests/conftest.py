import pytest
from utils import (HOST, USER, create_db, db_connection)
import mycli.sqlexecute


@pytest.yield_fixture(scope="function")
def connection():
    create_db('_test_db')
    connection = db_connection('_test_db')
    yield connection

    connection.close()


@pytest.fixture
def cursor(connection):
    with connection.cursor() as cur:
        return cur


@pytest.fixture
def executor(connection):
    return mycli.sqlexecute.SQLExecute(database='_test_db', user=USER,
            host=HOST, password=None, port=None)

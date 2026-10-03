# type: ignore

import pytest

from mycli.packages.execution import sql_execute
from test.utils import CHARACTER_SET, DATABASE, HOST, PASSWORD, PORT, USER, create_db, db_connection


@pytest.fixture(scope="function")
def connection():
    create_db(DATABASE)
    connection = db_connection(DATABASE)
    yield connection

    connection.close()


@pytest.fixture
def cursor(connection):
    with connection.cursor() as cur:
        return cur


@pytest.fixture
def executor(connection):
    return sql_execute.SQLExecute(
        database=DATABASE,
        user=USER,
        host=HOST,
        password=PASSWORD,
        port=PORT,
        socket=None,
        character_set=CHARACTER_SET,
        local_infile=False,
        ssl=None,
    )

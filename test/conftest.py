import pytest

import mycli.sqlexecute
from test.utils import CHARSET, HOST, PASSWORD, PORT, SSH_HOST, SSH_PORT, SSH_USER, USER, create_db, db_connection


@pytest.fixture(scope="function")
def connection():
    create_db("mycli_test_db")
    connection = db_connection("mycli_test_db")
    yield connection

    connection.close()


@pytest.fixture
def cursor(connection):
    with connection.cursor() as cur:
        return cur


@pytest.fixture
def executor(connection):
    return mycli.sqlexecute.SQLExecute(
        database="mycli_test_db",
        user=USER,
        host=HOST,
        password=PASSWORD,
        port=PORT,
        socket=None,
        charset=CHARSET,
        local_infile=False,
        ssl=None,
        ssh_user=SSH_USER,
        ssh_host=SSH_HOST,
        ssh_port=SSH_PORT,
        ssh_password=None,
        ssh_key_filename=None,
    )

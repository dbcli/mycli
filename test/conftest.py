import pytest

from mycli.packages.ssh_client import create_ssh_client
from .utils import (HOST, USER, PASSWORD, PORT, CHARSET, create_db,
                    db_connection, SSH_USER, SSH_HOST, SSH_PORT)
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
    if SSH_HOST:
        ssh_client = create_ssh_client(SSH_HOST, SSH_PORT, SSH_USER)
    else:
        ssh_client = None

    return mycli.sqlexecute.SQLExecute(
        database='_test_db', user=USER,
        host=HOST, password=PASSWORD, port=PORT, socket=None, charset=CHARSET,
        local_infile=False, ssl=None, ssh_client=ssh_client
    )

# type: ignore

import pymysql

from mycli.constants import DEFAULT_CHARSET, DEFAULT_HOST, DEFAULT_PORT


def create_db(hostname=DEFAULT_HOST, port=DEFAULT_PORT, username=None, password=None, dbname=None):
    """Create test database.

    :param hostname: string
    :param port: int
    :param username: string
    :param password: string
    :param dbname: string
    :return:

    """
    cn = pymysql.connect(
        host=hostname, port=port, user=username, password=password, charset=DEFAULT_CHARSET, cursorclass=pymysql.cursors.DictCursor
    )

    with cn.cursor() as cr:
        cr.execute("drop database if exists " + dbname)
        cr.execute("create database " + dbname)

    cn.close()

    cn = create_cn(hostname, port, password, username, dbname)
    return cn


def create_cn(hostname, port, password, username, dbname):
    """Open connection to database.

    :param hostname:
    :param port:
    :param password:
    :param username:
    :param dbname: string
    :return: psycopg2.connection

    """
    cn = pymysql.connect(
        host=hostname,
        port=port,
        user=username,
        password=password,
        db=dbname,
        charset=DEFAULT_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
    )

    return cn


def drop_db(hostname=DEFAULT_HOST, port=DEFAULT_PORT, username=None, password=None, dbname=None):
    """Drop database.

    :param hostname: string
    :param port: int
    :param username: string
    :param password: string
    :param dbname: string

    """
    cn = pymysql.connect(
        host=hostname,
        port=port,
        user=username,
        password=password,
        db=dbname,
        charset=DEFAULT_CHARSET,
        cursorclass=pymysql.cursors.DictCursor,
    )

    with cn.cursor() as cr:
        cr.execute("drop database if exists " + dbname)

    close_cn(cn)


def close_cn(cn=None):
    """Close connection.

    :param connection: pymysql.connection

    """
    if cn:
        cn.close()

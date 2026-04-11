HOME_URL = 'https://mycli.net'
REPO_URL = 'https://github.com/dbcli/mycli'
DOCS_URL = f'{HOME_URL}/docs'
ISSUES_URL = f'{REPO_URL}/issues'

DEFAULT_CHARSET = 'utf8mb4'
DEFAULT_DATABASE = 'mysql'
DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 3306
DEFAULT_USER = 'root'

TEST_DATABASE = 'mycli_test_db'

DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 25

# MySQL error codes not available in pymysql.constants.ER
ER_MUST_CHANGE_PASSWORD_LOGIN = 1862
ER_MUST_CHANGE_PASSWORD = 1820

EMPTY_PASSWORD_FLAG_SENTINEL = -1

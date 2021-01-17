import os
import sys
import requests

archive_name = os.getenv('MYSQL_ARCHIVE_NAME')
if not archive_name:
    print('Environment variable MYSQL_ARCHIVE_NAME not set')
    sys.exit(1)

print(f'downloading {archive_name}...')
file_name = f'{archive_name}.zip'
resp = requests.get(f'https://cdn.mysql.com//Downloads/MySQL-8.0/{archive_name}.zip')
with open(file_name, 'wb') as f:
    f.write(resp.content)
print(f'done, written to {os.path.join(os.getcwd(), file_name)}')


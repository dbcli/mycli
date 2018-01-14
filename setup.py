#!/usr/bin/env python

import re
import ast
from setuptools import setup, find_packages

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('mycli/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

description = 'CLI for MySQL Database. With auto-completion and syntax highlighting.'

install_requirements = [
    'click >= 4.1',
    'Pygments >= 1.6',
    'prompt_toolkit>=1.0.10,<1.1.0',
    'PyMySQL >= 0.6.7',
    'sqlparse>=0.2.2,<0.3.0',
    'configobj >= 5.0.5',
    'cryptography >= 1.0.0',
    'cli_helpers[styles] >= 1.0.1',
]

setup(
    name='mycli',
    author='Mycli Core Team',
    author_email='mycli-dev@googlegroups.com',
    version=version,
    url='http://mycli.net',
    packages=find_packages(),
    package_data={'mycli': ['myclirc', 'AUTHORS', 'SPONSORS']},
    description=description,
    long_description=description,
    install_requires=install_requirements,
    entry_points={
        'console_scripts': ['mycli = mycli.main:cli'],
        'distutils.commands': [
            'lint = tasks:lint',
            'test = tasks:test',
        ],
    },
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: SQL',
        'Topic :: Database',
        'Topic :: Database :: Front-Ends',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)

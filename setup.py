#!/usr/bin/env python

import ast
import re
import subprocess
import sys

from setuptools import Command, find_packages, setup
from setuptools.command.test import test as TestCommand

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('mycli/__init__.py') as f:
    version = ast.literal_eval(_version_re.search(
        f.read()).group(1))

description = 'CLI for MySQL Database. With auto-completion and syntax highlighting.'

install_requirements = [
    'click >= 7.0',
    'Pygments >= 1.6',
    'prompt_toolkit>=3.0.6,<4.0.0',
    'PyMySQL >= 0.9.2',
    'sqlparse>=0.3.0,<0.4.0',
    'configobj >= 5.0.5',
    'cryptography >= 1.0.0',
    'cli_helpers[styles] >= 2.0.1',
    'pyperclip >= 1.8.1'
]


class lint(Command):
    description = 'check code against PEP 8 (and fix violations)'

    user_options = [
        ('branch=', 'b', 'branch/revision to compare against (e.g. master)'),
        ('fix', 'f', 'fix the violations in place'),
        ('error-status', 'e', 'return an error code on failed PEP check'),
    ]

    def initialize_options(self):
        """Set the default options."""
        self.branch = 'master'
        self.fix = False
        self.error_status = True

    def finalize_options(self):
        pass

    def run(self):
        cmd = 'pep8radius {}'.format(self.branch)
        if self.fix:
            cmd += ' --in-place'
        if self.error_status:
            cmd += ' --error-status'
        sys.exit(subprocess.call(cmd, shell=True))


class test(TestCommand):

    user_options = [
        ('pytest-args=', 'a', 'Arguments to pass to pytest'),
        ('behave-args=', 'b', 'Arguments to pass to pytest')
    ]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ''
        self.behave_args = '--no-capture'

    def run_tests(self):
        unit_test_errno = subprocess.call(
            'pytest test/ ' + self.pytest_args,
            shell=True
        )
        cli_errno = subprocess.call(
            'behave test/features ' + self.behave_args,
            shell=True
        )
        subprocess.run(['git', 'checkout', '--', 'test/myclirc'], check=False)
        sys.exit(unit_test_errno or cli_errno)


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
    },
    cmdclass={'lint': lint, 'test': test},
    python_requires=">=3.6",
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: SQL',
        'Topic :: Database',
        'Topic :: Database :: Front-Ends',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    extras_require={
        'ssh':  ['paramiko'],
    },
)

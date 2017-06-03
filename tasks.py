# -*- coding: utf-8 -*-
"""Common development tasks for setup.py to use."""

import re
import subprocess
import sys

from setuptools import Command


class BaseCommand(Command, object):
    """The base command for project tasks."""

    user_options = []

    default_cmd_options = ('verbose', 'quiet', 'dry_run')

    def __init__(self, *args, **kwargs):
        super(BaseCommand, self).__init__(*args, **kwargs)
        self.verbose = False

    def initialize_options(self):
        """Override the distutils abstract method."""
        pass

    def finalize_options(self):
        """Override the distutils abstract method."""
        # Distutils uses incrementing integers for verbosity.
        self.verbose = bool(self.verbose)

    def call_and_exit(self, cmd, shell=True):
        """Run the *cmd* and exit with the proper exit code."""
        sys.exit(subprocess.call(cmd, shell=shell))

    def call_in_sequence(self, cmds, shell=True):
        """Run multiple commmands in a row, exiting if one fails."""
        for cmd in cmds:
            if subprocess.call(cmd, shell=shell) == 1:
                sys.exit(1)

    def apply_options(self, cmd, options=()):
        """Apply command-line options."""
        for option in (self.default_cmd_options + options):
            cmd = self.apply_option(cmd, option,
                                    active=getattr(self, option, False))
        return cmd

    def apply_option(self, cmd, option, active=True):
        """Apply a command-line option."""
        return re.sub(r'{{{}\:(?P<option>[^}}]*)}}'.format(option),
                      '\g<option>' if active else '', cmd)


class lint(BaseCommand):
    """A PEP 8 lint command that optionally fixes violations."""

    description = 'check code against PEP 8 (and fix violations)'

    user_options = [
        ('branch=', 'b', 'branch or revision to compare against (e.g. master)'),
        ('fix', 'f', 'fix the violations in place')
    ]

    def initialize_options(self):
        """Set the default options."""
        self.branch = 'master'
        self.fix = False
        super(lint, self).initialize_options()

    def run(self):
        """Run the linter."""
        cmd = 'pep8radius {branch} {{fix: --in-place}}{{verbose: -vv}}'
        cmd = cmd.format(branch=self.branch)
        self.call_and_exit(self.apply_options(cmd, ('fix', )))


class test(BaseCommand):
    """Run the test suites for this project."""

    description = 'run the test suite'

    user_options = [
        ('all', 'a', 'test against all supported versions of Python'),
        ('coverage', 'c', 'measure test coverage')
    ]

    unit_test_cmd = ('py.test{quiet: -q}{verbose: -v}{dry_run: --setup-only}'
                     '{coverage: --cov-report= --cov=mycli}')
    cli_test_cmd = 'behave{quiet: -q}{verbose: -v}{dry_run: -d} test/features'
    test_all_cmd = 'tox{verbose: -v}{dry_run: --notest}'
    coverage_cmd = 'coverage combine && coverage report'

    def initialize_options(self):
        """Set the default options."""
        self.all = False
        self.coverage = False
        super(test, self).initialize_options()

    def run(self):
        """Run the test suites."""
        if self.all:
            cmd = self.apply_options(self.test_all_cmd)
            self.call_and_exit(cmd)
        else:
            cmds = (self.apply_options(self.unit_test_cmd, ('coverage', )),
                    self.apply_options(self.cli_test_cmd))
            if self.coverage:
                cmds += (self.apply_options(self.coverage_cmd), )
            self.call_in_sequence(cmds)

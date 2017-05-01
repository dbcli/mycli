# -*- coding: utf-8
from __future__ import unicode_literals

import re


def expect_exact(context, expected, timeout, ignore_before=False):
    try:
        context.cli.expect_exact(expected, timeout=timeout)
        if not ignore_before:
            assert context.cli.before == ""
    except:
        # Strip color codes out of the output.
        actual = re.sub(r'\x1b\[([0-9A-Za-z;?])+[m|K]?',
                        '', context.cli.before)
        raise Exception('Expected:\n---\n{0!r}\n---\n\nActual:\n---\n{1!r}\n---'.format(
            expected,
            actual))


def expect_pager(context, expected, timeout):
    expect_exact(context, "{0}\r\n{1}{0}\r\n".format(
        context.conf['pager_boundary'], expected), timeout=timeout)

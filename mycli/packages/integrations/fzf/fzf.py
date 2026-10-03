"""Inspired by
https://github.com/nk412/pyfzf
and the fork
https://github.com/purarue/pyfzf

This code is trivially short and very far from the originals, but the MIT license
header from pyfzf is included anyway.
"""

# Portions Copyright (c) 2022 Nagarjuna Kumarappan
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from shutil import which
import subprocess
from typing import Any, Iterable

DELIMITER = '\x00'


class Fzf:
    def __init__(
        self,
        executable: str = 'fzf',
    ):
        self.executable: str | None = executable

        if not which(executable):
            self.executable = None

    def is_available(self) -> bool:
        return self.executable is not None

    def prompt(
        self,
        items: Iterable[Any],
        options: list[str] | None = None,
    ) -> str | None:
        options_final = ['--read0', '--print0'] + (options or [])

        fzf_process = subprocess.Popen(
            [self.executable or 'fzf', *options_final],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding='utf-8',
        )

        assert fzf_process.stdin is not None, 'Error creating fzf input stream'
        try:
            for item in items:
                fzf_process.stdin.write(str(item) + DELIMITER)
        except BrokenPipeError:
            pass

        stdout_str, _stderr_str = fzf_process.communicate()

        if stdout_str:
            # in mycli there is no meaning for multiple selection, so
            # just return the first item
            return stdout_str.split(DELIMITER)[0]

        return None

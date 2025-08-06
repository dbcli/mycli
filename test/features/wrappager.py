#!/usr/bin/env python

import sys


def wrappager(boundary: str) -> None:
    print(boundary)
    while 1:
        buf = sys.stdin.read(2048)
        if not buf:
            break
        sys.stdout.write(buf)
    print(boundary)


if __name__ == "__main__":
    wrappager("---boundary---")

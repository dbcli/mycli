import sys
collect_ignore = [
    "setup.py",
    "mycli/magic.py",
    "mycli/packages/parseutils.py",
]
if sys.version_info[0] > 2:
    collect_ignore.extend([
        "mycli/packages/counter.py",
        "mycli/packages/ordereddict.py",
    ])

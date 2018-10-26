# -*- coding: utf-8
from __future__ import unicode_literals
from mycli.encodingutils import text_type
import os


def list_path(root_dir):
    """List directory if exists.

    :param dir: str
    :return: list

    """
    res = []
    if os.path.isdir(root_dir):
        for name in os.listdir(root_dir):
            res.append(name)
    return res


def complete_path(curr_dir, last_dir):
    """Return the path to complete that matches the last entered component.

    If the last entered component is ~, expanded path would not
    match, so return all of the available paths.

    :param curr_dir: str
    :param last_dir: str
    :return: str

    """
    if not last_dir or curr_dir.startswith(last_dir):
        return curr_dir
    elif last_dir == '~':
        return os.path.join(last_dir, curr_dir)


def parse_path(root_dir):
    """Split path into head and last component for the completer.

    Also return position where last component starts.

    :param root_dir: str path
    :return: tuple of (string, string, int)

    """
    base_dir, last_dir, position = '', '', 0
    if root_dir:
        base_dir, last_dir = os.path.split(root_dir)
        position = -len(last_dir) if last_dir else 0
    return base_dir, last_dir, position


def suggest_path(root_dir):
    """List all files and subdirectories in a directory.

    If the directory is not specified, suggest root directory,
    user directory, current and parent directory.

    :param root_dir: string: directory to list
    :return: list

    """
    if not root_dir:
        return [text_type(os.path.abspath(os.sep)), text_type('~'), text_type(os.curdir), text_type(os.pardir)]

    if '~' in root_dir:
        root_dir = text_type(os.path.expanduser(root_dir))

    if not os.path.exists(root_dir):
        root_dir, _ = os.path.split(root_dir)

    return list_path(root_dir)


def dir_path_exists(path):
    """Check if the directory path exists for a given file.

    For example, for a file /home/user/.cache/mycli/log, check if
    /home/user/.cache/mycli exists.

    :param str path: The file path.
    :return: Whether or not the directory path exists.

    """
    return os.path.exists(os.path.dirname(path))

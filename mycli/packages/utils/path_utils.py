import os
import platform

DEFAULT_SOCKET_DIRS: list[str] = []
if os.name == "posix":
    if platform.system() == "Darwin":
        DEFAULT_SOCKET_DIRS = ["/tmp"]
    else:
        DEFAULT_SOCKET_DIRS = ["/var/run", "/var/lib"]


def list_path(root_dir: str, *, sql_only: bool = True) -> list[str]:
    """List directory if exists.

    :param root_dir: str
    :return: list

    """
    files = []
    dirs = []
    if not os.path.isdir(root_dir):
        return []
    for name in sorted(os.listdir(root_dir)):
        if name.startswith('.'):
            continue
        elif os.path.isdir(os.path.join(root_dir, name)):
            dirs.append(f'{name}/')
        elif not sql_only or name.lower().endswith('.sql'):
            files.append(name)
    return files + dirs


def complete_path(curr_dir: str, last_dir: str) -> str:
    """Return the path to complete that matches the last entered component.

    If the last entered component is ~, expanded path would not
    match, so return all of the available paths.

    :param curr_dir: str
    :param last_dir: str
    :return: str

    """
    if not last_dir or curr_dir.startswith(last_dir):
        return curr_dir
    elif last_dir == "~":
        return os.path.join(last_dir, curr_dir)
    else:
        return ''


def parse_path(root_dir: str) -> tuple[str, str, int]:
    """Split path into head and last component for the completer.

    Also return position where last component starts.

    :param root_dir: str path
    :return: tuple of (string, string, int)

    """
    base_dir, last_dir, position = "", "", 0
    if root_dir:
        base_dir, last_dir = os.path.split(root_dir)
        position = -len(last_dir) if last_dir else 0
    return base_dir, last_dir, position


def suggest_path(root_dir: str, *, sql_only: bool = True) -> list[str]:
    """List all files and subdirectories in a directory.

    If the directory is not specified, suggest root directory,
    user directory, current and parent directory.

    :param root_dir: string: directory to list
    :return: list

    """
    if not root_dir:
        return [
            os.path.abspath(os.sep),
            "~",
            os.curdir,
            os.pardir,
            *list_path(os.curdir, sql_only=sql_only),
        ]

    if root_dir[0] not in ('/', '~') and root_dir[0:2] != './' and not os.path.dirname(root_dir):
        return list_path(os.curdir, sql_only=sql_only)

    if "~" in root_dir:
        root_dir = os.path.expanduser(root_dir)

    if not os.path.exists(root_dir):
        root_dir, _ = os.path.split(root_dir)

    return list_path(root_dir, sql_only=sql_only)


def suggest_path_by_prefix(root_dir: str, *, sql_only: bool = True) -> list[str]:
    """Complete each slash-separated component of a pathname by prefix."""
    drive, path = os.path.splitdrive(root_dir)
    if drive and path.startswith('/'):
        search_root = f'{drive}{os.sep}'
        display_root = f'{drive}/'
        path = path[1:]
    elif path.startswith('/'):
        search_root = os.path.abspath(os.sep)
        display_root = '/'
        path = path[1:]
    elif path.startswith('~/'):
        search_root = os.path.expanduser('~')
        display_root = '~/'
        path = path[2:]
    else:
        parent_prefix = ''
        while path.startswith('../'):
            parent_prefix += '../'
            path = path[3:]
        if parent_prefix:
            search_root = parent_prefix.rstrip('/')
            display_root = parent_prefix
        elif path.startswith('./'):
            search_root = os.curdir
            display_root = './'
            path = path[2:]
        else:
            search_root = os.curdir
            display_root = ''

    components = [component for component in path.split('/') if component]
    if not components or path.endswith('/'):
        components.append('')

    locations = [(search_root, display_root)]
    for component in components[:-1]:
        next_locations = []
        for directory, display_prefix in locations:
            for name in list_path(directory, sql_only=sql_only):
                if name.endswith('/') and name[:-1].startswith(component):
                    next_locations.append((
                        os.path.join(directory, name[:-1]),
                        f'{display_prefix}{name}',
                    ))
        locations = next_locations
        if not locations:
            return []

    last_component = components[-1]
    files: list[str] = []
    dirs: list[str] = []
    for directory, display_prefix in locations:
        for name in list_path(directory, sql_only=sql_only):
            if name.rstrip('/').startswith(last_component):
                suggestion = f'{display_prefix}{name}'
                (dirs if name.endswith('/') else files).append(suggestion)
    return files + dirs


def dir_path_exists(path: str) -> bool:
    """Check if the directory path exists for a given file.

    For example, for a file /home/user/.cache/mycli/log, check if
    /home/user/.cache/mycli exists.

    :param str path: The file path.
    :return: Whether or not the directory path exists.

    """
    return os.path.exists(os.path.dirname(path))


def guess_socket_location() -> str | None:
    """Try to guess the location of the default mysql socket file."""
    socket_dirs = filter(os.path.exists, DEFAULT_SOCKET_DIRS)
    for directory in socket_dirs:
        for r, dirs, files in os.walk(directory, topdown=True):
            for filename in files:
                name, ext = os.path.splitext(filename)
                if name.startswith("mysql") and name != "mysqlx" and ext in (".socket", ".sock"):
                    return os.path.join(r, filename)
            dirs[:] = [d for d in dirs if d.startswith("mysql")]
    return None

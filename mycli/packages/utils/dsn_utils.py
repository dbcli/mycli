from __future__ import annotations

import logging
import os
from typing import Any

from mycli.config import log, read_config_file

logger = logging.getLogger(__name__)
INVALID_DSN_ALIAS_ERROR = 'Error: DSN aliases cannot start with a dash.'


def is_valid_dsn_alias(alias: str) -> bool:
    return not alias.startswith('-')


def merge_shared_dsns(config: Any, shared_dsns_file: str | None) -> None:
    if not shared_dsns_file:
        return

    shared_dsns_file = os.path.expanduser(shared_dsns_file)
    if not os.path.isabs(shared_dsns_file):
        log(logger, logging.WARNING, f"Shared DSNs file path must be absolute: '{shared_dsns_file}'.")
        return
    if not os.path.isfile(shared_dsns_file):
        log(logger, logging.WARNING, f"Unable to read shared DSNs file '{shared_dsns_file}'.")
        return

    shared_config = read_config_file(shared_dsns_file)
    if shared_config is None:
        return

    configured_aliases = config.get('alias_dsn', {})
    shared_aliases = shared_config.get('alias_dsn', {})
    config['alias_dsn'] = {}
    config['alias_dsn'].update(shared_aliases)
    config['alias_dsn'].update(configured_aliases)

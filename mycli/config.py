from __future__ import print_function
import logging
import os

from cli_helpers.config import Config

logger = logging.getLogger(__name__)
PACKAGE_ROOT = os.path.dirname(__file__)


class MyCliConfig(Config):

    mysql = {}

    def __init__(self, app_name, app_author, filename, **kwargs):
        self.filename = filename

        kwargs['default'] = self.default_config_file()
        super(MyCliConfig, self).__init__(app_name, app_author, filename,
                                          **kwargs)

    def legacy_config_file(self):
        return os.path.expanduser('~/.myclirc')

    def default_config_file(self):
        return os.path.join(PACKAGE_ROOT, self.filename)

    def legacy_file_loaded(self):
        """Check if the legacy config file was loaded."""
        return (self.config_filenames and
                self.config_filenames[-1] == self.legacy_config_file())

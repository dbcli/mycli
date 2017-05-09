Development Guide
-----------------

This is a guide for developers who would like to contribute to this project.

If you're interested in contributing to mycli, thank you. We'd love your help!
You'll always get credit for your work.

GitHub Workflow
---------------

1. `Fork the repository <https://github.com/dbcli/mycli>`_ on GitHub.
2. Clone your fork locally::

    $ git clone <url-for-your-fork>

3. Add the official repository (``upstream``) as a remote repository::

    $ git remote add upstream git@github.com:dbcli/mycli.git

4. Set up a `virtual environment <http://docs.python-guide.org/en/latest/dev/virtualenvs>`_
   for development::

    $ cd mycli
    $ pip install virtualenv
    $ virtualenv mycli_dev

   We've just created a virtual environment that we'll use to install all the dependencies
   and tools we need to work on mycli. Whenever you want to work on mycli, you
   need to activate the virtual environment::

    $ source mycli_dev/bin/activate

5. Install the dependencies and development tools::

    $ pip install -r requirements-dev.txt
    $ pip install --editable .

6. Create a branch for your bugfix or feature::

    $ git checkout -b <name-of-bugfix-or-feature>

7. While you work on your bugfix or feature, be sure to pull the latest changes from ``upstream``. This ensures that your local codebase is up-to-date::

    $ git pull upstream master


Running the Tests
-----------------

While you work on mycli, it's important to run the tests to make sure your code
hasn't broken any existing functionality. To run the tests, just type in::

    $ ./setup.py test

Mycli supports Python 2.7 and 3.3+. You can test against multiple versions of
Python by running::

    $ ./setup.py test --all


Coding Style
------------

Mycli requires code submissions to adhere to
`PEP 8 <https://www.python.org/dev/peps/pep-0008/>`_.
It's easy to check the style of your code, just run::

    $ ./setup.py lint

If you see any PEP 8 style issues, you can automatically fix them by running::

    $ ./setup.py lint --fix

Be sure to commit and push any PEP 8 fixes.

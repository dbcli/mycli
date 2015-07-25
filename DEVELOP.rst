Development Guide
-----------------
This is a guide for developers who would like to contribute to this project.

GitHub Workflow
---------------

If you're interested in contributing to mycli, first of all my heart felt
thanks. `Fork the project <https://github.com/dbcli/mycli>`_ in github.  Then
clone your fork into your computer (``git clone <url-for-your-fork>``).  Make
the changes and create the commits in your local machine. Then push those
changes to your fork. Then click on the pull request icon on github and create
a new pull request. Add a description about the change and send it along. I
promise to review the pull request in a reasonable window of time and get back
to you. 

In order to keep your fork up to date with any changes from mainline, add a new
git remote to your local copy called 'upstream' and point it to the main mycli
repo.

:: 

   $ git remote add upstream git@github.com:dbcli/mycli.git

Once the 'upstream' end point is added you can then periodically do a ``git
pull upstream master`` to update your local copy and then do a ``git push
origin master`` to keep your own fork up to date. 

Local Setup
-----------

The installation instructions in the README file are intended for users of
mycli. If you're developing mycli, you'll need to install it in a slightly
different way so you can see the effects of your changes right away without
having to go through the install cycle everytime you change the code.

It is highly recommended to use virtualenv for development. If you don't know
what a virtualenv is, this `guide <http://docs.python-guide.org/en/latest/dev/virtualenvs/#virtual-environments>`_
will help you get started.

Create a virtualenv (let's call it mycli-dev). Activate it:

::

    source ./mycli-dev/bin/activate

Once the virtualenv is activated, `cd` into the local clone of mycli folder
and install mycli using pip as follows:

::

    $ pip install --editable .

    or

    $ pip install -e .

This will install the necessary dependencies as well as install mycli from the
working folder into the virtualenv. By installing it using `pip install -e`
we've linked the mycli installation with the working copy. So any changes made
to the code is immediately available in the installed version of mycli. This
makes it easy to change something in the code, launch mycli and check the
effects of your change. 

Building DEB package from scratch
--------------------

First pip install `make-deb`. Then run make-deb. It will create a debian folder
after asking a few questions like maintainer name, email etc.

$ vagrant up


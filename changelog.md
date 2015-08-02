1.1.1:
======

Bug Fixes:
----------

* Change dictonary comprehension used in mycnf reader to list comprehension to make it compatible with Python 2.6.


1.1.0:
======

Features:
---------

* Fuzzy completion is now case-insensitive. (Thanks: [bjarnagin](https://github.com/bjarnagin))
* Added new-line (`\n`) to the list of special characters to use in prompt. (Thanks: [brewneaux](https://github.com/brewneaux))
* Honor the `pager` setting in my.cnf files. (Thanks: [Iryna Cherniavska](http://github.com/j-bennet))

Bug Fixes:
----------

* Fix a crashing bug in completion engine for cross joins.
* Make `<null>` value consistent between tabular and vertical output.

Internal Changes:
-----------------

* Changed pymysql version to be greater than 0.6.6.
* Upgrade prompt_toolkit version to 0.42. (Thanks: [Yasuhiro Matsumoto](https://github.com/mattn))
* Removed the explicit dependency on six.

2015/06/10:
===========

Features:
---------

* Customizable prompt. (Thanks [Steve Robbins](https://github.com/steverobbins))
* Make `\G` formatting to behave more like mysql.
   
Bug Fixes:
----------

* Formatting issue in \G for really long column values.


2015/06/07:
===========

Features:
---------

* Upgrade prompt_toolkit to 0.38. This improves the performance of pasting long queries. 
* Add support for reading my.cnf files.
* Add editor command \e.
* Replace ConfigParser with ConfigObj.
* Add \dt to show all tables.
* Add fuzzy completion for table names and column names.
* Automatically reconnect when connection is lost to the database.

Bug Fixes:
----------

* Fix a bug with reconnect failure.
* Fix the issue with `use` command not changing the prompt.
* Fix the issue where `\\r` shortcut was not recognized.


2015/05/24
==========

Features:
---------

* Add support for connecting via socket.
* Add completion for SQL functions.
* Add completion support for SHOW statements.
* Made the timing of sql statements human friendly. 
* Automatically prompt for a password if needed.

Bug Fixes:
----------
* Fixed the installation issues with PyMySQL dependency on case-sensitive file systems. 

Current:
==========

Features:
---------

* Upgrade prompt_toolkit to 0.38. This improves the performance of pasting long queries. 
* Add support for reading my.cnf files.
* Add editor command \e.
* Replace ConfigParser with ConfigObj.
* Add \dt to show all tables.

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

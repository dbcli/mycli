Feature: connect to a database:

  @requires_local_db
  Scenario: run mycli on localhost without port
    When we run mycli with arguments "host=localhost" without arguments "port"
      When we query "status"
      Then status contains "via UNIX socket"

  Scenario: run mycli on TCP host without port
    When we run mycli without arguments "port"
      When we query "status"
      Then status contains "via TCP/IP"

  Scenario: run mycli with port but without host
    When we run mycli without arguments "host"
      When we query "status"
      Then status contains "via TCP/IP"

  @requires_local_db
  Scenario: run mycli without host and port
    When we run mycli without arguments "host port"
      When we query "status"
      Then status contains "via UNIX socket"

  Scenario: run mycli with my.cnf configuration
    When we create my.cnf file
    When we run mycli without arguments "host port user pass defaults_file"
      Then we are logged in

  Scenario: run mycli with mylogin.cnf configuration
    When we create mylogin.cnf file
    When we run mycli with arguments "login_path=test_login_path" without arguments "host port user pass defaults_file"
      Then we are logged in



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

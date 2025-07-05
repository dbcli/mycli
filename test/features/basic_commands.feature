Feature: run the cli,
  call the help command,
  check our application name,
  insert the date,
  exit the cli

  Scenario: run "\?" command
     When we send "\?" command
      then we see help output

  Scenario: run source command
     When we send source command
      then we see help output

  Scenario: check our application_name
     When we run query to check application_name
      then we see found

  Scenario: insert the date
     When we send "ctrl + o, ctrl + d"
      then we see the date

  Scenario: run the cli and exit
     When we send "ctrl + d"
      then dbcli exits

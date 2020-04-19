Feature: manipulate tables:
  create, insert, update, select, delete from, drop

  Scenario: create, insert, select from, update, drop table
     When we connect to test database
      then we see database connected
      when we create table
      then we see table created
      when we insert into table
      then we see record inserted
      when we update table
      then we see record updated
      when we select from table
      then we see data selected
      when we delete from table
      then we confirm the destructive warning
      then we see record deleted
      when we drop table
      then we confirm the destructive warning
      then we see table dropped
      when we connect to dbserver
      then we see database connected

  Scenario: select null values
    When we connect to test database
      then we see database connected
      when we select null
      then we see null selected

  Scenario: confirm destructive query
     When we query "create table foo(x integer);"
      and we query "delete from foo;"
      and we answer the destructive warning with "y"
      then we see text "Your call!"

  Scenario: decline destructive query
     When we query "delete from foo;"
      and we answer the destructive warning with "n"
      then we see text "Wise choice!"

   Scenario: no destructive warning if disabled in config
     When we run dbcli with --no-warn
      and we query "create table blabla(x integer);"
      and we query "delete from blabla;"
     Then we see text "Query OK"

  Scenario: confirm destructive query with invalid response
     When we query "delete from foo;"
      then we answer the destructive warning with invalid "1" and see text "is not a valid boolean"

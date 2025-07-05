Feature: I/O commands

  Scenario: edit sql in file with external editor
     When we start external editor providing a file name
      and we type "select * from abc" in the editor
      and we exit the editor
      then we see dbcli prompt
      and we see "select * from abc" in prompt

  Scenario: tee output from query
     When we tee output
      and we wait for prompt
      and we select "select 123456"
      and we wait for prompt
      and we notee output
      and we wait for prompt
      then we see 123456 in tee output

   Scenario: set delimiter
      When we query "delimiter $"
      then delimiter is set to "$"

   Scenario: set delimiter twice
      When we query "delimiter $"
      and we query "delimiter ]]"
      then delimiter is set to "]]"

   Scenario: set delimiter and query on same line
      When we query "select 123; delimiter $ select 456 $ delimiter %"
      then we see tabular result "123"
      and we see tabular result "456"
      and delimiter is set to "%"

   Scenario: send output to file
      When we query "\o /tmp/output1.sql"
      and we query "select 123"
      and we query "system cat /tmp/output1.sql"
      then we see csv result "123"

   Scenario: send output to file two times
      When we query "\o /tmp/output1.sql"
      and we query "select 123"
      and we query "\o /tmp/output2.sql"
      and we query "select 456"
      and we query "system cat /tmp/output2.sql"
      then we see csv result "456"
  
   Scenario: shell style redirect to file
      When we query "select 123 as constant $> /tmp/output1.csv"
      and we query "system cat /tmp/output1.csv"
      then we see csv 123 in redirected output

   Scenario: shell style redirect to command
      When we query "select 100 $| wc"
      then we see 12 in redirected output

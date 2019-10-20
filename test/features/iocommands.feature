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
      then we see result "123"
      and we see result "456"
      and delimiter is set to "%"

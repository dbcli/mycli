Feature: LLM special command

  Scenario: show usage without args
     When we query "\llm"
      and we wait for prompt
      then we see text "Use an LLM to create SQL queries"
      then we see dbcli prompt

  Scenario: run llm models
     When we query "\llm models"
      and we wait for prompt
      then we see text "Default: "
      then we see dbcli prompt


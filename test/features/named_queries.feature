Feature: named queries:
  save, use and delete named queries

  Scenario: save, use and delete named queries
     When we connect to test database
      then we see database connected
      when we save a named query
      then we see the named query saved
      when we use a named query
      then we see the named query executed
      when we delete a named query
      then we see the named query deleted

  Scenario: save, use and delete named queries with parameters
     When we connect to test database
      then we see database connected
      when we save a named query with parameters
      then we see the named query saved
      when we use named query with parameters
      then we see the named query with parameters executed
      when we use named query with too few parameters
      then we see the named query with parameters fail with missing parameters
      when we use named query with too many parameters
      then we see the named query with parameters fail with extra parameters

from collections import namedtuple

# Query tuples are used for maintaining history
Query = namedtuple("Query", ["query", "successful", "mutating"])

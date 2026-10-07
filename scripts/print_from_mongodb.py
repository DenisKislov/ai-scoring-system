"""Quick debug view of parsed vacancies in MongoDB.

Prints the vacancy count and each vacancy's title/salary. Connects to the same
``gb_parse`` db the spider writes to (override via MONGO_URI / MONGO_DB env,
matching the rest of the project).
"""
import os

from pymongo import MongoClient

client = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.environ.get("MONGO_DB", "gb_parse")]

vacancies = list(db["hh"].find())
print(len(vacancies))
for v in vacancies:
    print(v.get("title"), v.get("salary"))

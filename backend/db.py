"""SQLite storage + sample data seeding."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "feedbacklens.db"

SAMPLE_RUBRIC = {
    "name": "CS101: Explain how a hash table works",
    "assignment_prompt": "In 150-300 words, explain how a hash table stores and retrieves data. "
                         "Cover hashing, collisions and performance, and include an example.",
    "min_words": 120,
    "criteria": [
        {"name": "Core concepts", "type": "concepts", "max_points": 10,
         "description": "Explains the key ideas behind hash tables.",
         "concepts": [
             {"name": "Hash function", "keywords": ["hash function", "hashing", "hash code", "hashes"],
              "hint": "Say how a key is turned into an array index.",
              "example": "A hash function maps a key to an index, e.g. index = hash(key) mod table_size."},
             {"name": "Collisions", "keywords": ["collision", "collide"],
              "hint": "Explain what happens when two keys map to the same index.",
              "example": "Keys 15 and 25 both map to index 5 when the table size is 10, which is a collision."},
             {"name": "Collision resolution", "keywords": ["chaining", "open addressing", "linear probing", "probing", "linked list"],
              "hint": "Name at least one strategy (chaining or open addressing).",
              "example": "With chaining, each bucket holds a linked list of all entries that hash to it."},
             {"name": "Time complexity", "keywords": ["o(1)", "constant time", "average case", "o(n)", "time complexity"],
              "hint": "State average and worst-case lookup cost.",
              "example": "Lookups take O(1) on average but can degrade to O(n) if many keys collide."},
             {"name": "Load factor / resizing", "keywords": ["load factor", "resiz", "rehash"],
              "hint": "Mention how the table grows to keep it fast.",
              "example": "When the load factor passes about 0.75 the table is resized and entries are rehashed."}]},
        {"name": "Examples & evidence", "type": "evidence", "max_points": 4,
         "description": "Uses a concrete example."},
        {"name": "Structure & organisation", "type": "structure", "max_points": 3,
         "description": "Clear intro, body and conclusion."},
        {"name": "Clarity & language", "type": "clarity", "max_points": 3,
         "description": "Readable sentences, appropriate length."},
    ],
}

SAMPLE_SUBMISSIONS = [
    ("Ayesha Khan",
     "A hash table stores key-value pairs in an array. A hash function converts each key into an index, so we can jump "
     "straight to the right slot.\n\nSometimes two keys produce the same index. This is called a collision. For example, with "
     "a table of size 10, keys 15 and 25 both map to index 5. One common solution is chaining, where each slot holds a linked "
     "list of entries. Another is open addressing with linear probing.\n\nBecause of this design, lookups take O(1) time on "
     "average, although the worst case is O(n) when many keys collide. Therefore, tables are resized when the load factor "
     "becomes too high, and all entries are rehashed.\n\nIn conclusion, hash tables give very fast access at the cost of extra memory."),
    ("Bilal Ahmed",
     "A hash table is a data structure that stores data in an array and uses hashing to find things quickly. "
     "It is used in many programs and is very useful for storing data and finding it later."),
]


def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init(engine_analyze=None):
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS rubrics(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY, rubric_id INTEGER NOT NULL, student_name TEXT NOT NULL,
            text TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS feedback(
            submission_id INTEGER PRIMARY KEY, data TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', updated REAL NOT NULL);
        """)
        if c.execute("SELECT COUNT(*) FROM rubrics").fetchone()[0] == 0:
            cur = c.execute("INSERT INTO rubrics(data) VALUES (?)", (json.dumps(SAMPLE_RUBRIC),))
            rid = cur.lastrowid
            if engine_analyze:
                for name, text in SAMPLE_SUBMISSIONS:
                    sc = c.execute("INSERT INTO submissions(rubric_id,student_name,text,created) VALUES (?,?,?,?)",
                                   (rid, name, text, time.time()))
                    fb = engine_analyze(SAMPLE_RUBRIC, text, "local")
                    c.execute("INSERT INTO feedback(submission_id,data,status,updated) VALUES (?,?,?,?)",
                              (sc.lastrowid, json.dumps(fb), "draft", time.time()))

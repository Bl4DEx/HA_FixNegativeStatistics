#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This script fixes the broken statistics in the HomeAssistant database caused by a bug in the Riemann Sum in HA 2023.05
It fixes the tables: statistics, statistics_short_term
It fixes the keys: sum, state

Usage: python HA_FixNegativeStatistics [--list]
"""

import os
import sys
import shutil
import sqlite3

__author__ = "Sebastian Hollas"
__version__ = "1.0.0"

# Path to your database
DATABASE_PATH = r"config/home-assistant_v2.db"
# Set the metadata_ids that you want to have fixed; run "python FixNegativeStatistics.py --list" for some help
METADATA_IDS = (96, 97, 98, 99, 100, 101, 133, 137, 151, 152, 153, 154)

if not os.path.isfile(DATABASE_PATH):
    sys.exit("Database does not exist!")

# Open database
db = sqlite3.connect(DATABASE_PATH)
# Create cursor object within the database
cur = db.cursor()

# Amount of entries changed
entries_changed = 0


def fixDatabase():
    # Create database backup
    shutil.copyfile(DATABASE_PATH, DATABASE_PATH.replace(".db", ".db.BAK"))

    # Update both tables statistics and statistics_short_term
    for table in ("statistics", "statistics_short_term"):

        # Update both keys state and sum
        for key in ("state", "sum"):

            # Fix value for all metadata_ids
            for metadata_id in METADATA_IDS:
                fix_table_state(table, key, metadata_id)

    # Store database on disk
    db.close()

    # Print result
    print(f"\n\n{entries_changed} values changed!")


def fix_table_state(table: str, key: str, metadata_id: int):
    # Execute SQL query to get all entries for this metadata_id
    cur.execute("SELECT id,{} FROM {} WHERE metadata_id=? ORDER BY created_ts".format(key, table), (metadata_id,))
    result = cur.fetchall()

    # Step through database in reverse order
    for index, (id, value) in reversed(list(enumerate(result))):
        # Get previous entry
        _, pre_value = result[index - 1]

        if pre_value <= value or index == 0:
            # We reached the first entry
            # OR
            # current and previous are the same or incrementing. Value is correct

            # nothing to do
            continue

        print(f"\nStarting with ID: {id}")

        # First broken value; re-use old value (we might lose one time period of measurement)
        new_value = pre_value

        # Update value in database
        updateValueInDatabase(table, id, key, new_value)
        print(f"({id}, {value}) -> ({id}, {new_value})")

        # Fix ALL following entries
        for fix_index, (fix_id, fix_value) in enumerate(result[index + 1:], index + 1):

            # Get previous value (before it was fixed)
            _, pre_value = result[fix_index - 1]

            # Add difference between last value and new value
            new_value += fix_value - pre_value

            # Update value in database
            updateValueInDatabase(table, fix_id, key, new_value)
            print(f"({fix_id}, {fix_value}) -> ({fix_id}, {new_value})")

        # Update entries for next run
        cur.execute("SELECT id,{} FROM {} WHERE metadata_id=? ORDER BY created_ts".format(key, table), (metadata_id,))
        result = cur.fetchall()


def updateValueInDatabase(table: str, id: int, key: str, value: int):
    """
    Update key with value in table
    :param table: Table to update in database
    :param id   : ID of entry to update
    :param key  : Key to update
    :param value: New value
    """

    # Execute SQL query
    cur.execute("UPDATE '{}' SET '{}'=? WHERE id=?".format(table, key), (value, id))

    # Commit changes to DB
    db.commit()

    global entries_changed
    entries_changed += 1


def list_metadataIds():
    # Execute SQL query
    cur.execute("SELECT id,statistic_id FROM statistics_meta WHERE has_sum=1")

    for id, entity in cur.fetchall():
        # Print metadata_id and entity name
        print(f"metadata_id: {id: >3} | {entity}")


if __name__ == "__main__":

    if len(sys.argv) == 1:
        # Fix database
        fixDatabase()

    elif len(sys.argv) == 2 and sys.argv[1] == "--list":
        # List available metadata_ids
        list_metadataIds()

    else:
        sys.exit("Unknown input argument!")

    sys.exit(0)

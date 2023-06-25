#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This script fixes the broken statistics in the HomeAssistant database caused by a bug in the Riemann Sum in HA 2023.05

Usage: python HA_FixNegativeStatistics [--list]
"""

import json
import os
import sys
import shutil
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime

__author__ = "Sebastian Hollas"
__version__ = "2.1.1"

####################################################################################
# USER INPUT REQUIRED !
# Path to HomeAssistant config root (e.g. /HomeAssistant/config )
HA_CONFIG_ROOT = "/HomeAssistant/config"
####################################################################################

# USER INPUT OPTIONAL ! (if MySQL server shall be used instead of a SQLite database file)
DB_SERVER = {
    "DB_HOST": "",
    "DB_USER": "",
    "DB_PASSWORD": "",
    "DB_NAME": ""
}
####################################################################################

# Build Filepaths
ENTITIES_FILE = os.path.join(HA_CONFIG_ROOT, "entities.list")
RESTORE_STATE_PATH = os.path.join(HA_CONFIG_ROOT, ".storage", "core.restore_state")

if not os.path.isfile(RESTORE_STATE_PATH):
    sys.exit(f"File {RESTORE_STATE_PATH} does not exist! (Path to HomeAssistant config valid?)")

# Open MySQL server connection if user provided DB_SERVER information
if all(DB_SERVER.values()):
    import pymysql
    db = pymysql.connect(
        host=DB_SERVER["DB_HOST"],
        user=DB_SERVER["DB_USER"],
        password=DB_SERVER["DB_PASSWORD"],
        database=DB_SERVER["DB_NAME"],
        autocommit=True
    )

# Create connection to database file if no DB_SERVER information was provided
else:
    # Check for database file
    DATABASE_PATH = os.path.join(HA_CONFIG_ROOT, "home-assistant_v2.db")
    if not os.path.isfile(DATABASE_PATH):
        sys.exit(f"Database {DATABASE_PATH} does not exist!")

    db = sqlite3.connect(DATABASE_PATH)

# Create cursor object within the database
cur = db.cursor()


def main():

    if len(sys.argv) == 1:

        # Check that no backup file exists
        if isinstance(db, sqlite3.Connection):
            if os.path.isfile(f"{DATABASE_PATH}.BAK"):
                sys.exit("Database backup file already exists!")
            # Create database backup
            shutil.copyfile(DATABASE_PATH, f"{DATABASE_PATH}.BAK")
        else:
            print("Cannot create backup with a connection to a database server!\n"
                  "Changes are made to database immediately. Make sure to have a backup available!\n\n"
                  "Do you want to continue? (yes/no)")
            if input().lower() != "yes":
                sys.exit("Execution stopped by user!")

        # Check that no backup file exists
        if os.path.isfile(f"{RESTORE_STATE_PATH}.BAK"):
            sys.exit("core.restore_state backup file already exists!")
        # Create core.restore_state backup
        shutil.copyfile(RESTORE_STATE_PATH, f"{RESTORE_STATE_PATH}.BAK")

        if not os.path.isfile(ENTITIES_FILE):
            sys.exit(f"File {ENTITIES_FILE} does not exist! (Run with --list first and remove unwanted entities)")

        with open(ENTITIES_FILE, "r") as file:
            ENTITIES = file.read().splitlines()

        # Fix database
        fixDatabase(ENTITIES=ENTITIES)

    elif len(sys.argv) == 2 and sys.argv[1] == "--list":

        with open(ENTITIES_FILE, "w") as file:
            # Get Entities that have a round option
            SqlExec("SELECT statistic_id FROM statistics_meta WHERE has_sum=1", ())
            if not (result := cur.fetchall()):
                sys.exit("There are no entities which can be fixed in the database (key 'sum' in table statistics_meta is not populated)")

            for entity_id in result:
                file.write(f"{entity_id[0]}\n")

        print(f"File '{ENTITIES_FILE}' created with entities that have the key 'sum'"
              f"\nPlease adjust to your needs and rerun the script with no arguments.")

    else:
        sys.exit("Unknown input argument!")


def fixDatabase(ENTITIES: list):

    # Fix value for all metadata_ids
    for entity_id in ENTITIES:

        ################################################################################################################
        # Get metadata_id used in table "states"
        SqlExec("SELECT metadata_id FROM states_meta WHERE entity_id=?", (entity_id,))

        if (result := cur.fetchone()) is None:
            print(f"  [WARNING]: Entity with name '{entity_id}' does not exist in table states_meta! Skipping...")
            continue

        # Get metadata_id from SQL Query result
        metadata_id_states = result[0]

        ################################################################################################################
        # Get metadata_id used in table "statistics"
        SqlExec("SELECT id FROM statistics_meta WHERE statistic_id=?", (entity_id,))

        if (result := cur.fetchone()) is None:
            print(f"  [WARNING]: Entity with name '{entity_id}' does not exist in table states_meta! Skipping...")
            continue

        # Get metadata_id from SQL Query result
        metadata_id_statistics = result[0]

        ################################################################################################################
        # FIX DATABASE
        print("\n========================================================================")
        print(f"{entity_id} | {metadata_id_states = } | {metadata_id_statistics = }")

        # Fix table "statistics"
        lastValidSum = recalculateStatistics(metadata_id=metadata_id_statistics, key="sum")
        lastValidState = recalculateStatistics(metadata_id=metadata_id_statistics, key="state")

        # Delete ShortTerm statistics and input one entry with current state
        fixShortTerm(metadata_id=metadata_id_statistics, lastValidSum=lastValidSum, lastValidState=lastValidState)

        # Fix table "states"
        recalculateStates(metadata_id=metadata_id_states)

        # Fix last valid state to current state
        fixLastValidState(entity_id=entity_id, lastValidState=lastValidState)

    # Store database on disk
    print(f"\n{db.total_changes} changes made to database!")
    db.commit()
    db.close()


def recalculateStatistics(metadata_id: int, key: str) -> str:

    print(f"  Fixing table statistics for key: {key}")

    # Execute SQL query to get all entries for this metadata_id
    SqlExec(f"SELECT id,{key} FROM statistics WHERE metadata_id=? ORDER BY created_ts", (metadata_id,))
    result = cur.fetchall()

    # Get first value from database; this is our starting point
    try:
        current_value = Decimal(str(result[0][1]))
    except ValueError:
        sys.exit(f"  [ERROR]: Cannot fix this entity because first entry in table 'statistics' for {key} is not a number! Sorry!")

    # Loop over all entries starting with the second entry
    for index, (idx, value) in enumerate(result[1:]):

        # Get previous entry
        _, pre_value = result[index]

        # Convert do decimal object
        value = Decimal(str(value))
        pre_value = Decimal(str(pre_value))

        if value < current_value:
            # Current value is out-dated

            if value >= pre_value:
                # Recalculate new value with difference of previous entries
                current_value += (value-pre_value)

            print(f"    Updating {idx = }: {value} -> {current_value}")
            SqlExec(f"UPDATE statistics SET {key}=? WHERE id=?", (float(current_value), idx))

            continue

        # Set current value as new value
        current_value = value

    # Return last value
    return str(current_value)


def fixShortTerm(metadata_id: int, lastValidSum: str, lastValidState: str):

    # Delete Short Term statistics from database
    print("  Deleting short term statistics")
    SqlExec("DELETE FROM statistics_short_term WHERE metadata_id=?", (metadata_id, ))

    now = datetime.now()
    minute_end = now.minute - (now.minute % 5)
    minute_start = (minute_end - 5) if minute_end else 55
    now_end = now.replace(minute=minute_end, second=0, microsecond=0)
    now_start = now.replace(minute=minute_start, second=0, microsecond=0)

    SqlExec("INSERT INTO statistics_short_term (state, sum, metadata_id, created_ts, start_ts) VALUES(?, ?, ?, ?, ?)",
            (lastValidState, lastValidSum, metadata_id, now_end.timestamp(), now_start.timestamp()))


def recalculateStates(metadata_id: int):
    print(f"  Fixing table states")

    SqlExec("SELECT state_id,state,old_state_id,attributes_id FROM states WHERE metadata_id=? ORDER BY state_id",
                (metadata_id,))
    result = cur.fetchall()

    # Get first value from database; this is our starting point
    try:
        current_state = Decimal(str(result[0][1]))
        attributes_id = result[0][3]
    except InvalidOperation:
        sys.exit(f"  [ERROR]: Cannot fix this entity because first entry in table 'states' is not a number! first entry: {result[0][3]}")

    # Loop over all entries starting with the second entry
    for index, (state_id, state, old_state_id, attr_id) in enumerate(result[1:]):
        pre_state_id, pre_state, _, _ = result[index]

        if old_state_id is None:
            # old_state_id is missing; Update to id of previous entry
            SqlExec("UPDATE states SET old_state_id=? WHERE state_id=?", (pre_state_id, state_id))

        if attributes_id != attr_id:
            # attribute_id is wrong; update to correct one (HA sometimes creates new attributes in case of broken calculations)
            SqlExec("UPDATE states SET attributes_id=? WHERE state_id=?", (attributes_id, state_id))

        if state is None or not state.replace(".", "", 1).isdigit():
            # State is NULL or not numeric; update to current value
            print(f"    Updating {state_id = }: {state} -> {current_state}")
            SqlExec("UPDATE states SET state=? WHERE state_id=?", (float(current_state), state_id))
            continue

        state = Decimal(str(state))
        if state < current_state:
            # Current value is out-dated

            if pre_state and pre_state.replace(".", "", 1).isdigit() and state >= Decimal(str(pre_state)):
                # Recalculate new value with difference of previous entries
                current_state += (state - Decimal(str(pre_state)))

            print(f"    Updating {state_id = }: {state} -> {current_state}")
            SqlExec("UPDATE states SET state=? WHERE state_id=?", (float(current_state), state_id))
            continue

        # Set current value as new value
        current_state = state


def fixLastValidState(entity_id: str, lastValidState: str):
    # Read core.restore_state
    with open(RESTORE_STATE_PATH, "r") as file:
        restore_state = json.load(file)

    # Loop over json
    for state in restore_state["data"]:

        # Search for entity_id
        if state["state"]["entity_id"] != entity_id:
            continue

        # Modify state to new value
        if state["state"].get("state", ""):
            state["state"]["state"] = lastValidState

        if state["extra_data"]:

            if state["extra_data"].get("last_valid_state", ""):
                state["extra_data"]["last_valid_state"] = lastValidState

            if state["extra_data"].get("native_value", dict()).get("decimal_str", ""):
                state["extra_data"]["native_value"]["decimal_str"] = lastValidState

        break

    # Write modified json
    with open(RESTORE_STATE_PATH, "w") as file:
        json.dump(restore_state, file, indent=2, ensure_ascii=False)


def SqlExec(SqlQuery: str, arguments: tuple):
    if not isinstance(db, sqlite3.Connection):
        # Replace placeholder for module PyMySQL
        SqlQuery = SqlQuery.replace("?", "%s")

    cur.execute(SqlQuery, arguments)


if __name__ == "__main__":
    # Call main function
    main()
    # Exit with positive return value
    sys.exit(0)

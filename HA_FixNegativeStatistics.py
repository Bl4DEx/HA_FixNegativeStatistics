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
from datetime import datetime

__author__ = "Sebastian Hollas"
__version__ = "2.1.0"

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
CONFIG_ENTRIES_PATH = os.path.join(HA_CONFIG_ROOT, ".storage", "core.config_entries")
ENTITY_REGISTRY_PATH = os.path.join(HA_CONFIG_ROOT, ".storage", "core.entity_registry")

if not os.path.isfile(RESTORE_STATE_PATH):
    sys.exit(f"File {RESTORE_STATE_PATH} does not exist! (Path to HomeAssistant config valid?)")

if not os.path.isfile(CONFIG_ENTRIES_PATH):
    sys.exit(f"File {CONFIG_ENTRIES_PATH} does not exist! (Path to HomeAssistant config valid?)")

if not os.path.isfile(ENTITY_REGISTRY_PATH):
    sys.exit(f"File {ENTITY_REGISTRY_PATH} does not exist! (Path to HomeAssistant config valid?)")


# Open MySQL server connection if user provided DB_SERVER information
if all(DB_SERVER.values()):
    import pymysql
    db = pymysql.connect(
        host=DB_SERVER["DB_HOST"],
        user=DB_SERVER["DB_USER"],
        password=DB_SERVER["DB_PASSWORD"],
        database=DB_SERVER["DB_NAME"]
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
            for entity_id in getEntitiesPrecision():
                file.write(f"{entity_id}\n")

        print(f"File '{ENTITIES_FILE}' created with entities that have the key 'sum'"
              f"\nPlease adjust to your needs and rerun the script with no arguments.")

    else:
        sys.exit("Unknown input argument!")


def fixDatabase(ENTITIES: list):
    # Get Precision of Entities
    EntityPrecision = getEntitiesPrecision()

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
        # Get amount of decimals for Riemann Sum integral that the user configured
        if entity_id not in EntityPrecision:
            print(f"  [WARNING]: Entity seems not to be a Riemann Sum Entity! UNTESTED. USE WITH CAUTION!")
            roundDigits = -1
        else:
            # Get Precision of Entity that user configured
            roundDigits = EntityPrecision[entity_id]

        ################################################################################################################
        # FIX DATABASE
        print("\n========================================================================")
        print(f"{entity_id} | {metadata_id_states = } | {metadata_id_statistics = }")

        # Fix table "statistics"
        lastValidSum = recalculateStatistics(metadata_id=metadata_id_statistics, key="sum", roundDigits=roundDigits)
        lastValidState = recalculateStatistics(metadata_id=metadata_id_statistics, key="state", roundDigits=roundDigits)

        # Delete ShortTerm statistics and input one entry with current state
        fixShortTerm(metadata_id=metadata_id_statistics, lastValidSum=lastValidSum, lastValidState=lastValidState)

        # Fix table "states"
        recalculateStates(metadata_id=metadata_id_states, roundDigits=roundDigits)

        # Fix last valid state if entity seems to be a Riemann Sum Entity only
        # OPEN: How to find out if entity is a Riemann Sum Entity?!
        # Currently: If entity is in table statistics and has a "round" attribute, it is assumed to be a Riemann Sum Entity
        if roundDigits != -1:
            # Fix last valid state in HA to ensure a valid calculation with the next Riemann Sum calculation
            fixLastValidState(entity_id=entity_id, lastValidState=lastValidState)

    # Store database on disk
    print(f"\n{db.total_changes} changes made to database!")
    db.commit()
    db.close()


def recalculateStatistics(metadata_id: int, key: str, roundDigits: int) -> str:

    print(f"  Fixing table statistics for key: {key}")

    # Execute SQL query to get all entries for this metadata_id
    SqlExec(f"SELECT id,{key} FROM statistics WHERE metadata_id=? ORDER BY created_ts", (metadata_id,))
    result = cur.fetchall()

    # Get first value from database; this is our starting point
    try:
        current_value = float(result[0][1])
    except ValueError:
        sys.exit(f"  [ERROR]: Cannot fix this entity because first entry in table 'statistics' for {key} is not a number! Sorry!")

    # Loop over all entries starting with the second entry
    for index, (idx, value) in enumerate(result[1:]):

        # Get previous entry
        _, pre_value = result[index]

        if value < current_value:
            # Current value is out-dated

            if value >= pre_value:
                # Recalculate new value with difference of previous entries
                current_value += (value-pre_value)

            if roundDigits != -1:
                roundedValue = f"{current_value:.{roundDigits}f}"
            else:
                # Just copy because we don't round the value
                roundedValue = current_value
            print(f"    Updating {idx = }: {value = } -> {roundedValue = }")
            SqlExec(f"UPDATE statistics SET {key}=? WHERE id=?", (roundedValue, idx))

            continue

        # Set current value as new value
        current_value = value

    # Return last value
    if roundDigits != -1:
        # Return rounded value
        return f"{current_value:.{roundDigits}f}"
    else:
        # Return value as it is
        return current_value


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


def recalculateStates(metadata_id: int, roundDigits: int):
    print(f"  Fixing table states")

    SqlExec("SELECT state_id,state,old_state_id,attributes_id FROM states WHERE metadata_id=? ORDER BY state_id",
                (metadata_id,))
    result = cur.fetchall()

    # Get first value from database; this is our starting point
    try:
        current_state = float(result[0][1])
        attributes_id = result[0][3]
    except ValueError:
        sys.exit("  [ERROR]: Cannot fix this entity because first entry in table 'states' is not a number! Sorry!")

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
            if roundDigits != -1:
                roundedValue = f"{current_state:.{roundDigits}f}"
            else:
                # Just copy because we don't round the value
                roundedValue = current_state
            print(f"    Updating {state_id = }: {state = } -> {roundedValue}")
            SqlExec("UPDATE states SET state=? WHERE state_id=?", (roundedValue, state_id))
            continue

        state = float(state)
        if state < current_state:
            # Current value is out-dated

            if pre_state and pre_state.replace(".", "", 1).isdigit() and state >= float(pre_state):
                # Recalculate new value with difference of previous entries
                current_state += (state - float(pre_state))

            if roundDigits != -1:
                roundedValue = f"{current_state:.{roundDigits}f}"
            else:
                # Just copy because we don't round the value
                roundedValue = current_state
            print(f"    Updating {state_id = }: {state = } -> {roundedValue}")
            SqlExec("UPDATE states SET state=? WHERE state_id=?", (roundedValue, state_id))
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
        if state["state"]["entity_id"] == entity_id:
            # Modify state to new value
            state["state"]["state"] = lastValidState
            state["extra_data"]["native_value"]["decimal_str"] = lastValidState
            state["extra_data"]["last_valid_state"] = lastValidState
            break

    # Write modified json
    with open(RESTORE_STATE_PATH, "w") as file:
        json.dump(restore_state, file, indent=2, ensure_ascii=False)


def getEntitiesPrecision() -> dict[str: int]:
    # Initialize return dictionary
    returnDict = dict()

    # Read file core.config_entries
    with open(CONFIG_ENTRIES_PATH, "r") as file:
        configEntries = json.load(file)

    # Read file core.entity_registry
    with open(ENTITY_REGISTRY_PATH, "r") as file:
        configEntities = json.load(file)

    configIds = dict()

    # Find entry_ids which have the option/round attribute (these are most likely Riemann Sum Entities)
    for configEntry in configEntries["data"]["entries"]:
        number = configEntry["options"].get("round", -1)
        if number == -1:
            continue

        # Store precision value
        configIds[configEntry["entry_id"]] = int(number)

    # Find entity_id for all entry_ids
    for configEntity in configEntities["data"]["entities"]:
        if configEntity["config_entry_id"] not in configIds:
            continue

        entity_id = configEntity["entity_id"]
        config_entry_id = configEntity["config_entry_id"]
        # Store precision and entity_id
        returnDict[entity_id] = configIds[config_entry_id]

    # Return dict with format {entity_id: precision}
    return returnDict


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

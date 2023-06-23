# HA_FixNegativeStatistics

## Summary
There was a bug introduced with HomeAssistant 2023.05 which resulted in negative values in the energy dashboard if Riemann Sum was used for power calculation. 
This script fixed the values in the HomeAssistant database and recalculate all following entries  

Tested with
  * HomeAssistant Docker 2023.6.2

## You are not interested in the details and just want to have your database fixed? Read this paragraph
### DISCLAIMER 
* This script wipes *statistics_short_term* in the database and replaces it with one single entry with the last valid value.  
  It is **required** to have the last value updated for the next calculation of Riemann Sum Integral
* **You do NOT lose any long-term statistics.** (Read below to understand the reason)    
  This table holds the Riemann Sum Integral with a resolution of 5 minutes but not the long-term statistics.  
* HA starts to fill this table again  

### How to use this script
1. Clone this repository  
2. Change following variable to your HomeAssistant config folder
   ```bash
   HA_CONFIG_ROOT = "/HomeAssistant/config"
   ```
3. Create a entities.list file which includes entities that can be fixed by this script by executing:  
   **(This does NOT touch your database yet)**
   ```bash
   python HA_FixNegativeStatistics.py --list
   ```
5. Modify entities.list to your needs (remove unwanted entities)
6. Execute
   ```bash
   python HA_FixNegativeStatistics.py
   ```

**NOTE:**  
  * This script makes a backup of your existing database first.  
  * This script exits if a backup file exists already to prevent an ovewrite.

## What does this script do?
In order to ensure a valid calculation, we need to fix multiple tables in the database and also update the last valid value of the Riemann Sum Integral in the .storage of HomeAssistant.  
Otherwise, the next calculation of Riemann Sum Integral will result in an invalid value.  
  
We need to fix:  
  1. In table *statistics*: Key "state"
  2. In table *statistics*: Key "sum"
  3. In table *statistics_shor_term*: We need only entry with the last valid value of key "state" and "sum"
  4. In table "states": Key "state"
  5. In file *.storage/core.restore_state*: Last valid state of entity

## How are the values fixed?
### Table *statistiscs*
This table holds the long-term statistics of all the entities which support statistics (including Riemann Sum Entities).  
This table stores values with an interval of 1 hour and holds the entire history of your entities.  
For every full hour, HA copies the last value from *short_term_statistics* into *statistics*

  * We are looping through the table from top to bottom for both keys *state* and *sum*.
  * We start updating if a value is lower than the previous value. It is required to update **ALL** following entries in this case.
  * The script always tries to use the difference between the previous entries. We don't want to lose the actual history!

### Table *statistics_short_term*
This table holds the short_term statistics of the last ~ 10 days. This table is used to show a more precise graph to the user.  
This table stores values with an interval of 5 minutes and is not mandatory. But we need to make sure that the last value is set to the last valid value

  * We delete the entire history for the entity
  * We insert one single entry with the last valid value from table *statistics*
  * HomeAssistant starts to fill this table automatically

### Table *states*
This table holds all states for every single entity in your HomeAssistant.

  * We are looping through the table from top to bottom
  * We start updating if a value is lower than the previous value. It is required to update **ALL** following entries in this case.
  * The script always tries to use the difference between the previous entries. We don't want to lose the actual history!
  * In addition: The script fixes the attributes_id to the correct one. Sometimes HA creates a new attributes_id in case of broken calculation
  * In addition: The script fixes the key "old_state_id" if the value is NULL

### File *core.restore_state*
This file holds all the last valid values of your entities.  
The Riemann Sum Integration uses this value to calculate the next state for the table *states*

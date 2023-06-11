# HA_FixNegativeStatistics

## Summary
There was a bug introduced with HomeAssistant 2023.05 which resulted in negative values in the energy dashboard if Riemann Sum was used for power calculation. 
This script fixed the values in the HomeAssistant database and recalculate all following entries

**This script will fix the following entries:**
![image](https://github.com/Bl4DEx/HA_FixNegativeStatistics/assets/79091431/773bc384-3277-4a43-b304-5e750f97f18b)

**to:**
![image](https://github.com/Bl4DEx/HA_FixNegativeStatistics/assets/79091431/3cc19817-baae-4454-afb4-cd28596f1ecd)

## Usage
1. Clone this repository  
2. Change variables
   ```bash
   DATABASE_PATH: str  = "" # Your HomeAssistant database (e.g. config/home-assistant_v2.db)
   METADATA_IDS: tuple = () # metadata_ids that you want to have fixed (comma separated tuple)
   ```
3. Execute 
   ```bash
   python HA_FixNegativeStatistics.py
   ```
   
This script makes a backup of your existing database first.

## What metadata_ids do I want to update?
If you don't know which metadata_id your broken entities have, run the following:
```bash
python HA_FixNegativeStatistics.py --list
```
This will print all existing metadata_ids in your database with the entity_id name.  
**NOTE:** THIS COMMAND WILL NOT CHANGE ANYTHING IN YOUR DATABASE YET

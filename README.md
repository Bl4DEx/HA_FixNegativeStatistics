# HA_FixNegativeStatistics
There was a bug introduced with HomeAssistant 2023.05 which resulted in negative values in the energy dashboard if Riemann Sum was used for power calculation. 
This script fixed the values in the HomeAssistant database and recalculate all following entries

This script will fix the following entries:

![image](https://github.com/Bl4DEx/HA_FixNegativeStatistics/assets/79091431/773bc384-3277-4a43-b304-5e750f97f18b)

to:
![image](https://github.com/Bl4DEx/HA_FixNegativeStatistics/assets/79091431/82dc5c9d-aabc-48f5-b744-f51908b492dc)


# CHANGELOG.md

## 2.2.0
* Add support for fixing powercalc entities
* Fixing core.restore_state and powercalc_group is ignored if files do not exist
* Fixing states and statistiscs: Now searches first valid value and uses it as a starting point  
  (Previously, skipped if first value was not valid)

## 2.1.2
* Table statistics: Update sum/state if value is NULL
* FixLastValidState: Add checks for types
* Remove autocommit for MySQL server
* Remove output of total changes but improve script output overall

## 2.1.1
* Fixed a bug where --list did not list all entities with has_sum=1
* Added *autocommit=True* for MySQL server connection
* No longer round values but handle all values as they are stored in the database

## 2.1.0
* Add support for a MySQL server using the package PyMySQL
* Add support for entities that are no Riemann Sum Entities

## 2.0.0
* Working script for all Riemann Sum Entities

## 1.0.0
* Initial commit of script (Script is fixing database but sum was wrong with next Riemann Sum calculation)
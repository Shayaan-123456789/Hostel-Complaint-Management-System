-- DESTRUCTIVE development rebuild: removes the existing schema data.
-- Run in SQL*Plus/SQLcl as the project schema owner: @run_all.sql
-- Use run_all only on a disposable database; never on a live database.
SET SERVEROUTPUT ON SIZE UNLIMITED
SET DEFINE OFF
@00_drop_all.sql
-- The drop helper tolerates missing objects. Re-enable failure on errors
-- BEFORE creating any application objects or inserting test records.
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
@01_ddl.sql
@02_triggers.sql
@03_procedures.sql
@04_test_data.sql
@05_integrity_tests.sql
@06_verify_objects.sql
PROMPT === Database rebuild and checks finished successfully ===

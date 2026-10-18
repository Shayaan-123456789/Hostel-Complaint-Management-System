-- READ ONLY. Run as the Django Oracle DB user in SQL*Plus / SQLcl.
-- This file never creates/updates/deletes project data.
SET LINESIZE 180
SET PAGESIZE 100
COL session_user FORMAT A25
COL current_schema FORMAT A25
COL object_name FORMAT A34
COL status FORMAT A12
PROMPT === Session identity (schema owner vs API login) ===
SELECT USER AS session_user, SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema FROM dual;
PROMPT === Project objects visible from this login ===
SELECT owner, object_type, object_name, status
  FROM all_objects
 WHERE object_name IN (
 'ROOM','STUDENT','CATEGORY','STAFF','COMPLAINT','COMPLAINT_PHOTO',
 'COMPLAINT_ASSIGNMENT','COMPLAINT_STATUS','COMPLAINT_FEEDBACK',
 'V_COMPLAINT_DETAILS','V_DASHBOARD_SUMMARY',
 'SP_REGISTER_STUDENT','SP_SUBMIT_COMPLAINT','SP_ADD_PHOTO',
 'SP_ASSIGN_COMPLAINT','SP_UPDATE_STATUS','SP_SUBMIT_FEEDBACK',
 'SP_ESCALATE_OVERDUE','SEQ_ROOM','SEQ_STUDENT','SEQ_COMPLAINT')
 ORDER BY owner, object_type, object_name;
PROMPT === Missing privileges when logged in separately ===
SELECT owner, table_name, grantee, privilege
  FROM all_tab_privs
 WHERE grantee IN (USER, 'PUBLIC')
   AND (table_name LIKE 'SP\_%' ESCAPE '\' OR
        table_name LIKE 'SEQ\_%' ESCAPE '\' OR
        table_name IN ('ROOM','STUDENT','CATEGORY','STAFF','COMPLAINT',
          'COMPLAINT_PHOTO','COMPLAINT_ASSIGNMENT','COMPLAINT_STATUS',
          'COMPLAINT_FEEDBACK','V_COMPLAINT_DETAILS','V_DASHBOARD_SUMMARY'))
 ORDER BY owner, table_name, privilege;
PROMPT === Invalid objects owned by this login ===
SELECT object_type, object_name, status FROM user_objects
 WHERE status = 'INVALID' ORDER BY object_type, object_name;
PROMPT === Compilation errors owned by this login ===
SELECT name, type, line, position, text FROM user_errors ORDER BY name, sequence;

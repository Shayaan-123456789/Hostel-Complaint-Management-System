-- Check all installed project objects after DDL, trigger, and procedure creation.
SET SERVEROUTPUT ON SIZE UNLIMITED
DECLARE
    v_tables PLS_INTEGER;
    v_bad    PLS_INTEGER;
    v_procs  PLS_INTEGER;
    v_trigs  PLS_INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_tables FROM user_tables
     WHERE table_name IN (
        'ROOM', 'STUDENT', 'CATEGORY', 'STAFF', 'COMPLAINT',
        'COMPLAINT_PHOTO', 'COMPLAINT_ASSIGNMENT',
        'COMPLAINT_STATUS', 'COMPLAINT_FEEDBACK');
    IF v_tables <> 9 THEN
        RAISE_APPLICATION_ERROR(-20995,
            'Expected exactly nine defined hostel tables; found ' || v_tables);
    END IF;

    SELECT COUNT(*) INTO v_procs FROM user_objects
     WHERE object_type = 'PROCEDURE' AND object_name LIKE 'SP\_%' ESCAPE '\';
    SELECT COUNT(*) INTO v_trigs FROM user_objects
     WHERE object_type = 'TRIGGER' AND object_name LIKE 'TRG\_%' ESCAPE '\';
    IF v_procs <> 13 OR v_trigs <> 15 THEN
        RAISE_APPLICATION_ERROR(-20996, 'Expected 13 procedures and 15 triggers; found ' ||
            v_procs || ' procedures, ' || v_trigs || ' triggers.');
    END IF;

    SELECT COUNT(*) INTO v_bad
      FROM user_objects
     WHERE status <> 'VALID'
       AND ((object_type = 'PROCEDURE' AND object_name LIKE 'SP\_%' ESCAPE '\') OR
            (object_type = 'TRIGGER'   AND object_name LIKE 'TRG\_%' ESCAPE '\') OR
            (object_type = 'VIEW' AND object_name IN
                ('V_COMPLAINT_DETAILS', 'V_DASHBOARD_SUMMARY')));
    IF v_bad <> 0 THEN
        RAISE_APPLICATION_ERROR(-20997,
            v_bad || ' project procedures/triggers/views have INVALID status.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('PASS: 9 tables, 13 procedures, 15 triggers; project objects VALID.');
END;
/
PROMPT --- Compilation errors (should be empty) ---
SELECT name, type, line, position, text
  FROM user_errors
 WHERE type IN ('TRIGGER', 'PROCEDURE', 'VIEW')
 ORDER BY name, sequence;

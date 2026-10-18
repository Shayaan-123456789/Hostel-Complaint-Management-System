-- =====================================================================
-- 05_integrity_tests.sql : executable negative/positive SQL integration tests
-- Must run AFTER 04_test_data.sql. All test-only changes are rolled back.
-- Errors are caught inside PL/SQL so WHENEVER SQLERROR EXIT remains enabled.
-- =====================================================================
SET SERVEROUTPUT ON SIZE UNLIMITED
SET DEFINE OFF

DECLARE
    v_open       complaint.complaint_id%TYPE;
    v_assigned   complaint.complaint_id%TYPE;
    v_resolved   complaint.complaint_id%TYPE;
    v_asg        complaint_assignment.assignment_id%TYPE;
    v_staff      staff.staff_id%TYPE;
    v_room       room.room_id%TYPE;
    v_student    student.student_id%TYPE;
    v_temp       student.student_id%TYPE;
    v_block      student.block%TYPE;
    v_count      PLS_INTEGER;
    v_tests      PLS_INTEGER := 0;

    PROCEDURE expect_error(p_label VARCHAR2, p_sql VARCHAR2, p_code NUMBER) IS
        v_error NUMBER;
        v_message VARCHAR2(2000);
    BEGIN
        SAVEPOINT test_case;
        BEGIN
            EXECUTE IMMEDIATE p_sql;
        EXCEPTION
            WHEN OTHERS THEN
                v_error := SQLCODE;
                v_message := SQLERRM;
                ROLLBACK TO test_case;
                IF v_error <> p_code THEN
                    RAISE_APPLICATION_ERROR(-20990,
                        'FAIL ' || p_label || ': expected ' || p_code ||
                        ', got ' || v_error || ' - ' || SUBSTR(v_message, 1, 500));
                END IF;
                v_tests := v_tests + 1;
                DBMS_OUTPUT.PUT_LINE('PASS: ' || p_label || ' (' || p_code || ')');
                RETURN;
        END;
        ROLLBACK TO test_case;
        RAISE_APPLICATION_ERROR(-20991, 'FAIL ' || p_label || ': expected an error but SQL succeeded.');
    END;
BEGIN
    SELECT complaint_id INTO v_open FROM complaint WHERE title = 'Socket sparking';
    SELECT complaint_id INTO v_assigned FROM complaint WHERE title = 'Tap leaking';
    SELECT complaint_id INTO v_resolved FROM complaint WHERE title = 'Ceiling fan not working';
    SELECT staff_id INTO v_staff FROM staff WHERE email = 'ravi@hostel.edu';
    SELECT room_id INTO v_room FROM room WHERE block = 'A' AND room_number = '101';
    SELECT student_id INTO v_student FROM student WHERE email = 'arun@hostel.edu';
    SELECT assignment_id INTO v_asg FROM complaint_assignment
     WHERE complaint_id = v_assigned AND completed_date IS NULL;

    SAVEPOINT integrity_suite;

    expect_error('No OPEN -> CLOSED shortcut',
        'UPDATE complaint SET status = ''CLOSED'' WHERE complaint_id = ' || v_open, -20011);
    expect_error('Cannot directly ASSIGN without staff assignment',
        'UPDATE complaint SET status = ''ASSIGNED'' WHERE complaint_id = ' || v_open, -20014);
    expect_error('No ASSIGNED -> RESOLVED shortcut',
        'UPDATE complaint SET status = ''RESOLVED'', resolution_remark = ''done'' WHERE complaint_id = ' || v_assigned,
        -20011);
    expect_error('Cannot insert a non-OPEN complaint',
        'INSERT INTO complaint (student_id, category_id, title, description, status) ' ||
        'SELECT student_id, category_id, ''bad'', ''bad'', ''CLOSED'' FROM complaint WHERE complaint_id = ' || v_open,
        -20011);
    expect_error('Resolved complaint cannot be newly assigned',
        'INSERT INTO complaint_assignment (complaint_id, staff_id) VALUES (' || v_resolved || ',' || v_staff || ')',
        -20032);
    expect_error('Cannot complete assignment before resolution',
        'UPDATE complaint_assignment SET completed_date = SYSDATE WHERE assignment_id = ' || v_asg,
        -20036);
    expect_error('Cannot change assigned staff by direct UPDATE',
        'UPDATE complaint_assignment SET staff_id = ' || v_staff || ' WHERE assignment_id = ' || v_asg,
        -20033);
    expect_error('Cannot give feedback before resolution',
        'INSERT INTO complaint_feedback (complaint_id, rating) VALUES (' || v_open || ',4)', -20040);
    expect_error('Cannot move existing feedback to another complaint',
        'UPDATE complaint_feedback SET complaint_id = ' || v_open ||
        ' WHERE complaint_id = ' || v_resolved, -20044);
    expect_error('Cannot submit second feedback for same complaint',
        'BEGIN sp_submit_feedback(' || v_resolved || ',' || v_student || ',4); END;', -20043);
    expect_error('Complaints cannot be deleted',
        'DELETE FROM complaint WHERE complaint_id = ' || v_open, -20017);
    expect_error('Status history cannot be rewritten',
        'DELETE FROM complaint_status WHERE complaint_id = ' || v_resolved, -20045);
    expect_error('Room block cannot change while occupied',
        'UPDATE room SET block = ''Z'' WHERE room_id = ' || v_room, -20026);

    -- Changing STUDENT.block directly is automatically corrected from ROOM.
    UPDATE student SET block = 'Z' WHERE student_id = v_student;
    SELECT block INTO v_block FROM student WHERE student_id = v_student;
    IF v_block <> 'A' THEN
        RAISE_APPLICATION_ERROR(-20992, 'FAIL student block synchronization.');
    END IF;
    v_tests := v_tests + 1;
    DBMS_OUTPUT.PUT_LINE('PASS: Student block remains synchronized with room');

    -- Fill room A-101 (capacity 2) and check both procedure and direct DML.
    sp_register_student('Temporary Occupant', 'temp_occupant@hostel.edu',
        'test_hash_only', NULL, v_room, v_temp);
    expect_error('Registration procedure rejects a full room',
        'DECLARE x NUMBER; BEGIN sp_register_student(''Third'', ' ||
        '''third_student@hostel.edu'', ''test_hash_only'', NULL, ' || v_room || ', x); END;', -20021);
    expect_error('Direct INSERT cannot bypass room capacity',
        'INSERT INTO student (name, email, password, room_id) ' ||
        'VALUES (''Fourth'', ''fourth_student@hostel.edu'', ''test_hash_only'', ' || v_room || ')', -20021);
    expect_error('Cannot reduce room capacity below active occupancy',
        'UPDATE room SET capacity = 1 WHERE room_id = ' || v_room, -20025);

    -- Procedure must reject missing resolution remark when transition is valid.
    SAVEPOINT resolve_test;
    sp_update_status(v_assigned, 'IN_PROGRESS', NULL, 'test_actor');
    expect_error('RESOLVED requires a resolution remark',
        'BEGIN sp_update_status(' || v_assigned || ',''RESOLVED''); END;', -20010);
    ROLLBACK TO resolve_test;

    -- Existing resolved complaint may be closed, then becomes immutable.
    SAVEPOINT closed_test;
    sp_update_status(v_resolved, 'CLOSED', NULL, 'test_actor');
    expect_error('Closed complaint title cannot be modified',
        'UPDATE complaint SET title = ''changed'' WHERE complaint_id = ' || v_resolved, -20012);
    ROLLBACK TO closed_test;

    -- A complete resolved lifecycle should have OPEN, ASSIGNED,
    -- IN_PROGRESS and RESOLVED history entries.
    SELECT COUNT(*) INTO v_count FROM complaint_status
     WHERE complaint_id = v_resolved;
    IF v_count <> 4 THEN
        RAISE_APPLICATION_ERROR(-20993,
            'FAIL status audit expected 4 records, got ' || v_count);
    END IF;
    v_tests := v_tests + 1;
    DBMS_OUTPUT.PUT_LINE('PASS: Four audit records for resolved complaint');

    SELECT COUNT(*) INTO v_count FROM complaint_assignment
     WHERE complaint_id = v_resolved AND completed_date IS NULL;
    IF v_count <> 0 THEN
        RAISE_APPLICATION_ERROR(-20994,
            'FAIL resolved complaint still has unfinished assignment.');
    END IF;
    v_tests := v_tests + 1;
    DBMS_OUTPUT.PUT_LINE('PASS: Resolved complaint assignment automatically completed');

    ROLLBACK TO integrity_suite;
    DBMS_OUTPUT.PUT_LINE('=== ' || v_tests || ' SQL integrity assertions passed; fixtures unchanged ===');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO integrity_suite;
        RAISE;
END;
/

PROMPT === Integrity tests finished ===

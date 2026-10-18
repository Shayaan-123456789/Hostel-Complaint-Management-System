-- =====================================================================
-- 03_procedures.sql : business procedures + cursor-based reports
-- Run with:  SET SERVEROUTPUT ON SIZE UNLIMITED
-- =====================================================================
SET ECHO ON
SET DEFINE OFF
SET SERVEROUTPUT ON SIZE UNLIMITED

-- =====================================================================
-- A. TRANSACTION PROCEDURES
-- =====================================================================

-- A1. Register a student (locks room to serialize capacity checks)
-- A STUDENT compound trigger also guards direct inserts/transfers/activations.
CREATE OR REPLACE PROCEDURE sp_register_student (
    p_name       IN  student.name%TYPE,
    p_email      IN  student.email%TYPE,
    p_password   IN  student.password%TYPE,      -- already hashed by Django
    p_phone      IN  student.phone%TYPE,
    p_room_id    IN  student.room_id%TYPE,
    p_student_id OUT student.student_id%TYPE
) AS
    v_capacity room.capacity%TYPE;
    v_occupied PLS_INTEGER;
BEGIN
    BEGIN
        SELECT capacity INTO v_capacity FROM room
         WHERE room_id = p_room_id FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20020, 'Room ' || p_room_id || ' does not exist.');
    END;

    SELECT COUNT(*) INTO v_occupied
      FROM student WHERE room_id = p_room_id AND status = 'ACTIVE';

    IF v_occupied >= v_capacity THEN
        RAISE_APPLICATION_ERROR(-20021, 'Room is full (capacity ' || v_capacity || ').');
    END IF;

    INSERT INTO student (name, email, password, phone, room_id)
    VALUES (p_name, p_email, p_password, p_phone, p_room_id)
    RETURNING student_id INTO p_student_id;
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(-20022, 'A student with this email already exists.');
END sp_register_student;
/
SHOW ERRORS

-- A2. Student submits a complaint (+ optional photo)  -- FR2, FR3, FR4
CREATE OR REPLACE PROCEDURE sp_submit_complaint (
    p_student_id   IN  complaint.student_id%TYPE,
    p_category_id  IN  complaint.category_id%TYPE,
    p_title        IN  complaint.title%TYPE,
    p_description  IN  complaint.description%TYPE,
    p_priority     IN  complaint.priority%TYPE,
    p_photo_path   IN  complaint_photo.photo_path%TYPE,   -- pass NULL if no photo
    p_complaint_id OUT complaint.complaint_id%TYPE
) AS
    v_status student.status%TYPE;
    v_prev_identifier VARCHAR2(64) := SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER');
BEGIN
    BEGIN
        SELECT status INTO v_status FROM student WHERE student_id = p_student_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'Student ' || p_student_id || ' does not exist.');
    END;
    IF v_status <> 'ACTIVE' THEN
        RAISE_APPLICATION_ERROR(-20003, 'Inactive students cannot submit complaints.');
    END IF;

    DBMS_SESSION.SET_IDENTIFIER(SUBSTR('STUDENT:' || p_student_id, 1, 64));

    INSERT INTO complaint (student_id, category_id, title, description, priority)
    VALUES (p_student_id, p_category_id, p_title, p_description, UPPER(p_priority))
    RETURNING complaint_id INTO p_complaint_id;

    IF p_photo_path IS NOT NULL THEN
        INSERT INTO complaint_photo (complaint_id, photo_path)
        VALUES (p_complaint_id, p_photo_path);
    END IF;

    IF v_prev_identifier IS NULL THEN
        DBMS_SESSION.CLEAR_IDENTIFIER;
    ELSE
        DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF v_prev_identifier IS NULL THEN
            DBMS_SESSION.CLEAR_IDENTIFIER;
        ELSE
            DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
        END IF;
        RAISE;
END sp_submit_complaint;
/
SHOW ERRORS

-- A3. Attach an extra photo to an existing complaint
CREATE OR REPLACE PROCEDURE sp_add_photo (
    p_complaint_id IN complaint_photo.complaint_id%TYPE,
    p_photo_path   IN complaint_photo.photo_path%TYPE
) AS
BEGIN
    INSERT INTO complaint_photo (complaint_id, photo_path)
    VALUES (p_complaint_id, p_photo_path);
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -2291 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Complaint ' || p_complaint_id || ' does not exist.');
        END IF;
        RAISE;
END sp_add_photo;
/
SHOW ERRORS

-- A4. Admin assigns a complaint to staff  -- FR6
--     (trigger trg_assignment_ai moves the complaint OPEN -> ASSIGNED)
CREATE OR REPLACE PROCEDURE sp_assign_complaint (
    p_complaint_id IN complaint.complaint_id%TYPE,
    p_staff_id     IN staff.staff_id%TYPE,
    p_admin_name   IN VARCHAR2 DEFAULT USER
) AS
    v_status complaint.status%TYPE;
    v_prev_identifier VARCHAR2(64) := SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER');
BEGIN
    BEGIN
        SELECT status INTO v_status FROM complaint
         WHERE complaint_id = p_complaint_id FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'Complaint ' || p_complaint_id || ' does not exist.');
    END;

    IF v_status <> 'OPEN' THEN
        RAISE_APPLICATION_ERROR(-20002, 'Only OPEN complaints can be assigned (current: ' || v_status || ').');
    END IF;

    DBMS_SESSION.SET_IDENTIFIER(SUBSTR(p_admin_name, 1, 64));

    INSERT INTO complaint_assignment (complaint_id, staff_id)
    VALUES (p_complaint_id, p_staff_id);

    IF v_prev_identifier IS NULL THEN
        DBMS_SESSION.CLEAR_IDENTIFIER;
    ELSE
        DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF v_prev_identifier IS NULL THEN
            DBMS_SESSION.CLEAR_IDENTIFIER;
        ELSE
            DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
        END IF;
        RAISE;
END sp_assign_complaint;
/
SHOW ERRORS

-- A5. Staff/admin updates status  -- FR7, FR8
--     Allowed path: ASSIGNED -> IN_PROGRESS -> RESOLVED -> CLOSED
CREATE OR REPLACE PROCEDURE sp_update_status (
    p_complaint_id IN complaint.complaint_id%TYPE,
    p_new_status   IN complaint.status%TYPE,
    p_remark       IN complaint.resolution_remark%TYPE DEFAULT NULL,
    p_changed_by   IN VARCHAR2 DEFAULT USER
) AS
    v_old complaint.status%TYPE;
    v_new complaint.status%TYPE := UPPER(p_new_status);
    v_prev_identifier VARCHAR2(64) := SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER');
BEGIN
    BEGIN
        SELECT status INTO v_old FROM complaint
         WHERE complaint_id = p_complaint_id FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'Complaint ' || p_complaint_id || ' does not exist.');
    END;

    IF NOT (   (v_old = 'ASSIGNED'    AND v_new = 'IN_PROGRESS')
            OR (v_old = 'IN_PROGRESS' AND v_new = 'RESOLVED')
            OR (v_old = 'RESOLVED'    AND v_new = 'CLOSED')) THEN
        RAISE_APPLICATION_ERROR(-20011, 'Invalid status change: ' || v_old || ' -> ' || v_new);
    END IF;

    DBMS_SESSION.SET_IDENTIFIER(SUBSTR(p_changed_by, 1, 64));

    UPDATE complaint
       SET status            = v_new,
           resolution_remark = NVL(p_remark, resolution_remark)
     WHERE complaint_id = p_complaint_id;

    -- The status-log compound trigger atomically completes the assignment
    -- when this status becomes RESOLVED, including direct table updates.
    IF v_prev_identifier IS NULL THEN
        DBMS_SESSION.CLEAR_IDENTIFIER;
    ELSE
        DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        IF v_prev_identifier IS NULL THEN
            DBMS_SESSION.CLEAR_IDENTIFIER;
        ELSE
            DBMS_SESSION.SET_IDENTIFIER(v_prev_identifier);
        END IF;
        RAISE;
END sp_update_status;
/
SHOW ERRORS

-- A6. Student gives rating/feedback  -- FR10
CREATE OR REPLACE PROCEDURE sp_submit_feedback (
    p_complaint_id IN complaint_feedback.complaint_id%TYPE,
    p_student_id   IN complaint.student_id%TYPE,
    p_rating       IN complaint_feedback.rating%TYPE,
    p_comments     IN complaint_feedback.comments%TYPE DEFAULT NULL
) AS
    v_owner complaint.student_id%TYPE;
BEGIN
    BEGIN
        SELECT student_id INTO v_owner FROM complaint WHERE complaint_id = p_complaint_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'Complaint ' || p_complaint_id || ' does not exist.');
    END;

    IF v_owner <> p_student_id THEN
        RAISE_APPLICATION_ERROR(-20042, 'Only the student who raised the complaint can rate it.');
    END IF;

    INSERT INTO complaint_feedback (complaint_id, rating, comments)
    VALUES (p_complaint_id, p_rating, p_comments);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(-20043, 'Feedback already submitted for this complaint.');
END sp_submit_feedback;
/
SHOW ERRORS

-- =====================================================================
-- B. CURSOR-BASED PROCEDURES
-- =====================================================================

-- B1. EXPLICIT cursor with parameter (OPEN / FETCH / CLOSE, %NOTFOUND, %ROWCOUNT)
CREATE OR REPLACE PROCEDURE sp_list_complaints_by_status (
    p_status IN complaint.status%TYPE
) AS
    CURSOR c_cmp (cp_status complaint.status%TYPE) IS
        SELECT c.complaint_id, c.title, c.priority,
               s.name AS student_name, r.block, r.room_number, c.created_date
          FROM complaint c
          JOIN student s ON s.student_id = c.student_id
          JOIN room    r ON r.room_id    = s.room_id
         WHERE c.status = cp_status
         ORDER BY CASE c.priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2
                                  WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                  c.created_date;
    v_row c_cmp%ROWTYPE;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Complaints with status ' || UPPER(p_status));
    DBMS_OUTPUT.PUT_LINE(RPAD('ID', 7) || RPAD('PRIORITY', 10) || RPAD('TITLE', 30) ||
                         RPAD('STUDENT', 20) || 'ROOM');
    OPEN c_cmp(UPPER(p_status));
    LOOP
        FETCH c_cmp INTO v_row;
        EXIT WHEN c_cmp%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(RPAD(v_row.complaint_id, 7) || RPAD(v_row.priority, 10) ||
                             RPAD(SUBSTR(v_row.title, 1, 28), 30) ||
                             RPAD(SUBSTR(v_row.student_name, 1, 18), 20) ||
                             v_row.block || '-' || v_row.room_number);
    END LOOP;
    DBMS_OUTPUT.PUT_LINE(c_cmp%ROWCOUNT || ' row(s).');
    CLOSE c_cmp;
END sp_list_complaints_by_status;
/
SHOW ERRORS

-- B2. CURSOR FOR loop : status history of one complaint
CREATE OR REPLACE PROCEDURE sp_complaint_history (
    p_complaint_id IN complaint.complaint_id%TYPE
) AS
    v_found BOOLEAN := FALSE;
BEGIN
    DBMS_OUTPUT.PUT_LINE('History of complaint ' || p_complaint_id);
    FOR h IN (SELECT old_status, new_status, changed_by, change_date
                FROM complaint_status
               WHERE complaint_id = p_complaint_id
               ORDER BY status_id) LOOP
        v_found := TRUE;
        DBMS_OUTPUT.PUT_LINE(TO_CHAR(h.change_date, 'DD-MON-YYYY HH24:MI:SS') || '  ' ||
                             RPAD(NVL(h.old_status, '(new)'), 12) || ' -> ' ||
                             RPAD(h.new_status, 12) || ' by ' || h.changed_by);
    END LOOP;
    IF NOT v_found THEN
        DBMS_OUTPUT.PUT_LINE('No history found.');
    END IF;
END sp_complaint_history;
/
SHOW ERRORS

-- B3. Cursor with GROUP BY / HAVING  -- FR11 dashboard numbers
CREATE OR REPLACE PROCEDURE sp_category_summary (
    p_min_total IN NUMBER DEFAULT 0
) AS
    CURSOR c_sum (cp_min NUMBER) IS
        SELECT cat.category_name,
               COUNT(c.complaint_id) AS total_cnt,
               NVL(SUM(CASE WHEN c.status IN ('RESOLVED','CLOSED') THEN 1 ELSE 0 END), 0) AS resolved_cnt,
               ROUND(AVG(f.rating), 2) AS avg_rating
          FROM category cat
          LEFT JOIN complaint c ON c.category_id = cat.category_id
          LEFT JOIN complaint_feedback f ON f.complaint_id = c.complaint_id
         GROUP BY cat.category_name
        HAVING COUNT(c.complaint_id) >= cp_min
         ORDER BY total_cnt DESC, cat.category_name;
BEGIN
    DBMS_OUTPUT.PUT_LINE(RPAD('CATEGORY', 20) || RPAD('TOTAL', 8) || RPAD('RESOLVED', 10) || 'AVG RATING');
    FOR r IN c_sum(p_min_total) LOOP
        DBMS_OUTPUT.PUT_LINE(RPAD(r.category_name, 20) || RPAD(r.total_cnt, 8) ||
                             RPAD(r.resolved_cnt, 10) || NVL(TO_CHAR(r.avg_rating), '-'));
    END LOOP;
END sp_category_summary;
/
SHOW ERRORS

-- B4. NESTED parameterised cursors : pending work for each active staff member
CREATE OR REPLACE PROCEDURE sp_staff_workload AS
    CURSOR c_staff IS
        SELECT staff_id, name, department
          FROM staff WHERE status = 'ACTIVE' ORDER BY name;

    CURSOR c_work (cp_staff staff.staff_id%TYPE) IS
        SELECT c.complaint_id, c.title, c.priority, c.status
          FROM complaint c
          JOIN complaint_assignment a ON a.complaint_id = c.complaint_id
         WHERE a.staff_id = cp_staff
           AND a.completed_date IS NULL
           AND c.status IN ('ASSIGNED', 'IN_PROGRESS')
         ORDER BY c.created_date;

    v_count PLS_INTEGER;
BEGIN
    FOR s IN c_staff LOOP
        DBMS_OUTPUT.PUT_LINE(s.name || ' (' || s.department || ')');
        v_count := 0;
        FOR w IN c_work(s.staff_id) LOOP
            v_count := v_count + 1;
            DBMS_OUTPUT.PUT_LINE('   #' || w.complaint_id || '  ' || RPAD(w.status, 12) ||
                                 RPAD(w.priority, 8) || w.title);
        END LOOP;
        IF v_count = 0 THEN
            DBMS_OUTPUT.PUT_LINE('   (no pending work)');
        END IF;
    END LOOP;
END sp_staff_workload;
/
SHOW ERRORS

-- B5. FOR UPDATE cursor + WHERE CURRENT OF : raise priority of overdue complaints
--     LOW -> MEDIUM -> HIGH -> URGENT (one step per run)
CREATE OR REPLACE PROCEDURE sp_escalate_overdue (
    p_days IN NUMBER DEFAULT 3
) AS
    CURSOR c_old (cp_days NUMBER) IS
        SELECT complaint_id, priority
          FROM complaint
         WHERE status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS')
           AND priority <> 'URGENT'
           AND created_date < SYSDATE - cp_days
           FOR UPDATE OF priority;
    v_n PLS_INTEGER := 0;
BEGIN
    IF p_days IS NULL OR p_days < 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Overdue days must be non-negative.');
    END IF;
    FOR r IN c_old(p_days) LOOP
        UPDATE complaint
           SET priority = CASE r.priority WHEN 'LOW'    THEN 'MEDIUM'
                                          WHEN 'MEDIUM' THEN 'HIGH'
                                          ELSE 'URGENT' END
         WHERE CURRENT OF c_old;
        v_n := v_n + 1;
    END LOOP;
    -- Do not COMMIT here: Django/the caller owns this transaction.
    DBMS_OUTPUT.PUT_LINE(v_n || ' complaint(s) escalated (older than ' || p_days || ' days).');
END sp_escalate_overdue;
/
SHOW ERRORS

-- =====================================================================
-- C. REF CURSOR procedures (search/filter for the application layer)
-- =====================================================================

-- C1. Admin search/filter  -- FR5   (pass NULL to skip a filter)
CREATE OR REPLACE PROCEDURE sp_search_complaints (
    p_status   IN  VARCHAR2 DEFAULT NULL,
    p_category IN  VARCHAR2 DEFAULT NULL,
    p_block    IN  VARCHAR2 DEFAULT NULL,
    p_priority IN  VARCHAR2 DEFAULT NULL,
    p_result   OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT *
          FROM v_complaint_details v
         WHERE (p_status   IS NULL OR v.status        = UPPER(p_status))
           AND (p_category IS NULL OR v.category_name = p_category)
           AND (p_block    IS NULL OR v.block         = p_block)
           AND (p_priority IS NULL OR v.priority      = UPPER(p_priority))
         ORDER BY CASE v.priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2
                                  WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                  v.created_date;
END sp_search_complaints;
/
SHOW ERRORS

-- C2. Student's own complaints  -- FR9
CREATE OR REPLACE PROCEDURE sp_student_complaints (
    p_student_id IN  complaint.student_id%TYPE,
    p_result     OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT *
          FROM v_complaint_details
         WHERE student_id = p_student_id
         ORDER BY created_date DESC;
END sp_student_complaints;
/
SHOW ERRORS

PROMPT === Procedures complete ===

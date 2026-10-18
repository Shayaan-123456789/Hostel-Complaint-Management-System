-- =====================================================================
-- 02_triggers.sql : ID generation, lifecycle, history, room integrity
-- Oracle 11g+ (compound triggers); existing nine-table schema unchanged.
-- =====================================================================
SET ECHO ON
SET DEFINE OFF

-- ---------- ID generators ----------
CREATE OR REPLACE TRIGGER trg_room_bi
BEFORE INSERT ON room FOR EACH ROW
WHEN (NEW.room_id IS NULL)
BEGIN
    :NEW.room_id := seq_room.NEXTVAL;
END;
/
SHOW ERRORS

CREATE OR REPLACE TRIGGER trg_category_bi
BEFORE INSERT ON category FOR EACH ROW
WHEN (NEW.category_id IS NULL)
BEGIN
    :NEW.category_id := seq_category.NEXTVAL;
END;
/
SHOW ERRORS

CREATE OR REPLACE TRIGGER trg_staff_bi
BEFORE INSERT ON staff FOR EACH ROW
WHEN (NEW.staff_id IS NULL)
BEGIN
    :NEW.staff_id := seq_staff.NEXTVAL;
END;
/
SHOW ERRORS

CREATE OR REPLACE TRIGGER trg_photo_bi
BEFORE INSERT ON complaint_photo FOR EACH ROW
WHEN (NEW.photo_id IS NULL)
BEGIN
    :NEW.photo_id := seq_photo.NEXTVAL;
END;
/
SHOW ERRORS

CREATE OR REPLACE TRIGGER trg_cstatus_bi
BEFORE INSERT ON complaint_status FOR EACH ROW
WHEN (NEW.status_id IS NULL)
BEGIN
    :NEW.status_id := seq_status.NEXTVAL;
END;
/
SHOW ERRORS

-- ---------- ROOM: no inconsistent block/capacity updates ----------
-- The STUDENT compound trigger below locks ROOM rows. An UPDATE to ROOM
-- also takes the same row lock, serializing capacity changes and admissions.
CREATE OR REPLACE TRIGGER trg_room_bu_integrity
BEFORE UPDATE OF room_id, block, capacity ON room
FOR EACH ROW
DECLARE
    v_total  PLS_INTEGER;
    v_active PLS_INTEGER;
BEGIN
    IF :NEW.room_id <> :OLD.room_id THEN
        RAISE_APPLICATION_ERROR(-20024, 'Changing a room ID is not supported.');
    END IF;

    IF :NEW.block <> :OLD.block THEN
        SELECT COUNT(*) INTO v_total FROM student WHERE room_id = :OLD.room_id;
        IF v_total > 0 THEN
            RAISE_APPLICATION_ERROR(-20026,
                'Cannot change a room block while students reference the room.');
        END IF;
    END IF;

    IF :NEW.capacity < :OLD.capacity THEN
        SELECT COUNT(*) INTO v_active
          FROM student
         WHERE room_id = :OLD.room_id AND status = 'ACTIVE';
        IF v_active > :NEW.capacity THEN
            RAISE_APPLICATION_ERROR(-20025,
                'Room capacity cannot be lower than its active occupancy.');
        END IF;
    END IF;
END;
/
SHOW ERRORS

-- ---------- STUDENT: ID, authoritative block and capacity ----------
-- BEFORE EACH ROW: lock target ROOM so two sessions cannot independently
-- admit the last available place, and derive STUDENT.block from ROOM.block.
-- AFTER STATEMENT: count students safely (not in the row trigger, because
-- reading STUDENT there would raise ORA-04091: mutating table).
-- This covers direct INSERTs, transfers, and ACTIVE/INACTIVE status changes.
CREATE OR REPLACE TRIGGER trg_student_bi_bu
FOR INSERT OR UPDATE OF room_id, status, block ON student
COMPOUND TRIGGER
    TYPE t_room_ids IS TABLE OF room.room_id%TYPE INDEX BY PLS_INTEGER;
    g_rooms t_room_ids;
    g_count PLS_INTEGER := 0;

    BEFORE EACH ROW IS
        v_block room.block%TYPE;
    BEGIN
        IF INSERTING AND :NEW.student_id IS NULL THEN
            :NEW.student_id := seq_student.NEXTVAL;
        END IF;

        BEGIN
            SELECT block INTO v_block
              FROM room
             WHERE room_id = :NEW.room_id
             FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                RAISE_APPLICATION_ERROR(-20020,
                    'Room ' || :NEW.room_id || ' does not exist.');
        END;
        :NEW.block := v_block;
        g_count := g_count + 1;
        g_rooms(g_count) := :NEW.room_id;
    END BEFORE EACH ROW;

    AFTER STATEMENT IS
        v_capacity room.capacity%TYPE;
        v_active PLS_INTEGER;
    BEGIN
        FOR i IN 1 .. g_count LOOP
            SELECT capacity INTO v_capacity
              FROM room WHERE room_id = g_rooms(i);
            SELECT COUNT(*) INTO v_active
              FROM student
             WHERE room_id = g_rooms(i) AND status = 'ACTIVE';
            IF v_active > v_capacity THEN
                RAISE_APPLICATION_ERROR(-20021,
                    'Room ' || g_rooms(i) || ' is full (capacity ' || v_capacity || ').');
            END IF;
        END LOOP;
    END AFTER STATEMENT;
END trg_student_bi_bu;
/
SHOW ERRORS

-- ---------- COMPLAINT: immutable CLOSED, strict lifecycle ----------
-- OPEN -> ASSIGNED -> IN_PROGRESS -> RESOLVED -> CLOSED.
-- For ASSIGNED/IN_PROGRESS/RESOLVED, require an unfinished assignment.
-- The assignment AFTER STATEMENT trigger makes its row visible here,
-- avoiding a mutating-table error.
CREATE OR REPLACE TRIGGER trg_complaint_bi_bu
BEFORE INSERT OR UPDATE ON complaint FOR EACH ROW
DECLARE
    v_active_assignment PLS_INTEGER;
BEGIN
    IF INSERTING THEN
        IF :NEW.complaint_id IS NULL THEN
            :NEW.complaint_id := seq_complaint.NEXTVAL;
        END IF;
        IF :NEW.status <> 'OPEN' THEN
            RAISE_APPLICATION_ERROR(-20011, 'New complaints must start as OPEN.');
        END IF;
        IF :NEW.resolved_date IS NOT NULL OR :NEW.resolution_remark IS NOT NULL THEN
            RAISE_APPLICATION_ERROR(-20010,
                'A new complaint cannot have resolution details.');
        END IF;
    ELSIF UPDATING THEN
        IF :OLD.status = 'CLOSED' THEN
            RAISE_APPLICATION_ERROR(-20012, 'Closed complaints cannot be modified.');
        END IF;
        IF :NEW.complaint_id <> :OLD.complaint_id OR
           :NEW.student_id   <> :OLD.student_id THEN
            RAISE_APPLICATION_ERROR(-20013,
                'Complaint ID and owning student cannot be changed.');
        END IF;
        IF :NEW.status <> :OLD.status THEN
            IF NOT (
                (:OLD.status = 'OPEN'        AND :NEW.status = 'ASSIGNED') OR
                (:OLD.status = 'ASSIGNED'    AND :NEW.status = 'IN_PROGRESS') OR
                (:OLD.status = 'IN_PROGRESS' AND :NEW.status = 'RESOLVED') OR
                (:OLD.status = 'RESOLVED'    AND :NEW.status = 'CLOSED')
            ) THEN
                RAISE_APPLICATION_ERROR(-20011,
                    'Invalid status change: ' || :OLD.status || ' -> ' || :NEW.status);
            END IF;

            IF :NEW.status IN ('ASSIGNED', 'IN_PROGRESS', 'RESOLVED') THEN
                SELECT COUNT(*) INTO v_active_assignment
                  FROM complaint_assignment
                 WHERE complaint_id = :NEW.complaint_id
                   AND completed_date IS NULL;
                IF v_active_assignment <> 1 THEN
                    RAISE_APPLICATION_ERROR(-20014,
                        'Exactly one unfinished assignment is required.');
                END IF;
            END IF;
        END IF;
    END IF;

    IF :NEW.status = 'RESOLVED' THEN
        IF :NEW.resolution_remark IS NULL THEN
            RAISE_APPLICATION_ERROR(-20010,
                'Resolution remark is required to resolve a complaint.');
        END IF;
        IF :NEW.resolved_date IS NULL THEN
            :NEW.resolved_date := SYSDATE;
        END IF;
    ELSIF :NEW.status = 'CLOSED' THEN
        IF :NEW.resolution_remark IS NULL OR :NEW.resolved_date IS NULL THEN
            RAISE_APPLICATION_ERROR(-20010,
                'Closed complaints require an existing resolution.');
        END IF;
    ELSE
        IF :NEW.resolved_date IS NOT NULL THEN
            RAISE_APPLICATION_ERROR(-20015,
                'Only resolved or closed complaints may have a resolution date.');
        END IF;
    END IF;
END;
/
SHOW ERRORS

-- ---------- COMPLAINT: status history + assignment completion ----------
-- Using AFTER STATEMENT for assignment completion means an assignment
-- trigger can validate COMPLAINT.status without hitting ORA-04091.
CREATE OR REPLACE TRIGGER trg_complaint_status_log
FOR INSERT OR UPDATE OF status ON complaint
COMPOUND TRIGGER
    TYPE t_ids IS TABLE OF complaint.complaint_id%TYPE INDEX BY PLS_INTEGER;
    g_resolved t_ids;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
        v_by VARCHAR2(100);
    BEGIN
        v_by := NVL(SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER'), USER);
        IF INSERTING THEN
            INSERT INTO complaint_status (complaint_id, old_status, new_status, changed_by)
            VALUES (:NEW.complaint_id, NULL, :NEW.status, v_by);
        ELSIF :OLD.status <> :NEW.status THEN
            INSERT INTO complaint_status (complaint_id, old_status, new_status, changed_by)
            VALUES (:NEW.complaint_id, :OLD.status, :NEW.status, v_by);
            IF :NEW.status = 'RESOLVED' THEN
                g_count := g_count + 1;
                g_resolved(g_count) := :NEW.complaint_id;
            END IF;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_count LOOP
            UPDATE complaint_assignment
               SET completed_date = SYSDATE
             WHERE complaint_id = g_resolved(i)
               AND completed_date IS NULL;
            IF SQL%ROWCOUNT <> 1 THEN
                RAISE_APPLICATION_ERROR(-20016,
                    'Resolved complaint must complete exactly one assignment.');
            END IF;
        END LOOP;
    END AFTER STATEMENT;
END trg_complaint_status_log;
/
SHOW ERRORS

-- ---------- COMPLAINT: preserve status history and feedback ----------
CREATE OR REPLACE TRIGGER trg_complaint_bd
BEFORE DELETE ON complaint FOR EACH ROW
BEGIN
    RAISE_APPLICATION_ERROR(-20017,
        'Complaints cannot be deleted; close them to preserve audit history.');
END;
/
SHOW ERRORS

-- ---------- ASSIGNMENT: active staff and OPEN complaint ----------
CREATE OR REPLACE TRIGGER trg_assignment_bi
BEFORE INSERT ON complaint_assignment FOR EACH ROW
DECLARE
    v_staff_status staff.status%TYPE;
    v_cmp_status   complaint.status%TYPE;
BEGIN
    IF :NEW.assignment_id IS NULL THEN
        :NEW.assignment_id := seq_assignment.NEXTVAL;
    END IF;
    IF :NEW.completed_date IS NOT NULL THEN
        RAISE_APPLICATION_ERROR(-20033,
            'A new assignment cannot already be completed.');
    END IF;

    BEGIN
        SELECT status INTO v_cmp_status
          FROM complaint
         WHERE complaint_id = :NEW.complaint_id
         FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001,
                'Complaint ' || :NEW.complaint_id || ' does not exist.');
    END;
    IF v_cmp_status <> 'OPEN' THEN
        RAISE_APPLICATION_ERROR(-20032,
            'Only OPEN complaints can receive a new assignment.');
    END IF;

    BEGIN
        SELECT status INTO v_staff_status
          FROM staff WHERE staff_id = :NEW.staff_id FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20031,
                'Staff member ' || :NEW.staff_id || ' does not exist.');
    END;
    IF v_staff_status <> 'ACTIVE' THEN
        RAISE_APPLICATION_ERROR(-20030,
            'Staff member ' || :NEW.staff_id || ' is not active.');
    END IF;
END;
/
SHOW ERRORS

-- ---------- ASSIGNMENT: do not rewrite assignments or finish early ----------
CREATE OR REPLACE TRIGGER trg_assignment_bu
BEFORE UPDATE OF complaint_id, staff_id, completed_date ON complaint_assignment
FOR EACH ROW
DECLARE
    v_cmp_status complaint.status%TYPE;
BEGIN
    IF :NEW.complaint_id <> :OLD.complaint_id OR
       :NEW.staff_id <> :OLD.staff_id THEN
        RAISE_APPLICATION_ERROR(-20033,
            'Assignment complaint and staff cannot be reassigned by UPDATE.');
    END IF;
    IF :OLD.completed_date IS NOT NULL AND
       (:NEW.completed_date IS NULL OR :NEW.completed_date <> :OLD.completed_date) THEN
        RAISE_APPLICATION_ERROR(-20035, 'Completed assignments cannot be reopened or changed.');
    END IF;
    IF :OLD.completed_date IS NULL AND :NEW.completed_date IS NOT NULL THEN
        SELECT status INTO v_cmp_status
          FROM complaint WHERE complaint_id = :NEW.complaint_id;
        IF v_cmp_status NOT IN ('RESOLVED', 'CLOSED') THEN
            RAISE_APPLICATION_ERROR(-20036,
                'Only resolved complaints can have completed assignments.');
        END IF;
    END IF;
END;
/
SHOW ERRORS

-- ---------- ASSIGNMENT: new assignment automatically OPEN -> ASSIGNED ----------
-- AFTER STATEMENT is essential: the COMPLAINT trigger queries assignments.
-- A row-level AFTER INSERT trigger would cause ORA-04091 (mutating table).
CREATE OR REPLACE TRIGGER trg_assignment_ai
FOR INSERT ON complaint_assignment
COMPOUND TRIGGER
    TYPE t_ids IS TABLE OF complaint_assignment.complaint_id%TYPE INDEX BY PLS_INTEGER;
    g_ids t_ids;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_count := g_count + 1;
        g_ids(g_count) := :NEW.complaint_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_count LOOP
            UPDATE complaint
               SET status = 'ASSIGNED'
             WHERE complaint_id = g_ids(i) AND status = 'OPEN';
            IF SQL%ROWCOUNT <> 1 THEN
                RAISE_APPLICATION_ERROR(-20034,
                    'New assignment could not move its complaint to ASSIGNED.');
            END IF;
        END LOOP;
    END AFTER STATEMENT;
END trg_assignment_ai;
/
SHOW ERRORS

-- ---------- FEEDBACK: ID and eligibility on INSERT; immutable complaint FK ----------
CREATE OR REPLACE TRIGGER trg_feedback_bi
BEFORE INSERT OR UPDATE OF complaint_id ON complaint_feedback
FOR EACH ROW
DECLARE
    v_status complaint.status%TYPE;
BEGIN
    IF INSERTING AND :NEW.feedback_id IS NULL THEN
        :NEW.feedback_id := seq_feedback.NEXTVAL;
    END IF;
    IF UPDATING AND :NEW.complaint_id <> :OLD.complaint_id THEN
        RAISE_APPLICATION_ERROR(-20044,
            'Feedback cannot be moved to a different complaint.');
    END IF;
    BEGIN
        SELECT status INTO v_status
          FROM complaint WHERE complaint_id = :NEW.complaint_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20041,
                'Complaint ' || :NEW.complaint_id || ' does not exist.');
    END;
    IF v_status NOT IN ('RESOLVED', 'CLOSED') THEN
        RAISE_APPLICATION_ERROR(-20040,
            'Feedback is allowed only after the complaint is resolved.');
    END IF;
END;
/
SHOW ERRORS

-- ---------- Audit records are append-only ----------
CREATE OR REPLACE TRIGGER trg_cstatus_immutable
BEFORE UPDATE OR DELETE ON complaint_status FOR EACH ROW
BEGIN
    RAISE_APPLICATION_ERROR(-20045, 'Complaint status history is append-only.');
END;
/
SHOW ERRORS

PROMPT === Triggers complete ===

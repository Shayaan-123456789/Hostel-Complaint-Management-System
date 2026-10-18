-- =====================================================================
-- 01_ddl.sql : Smart Hostel Complaint Management System (Oracle)
-- Tables, constraints, sequences, indexes, views  (final 3NF schema)
-- =====================================================================
SET ECHO ON
SET DEFINE OFF

-- ---------- Sequences (primary-key generators) ----------
CREATE SEQUENCE seq_room       START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_student    START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_category   START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_staff      START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_complaint  START WITH 1001 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_photo      START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_assignment START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_status     START WITH 1 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_feedback   START WITH 1 INCREMENT BY 1 NOCACHE;

-- ---------- ROOM ----------
CREATE TABLE room (
    room_id      NUMBER(6)    CONSTRAINT pk_room PRIMARY KEY,
    room_number  VARCHAR2(10) NOT NULL,
    block        VARCHAR2(10) NOT NULL,
    capacity     NUMBER(2)    NOT NULL
                 CONSTRAINT ck_room_capacity CHECK (capacity > 0),
    room_type    VARCHAR2(20) NOT NULL
                 CONSTRAINT ck_room_type CHECK (room_type IN ('SINGLE','DOUBLE','TRIPLE','DORMITORY')),
    CONSTRAINT uq_room_block_number UNIQUE (block, room_number)
);

-- ---------- STUDENT ----------
-- password must hold a HASH (e.g. Django make_password output), never plain text.
-- block is filled automatically from ROOM by trigger trg_student_bi_bu.
CREATE TABLE student (
    student_id  NUMBER(6)     CONSTRAINT pk_student PRIMARY KEY,
    name        VARCHAR2(100) NOT NULL,
    email       VARCHAR2(120) NOT NULL
                CONSTRAINT uq_student_email UNIQUE
                CONSTRAINT ck_student_email CHECK (REGEXP_LIKE(email, '^[^@ ]+@[^@ ]+\.[^@ ]+$')),
    password    VARCHAR2(255) NOT NULL,
    phone       VARCHAR2(15),
    room_id     NUMBER(6)     NOT NULL
                CONSTRAINT fk_student_room REFERENCES room(room_id),
    block       VARCHAR2(10),
    status      VARCHAR2(10)  DEFAULT 'ACTIVE' NOT NULL
                CONSTRAINT ck_student_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

-- ---------- CATEGORY ----------
CREATE TABLE category (
    category_id    NUMBER(4)     CONSTRAINT pk_category PRIMARY KEY,
    category_name  VARCHAR2(50)  NOT NULL CONSTRAINT uq_category_name UNIQUE,
    description    VARCHAR2(200)
);

-- ---------- STAFF ----------
CREATE TABLE staff (
    staff_id    NUMBER(6)     CONSTRAINT pk_staff PRIMARY KEY,
    name        VARCHAR2(100) NOT NULL,
    email       VARCHAR2(120) NOT NULL
                CONSTRAINT uq_staff_email UNIQUE
                CONSTRAINT ck_staff_email CHECK (REGEXP_LIKE(email, '^[^@ ]+@[^@ ]+\.[^@ ]+$')),
    password    VARCHAR2(255) NOT NULL,
    department  VARCHAR2(50)  NOT NULL,
    phone       VARCHAR2(15),
    status      VARCHAR2(10)  DEFAULT 'ACTIVE' NOT NULL
                CONSTRAINT ck_staff_status CHECK (status IN ('ACTIVE','INACTIVE'))
);

-- ---------- COMPLAINT ----------
CREATE TABLE complaint (
    complaint_id       NUMBER(8)      CONSTRAINT pk_complaint PRIMARY KEY,
    student_id         NUMBER(6)      NOT NULL
                       CONSTRAINT fk_cmp_student  REFERENCES student(student_id),
    category_id        NUMBER(4)      NOT NULL
                       CONSTRAINT fk_cmp_category REFERENCES category(category_id),
    title              VARCHAR2(150)  NOT NULL,
    description        VARCHAR2(2000) NOT NULL,
    priority           VARCHAR2(10)   DEFAULT 'MEDIUM' NOT NULL
                       CONSTRAINT ck_cmp_priority CHECK (priority IN ('LOW','MEDIUM','HIGH','URGENT')),
    status             VARCHAR2(15)   DEFAULT 'OPEN' NOT NULL
                       CONSTRAINT ck_cmp_status CHECK (status IN ('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED','CLOSED')),
    created_date       DATE           DEFAULT SYSDATE NOT NULL,
    resolved_date      DATE,
    resolution_remark  VARCHAR2(1000),
    CONSTRAINT ck_cmp_dates CHECK (resolved_date IS NULL OR resolved_date >= created_date)
);

-- ---------- COMPLAINT_PHOTO (file lives in Django MEDIA, only the path is stored) ----------
CREATE TABLE complaint_photo (
    photo_id       NUMBER(8)     CONSTRAINT pk_photo PRIMARY KEY,
    complaint_id   NUMBER(8)     NOT NULL
                   CONSTRAINT fk_photo_complaint REFERENCES complaint(complaint_id) ON DELETE CASCADE,
    photo_path     VARCHAR2(300) NOT NULL,
    uploaded_date  DATE          DEFAULT SYSDATE NOT NULL
);

-- ---------- COMPLAINT_ASSIGNMENT ----------
CREATE TABLE complaint_assignment (
    assignment_id  NUMBER(8) CONSTRAINT pk_assignment PRIMARY KEY,
    complaint_id   NUMBER(8) NOT NULL
                   CONSTRAINT fk_asg_complaint REFERENCES complaint(complaint_id) ON DELETE CASCADE,
    staff_id       NUMBER(6) NOT NULL
                   CONSTRAINT fk_asg_staff REFERENCES staff(staff_id),
    assigned_date  DATE      DEFAULT SYSDATE NOT NULL,
    completed_date DATE,
    CONSTRAINT ck_asg_dates CHECK (completed_date IS NULL OR completed_date >= assigned_date)
);

-- ---------- COMPLAINT_STATUS (status-change history) ----------
CREATE TABLE complaint_status (
    status_id     NUMBER(10)    CONSTRAINT pk_cstatus PRIMARY KEY,
    complaint_id  NUMBER(8)     NOT NULL
                  CONSTRAINT fk_cstatus_complaint REFERENCES complaint(complaint_id) ON DELETE CASCADE,
    old_status    VARCHAR2(15),
    new_status    VARCHAR2(15)  NOT NULL,
    changed_by    VARCHAR2(100) NOT NULL,
    change_date   TIMESTAMP     DEFAULT SYSTIMESTAMP NOT NULL
);

-- ---------- COMPLAINT_FEEDBACK (at most one per complaint) ----------
CREATE TABLE complaint_feedback (
    feedback_id    NUMBER(8)      CONSTRAINT pk_feedback PRIMARY KEY,
    complaint_id   NUMBER(8)      NOT NULL
                   CONSTRAINT uq_feedback_complaint UNIQUE
                   CONSTRAINT fk_fb_complaint REFERENCES complaint(complaint_id) ON DELETE CASCADE,
    rating         NUMBER(1)      NOT NULL
                   CONSTRAINT ck_fb_rating CHECK (rating BETWEEN 1 AND 5),
    comments       VARCHAR2(1000),
    feedback_date  DATE           DEFAULT SYSDATE NOT NULL
);

-- ---------- Indexes (FK columns + common filters) ----------
CREATE INDEX idx_student_room     ON student(room_id);
CREATE INDEX idx_cmp_student      ON complaint(student_id);
CREATE INDEX idx_cmp_category     ON complaint(category_id);
CREATE INDEX idx_cmp_status_prio  ON complaint(status, priority);
CREATE INDEX idx_photo_cmp        ON complaint_photo(complaint_id);
CREATE INDEX idx_asg_cmp          ON complaint_assignment(complaint_id);
CREATE INDEX idx_asg_staff        ON complaint_assignment(staff_id);
CREATE INDEX idx_cstatus_cmp      ON complaint_status(complaint_id);

-- Only ONE open (not yet completed) assignment per complaint
CREATE UNIQUE INDEX uq_asg_one_open
    ON complaint_assignment (CASE WHEN completed_date IS NULL THEN complaint_id END);

-- ---------- Views (for the Django/ODBC layer and the admin dashboard) ----------
CREATE OR REPLACE VIEW v_complaint_details AS
SELECT c.complaint_id, c.title, c.description, c.priority, c.status,
       c.created_date, c.resolved_date, c.resolution_remark,
       cat.category_id, cat.category_name,
       s.student_id, s.name AS student_name,
       r.block, r.room_number,
       st.staff_id, st.name AS staff_name, a.assigned_date,
       (SELECT COUNT(*) FROM complaint_photo p
         WHERE p.complaint_id = c.complaint_id) AS photo_count
FROM   complaint c
JOIN   student  s   ON s.student_id  = c.student_id
JOIN   room     r   ON r.room_id     = s.room_id
JOIN   category cat ON cat.category_id = c.category_id
LEFT JOIN complaint_assignment a
       ON a.complaint_id = c.complaint_id
      AND a.assignment_id = (SELECT MAX(x.assignment_id)
                               FROM complaint_assignment x
                              WHERE x.complaint_id = c.complaint_id)
LEFT JOIN staff st ON st.staff_id = a.staff_id;

CREATE OR REPLACE VIEW v_dashboard_summary AS
SELECT cat.category_name, c.status, COUNT(*) AS complaint_count
FROM   complaint c
JOIN   category cat ON cat.category_id = c.category_id
GROUP  BY cat.category_name, c.status;

PROMPT === DDL complete ===

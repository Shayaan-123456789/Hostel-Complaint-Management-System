-- =====================================================================
-- 04_test_data.sql : sample data + end-to-end test of the whole workflow
-- =====================================================================
SET ECHO ON
SET DEFINE OFF
SET SERVEROUTPUT ON SIZE UNLIMITED

INSERT INTO room (room_number, block, capacity, room_type) VALUES ('101', 'A', 2, 'DOUBLE');
INSERT INTO room (room_number, block, capacity, room_type) VALUES ('102', 'A', 3, 'TRIPLE');
INSERT INTO room (room_number, block, capacity, room_type) VALUES ('201', 'B', 2, 'DOUBLE');

INSERT INTO category (category_name, description) VALUES ('Electrical', 'Fans, lights, sockets, wiring');
INSERT INTO category (category_name, description) VALUES ('Plumbing',   'Taps, leaks, drainage, water supply');
INSERT INTO category (category_name, description) VALUES ('Furniture',  'Beds, tables, chairs, cupboards');
INSERT INTO category (category_name, description) VALUES ('Cleaning',   'Rooms, corridors, washrooms');
INSERT INTO category (category_name, description) VALUES ('Internet',   'Wi-Fi and LAN issues');

INSERT INTO staff (name, email, password, department, phone)
VALUES ('Ravi Electrician', 'ravi@hostel.edu', 'hashed_pw', 'Electrical', '9000000001');
INSERT INTO staff (name, email, password, department, phone)
VALUES ('Mani Plumber', 'mani@hostel.edu', 'hashed_pw', 'Plumbing', '9000000002');
COMMIT;

DECLARE
    v_room_a  room.room_id%TYPE;
    v_room_b  room.room_id%TYPE;
    v_s1 NUMBER; v_s2 NUMBER;
    v_c1 NUMBER; v_c2 NUMBER; v_c3 NUMBER;
    v_elec category.category_id%TYPE;
    v_plmb category.category_id%TYPE;
    v_ravi staff.staff_id%TYPE;
    v_mani staff.staff_id%TYPE;
BEGIN
    SELECT room_id INTO v_room_a FROM room WHERE block = 'A' AND room_number = '101';
    SELECT room_id INTO v_room_b FROM room WHERE block = 'B' AND room_number = '201';
    SELECT category_id INTO v_elec FROM category WHERE category_name = 'Electrical';
    SELECT category_id INTO v_plmb FROM category WHERE category_name = 'Plumbing';
    SELECT staff_id INTO v_ravi FROM staff WHERE email = 'ravi@hostel.edu';
    SELECT staff_id INTO v_mani FROM staff WHERE email = 'mani@hostel.edu';

    sp_register_student('Arun Kumar', 'arun@hostel.edu', 'hashed_pw', '9876543210', v_room_a, v_s1);
    sp_register_student('Bala Singh', 'bala@hostel.edu', 'hashed_pw', '9876543211', v_room_b, v_s2);

    sp_submit_complaint(v_s1, v_elec, 'Ceiling fan not working', 'Fan stopped in room 101.',
                        'HIGH', 'media/complaints/fan_101.jpg', v_c1);
    sp_submit_complaint(v_s2, v_plmb, 'Tap leaking', 'Bathroom tap leaks all night.',
                        'MEDIUM', NULL, v_c2);
    sp_submit_complaint(v_s1, v_elec, 'Socket sparking', 'Socket near bed sparks.',
                        'URGENT', 'media/complaints/socket_101.jpg', v_c3);

    -- full lifecycle for complaint 1
    sp_assign_complaint(v_c1, v_ravi, 'admin_warden');
    sp_update_status(v_c1, 'IN_PROGRESS', NULL, 'Ravi Electrician');
    sp_update_status(v_c1, 'RESOLVED', 'Capacitor replaced.', 'Ravi Electrician');
    sp_submit_feedback(v_c1, v_s1, 5, 'Fixed quickly.');

    -- complaint 2 only assigned
    sp_assign_complaint(v_c2, v_mani, 'admin_warden');
    COMMIT;
END;
/

PROMPT --- Open complaints (cursor) ---
EXEC sp_list_complaints_by_status('OPEN');

PROMPT --- History of first complaint ---
EXEC sp_complaint_history(1001);

PROMPT --- Category summary ---
EXEC sp_category_summary;

PROMPT --- Staff workload (nested cursors) ---
EXEC sp_staff_workload;

PROMPT --- Escalate (0 days so the demo rows qualify) ---
EXEC sp_escalate_overdue(0);
-- Procedure does not COMMIT: the caller decides when its transaction ends.
COMMIT;

PROMPT --- REF CURSOR search: block A, any status ---
VARIABLE rc REFCURSOR
EXEC sp_search_complaints(p_block => 'A', p_result => :rc);
PRINT rc

PROMPT --- Integrity/error-path checks run in 05_integrity_tests.sql ---

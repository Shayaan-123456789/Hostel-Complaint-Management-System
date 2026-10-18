-- =====================================================================
-- 00_drop_all.sql : clean re-run helper (errors on first run are harmless)
-- =====================================================================
WHENEVER SQLERROR CONTINUE
SET ECHO ON

DROP VIEW v_dashboard_summary;
DROP VIEW v_complaint_details;

DROP TABLE complaint_feedback   CASCADE CONSTRAINTS PURGE;
DROP TABLE complaint_status     CASCADE CONSTRAINTS PURGE;
DROP TABLE complaint_assignment CASCADE CONSTRAINTS PURGE;
DROP TABLE complaint_photo      CASCADE CONSTRAINTS PURGE;
DROP TABLE complaint            CASCADE CONSTRAINTS PURGE;
DROP TABLE staff                CASCADE CONSTRAINTS PURGE;
DROP TABLE category             CASCADE CONSTRAINTS PURGE;
DROP TABLE student              CASCADE CONSTRAINTS PURGE;
DROP TABLE room                 CASCADE CONSTRAINTS PURGE;

DROP SEQUENCE seq_room;
DROP SEQUENCE seq_student;
DROP SEQUENCE seq_category;
DROP SEQUENCE seq_staff;
DROP SEQUENCE seq_complaint;
DROP SEQUENCE seq_photo;
DROP SEQUENCE seq_assignment;
DROP SEQUENCE seq_status;
DROP SEQUENCE seq_feedback;

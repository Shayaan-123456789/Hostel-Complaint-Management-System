# Smart Hostel — Student / staff HTTP 500 role fix

## Failure identified on October 18, 2026

An authenticated student (ID 5) received HTTP 500 in Overview and Complaints.
The Django stack trace confirmed `KeyError: 'role'` in `views.complaints`
and `views.complaint_summary`. The Oracle read-only queries and all 22 ODBC
checks were passing, so this was not a database problem.

## Root cause

`hostel/security.py:authenticate()` returned `{id, name, email}` for STUDENT
and STAFF, whereas the WARDEN path returned `{role, id, name, email}`.
The decorator and views rely on `actor['role']` for access restrictions.
Existing tests mocked `authenticate()` using dictionaries that already
contained a role, so the defect was masked. `verify_login()` was unaffected,
which is why sign-in succeeded.

## Fix

Insert `actor['role'] = role` after reading and validating the student/staff
account and removing password/status fields in `authenticate()`. The role is
taken from the cryptographically verified JWT, NOT user input or a database
column. No changes to Oracle tables, stored procedures, triggers or files.

`tests/test_actor_role_regression.py` adds six tests that use the real
`authenticate()` function and mock only Oracle queries and JWT decoding.

## Install into existing working Django backend

1. Stop the Django development server with Ctrl+C.
2. Back up `hostel/security.py`.
3. Extract this patch in the folder that contains `manage.py`, preserving
   the `hostel/` and `tests/` subfolders. Overwrite `hostel/security.py`.
4. Keep your `.env`, `.venv`, Oracle schema and SQL scripts untouched.
5. Run:

   ```powershell
   python manage.py check
   python manage.py test tests
   python manage.py check_student_queries --student-id 5
   python manage.py check_oracle
   python manage.py runserver
   ```
6. Hard refresh the browser with Ctrl+Shift+R and log back in as the test
   student. Overview and Complaints should now load (the student can have
   zero complaints, which is a valid empty state).
7. After both pages work, test creating a complaint with a real JPEG/PNG
   under 5 MB and then viewing the uploaded image from the detail screen.

## Verification

- Static Python syntax compilation passed.
- Real Django test suite and live Oracle integration still require execution
  in the user's Windows environment.
- SQL schema and application secrets were not modified.

## If HTTP 500 remains

Capture the NEW Django traceback from the terminal. It may indicate another
issue. Do not recreate the database, and do not share tokens or passwords.

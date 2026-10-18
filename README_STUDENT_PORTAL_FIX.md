# Smart Hostel student portal: HTTP 500 diagnostic and fix

## Scope

The warden dashboard, student login and account panel worked; the student Overview and Complaints pages showed `Internal server error`. Both failing pages depend on student-scoped Oracle queries. The previous code passed IDs returned by Oracle ODBC into later query bind parameters without normalizing them; Oracle `NUMBER` can arrive as `decimal.Decimal`, which may be incompatible with binding on some driver versions.

The changes in this patch normalize authenticated STUDENT and STAFF primary keys to Python `int` and defensively normalize integral `Decimal` ODBC input binds. This fixes the **suspected** cause, not a confirmed production traceback. The new read-only diagnostic command will isolate the exact failing query should a 500 continue.

## Installation on Windows

1. Stop Django with Ctrl+C.
2. Back up the existing files `hostel\security.py` and `hostel\database.py` from your project.
3. Extract `Smart_Hostel_Student_Portal_Fix.zip` **into the project folder containing `manage.py`**, allowing replacement of matching files. The ZIP includes only these backend files, a new management command, a regression test and this README.
4. **Do not replace `.env`, run migrations, rerun `run_all.sql`, or run test data scripts.**
5. With your existing `.venv` activated:

   ```powershell
   python manage.py check
   python manage.py test tests
   python manage.py check_student_queries --student-id 5
   python manage.py check_oracle
   python manage.py runserver
   ```

The student ID 5 is taken from the user's screenshot. Replace it if the test account changed.

## Results to expect

The diagnostic command should print four PASS lines: student row, complaint view count, paginated complaint list, and overview summary. A student who has submitted no complaints should see empty-state screens, **not** HTTP 500.

If any check FAILS, share the four PASS/FAIL lines plus the final `CommandError` text, and the Django server's traceback for the first failing request. Do not share passwords, `.env`, JWTs, or SQL rows containing student details.

## Photo test after pages load

1. Sign in as student ID 5, then create a **new** complaint in Complaints and attach a small real JPG or PNG (under 5MB).
2. Open the new complaint and check that 1 attachment is listed. Add a second image using Add Photo if status is OPEN/ASSIGNED/IN_PROGRESS.
3. Sign out; sign in as warden; open that complaint and verify the photos display. This establishes both file storage and authenticated retrieval.
4. In SQL*Plus, read-only verification: `SELECT photo_id, photo_path FROM complaint_photo WHERE complaint_id = <new_id>;`. Older sample test rows may refer to placeholder paths without actual files.

## Changes and safety

- `hostel/security.py`: normalize Oracle IDs from `STUDENT`/`STAFF` authentication to `int`, reject non-integral/invalid IDs.
- `hostel/database.py`: convert integral `Decimal` values before ODBC bind execution.
- `hostel/management/commands/check_student_queries.py`: read-only diagnosis of four student queries, output counts/SQLSTATE codes only.
- `tests/test_student_id_bindings.py`: five regression tests for Oracle numeric IDs.

No Oracle table/view/procedure/trigger/sequence definition or SQL setup script has changed; frontend JS/CSS and login configuration are preserved. This package has passed Python syntax compilation, standalone tests of the conversion logic, and JS syntax verification. Live Oracle and full Django tests must be run on Windows; they were not available in this environment.

# Staff assignment department filtering fix

Applies to the **Smart_Hostel_Django_Student_Portal_Fixed_v4** project and its installed v4 equivalent.

## Why the plumber appeared for an Electrical complaint

The existing JavaScript assignment dropdown filtered only for `status === 'ACTIVE'`. The assignment API called `sp_assign_complaint` without checking the technician's department.

## Changes

- Frontend: only **ACTIVE** maintenance staff whose `department` matches the selected complaint's `category_name` (case-insensitive with whitespace trimmed) appear in Assign Staff.
- If there is no eligible technician, the user sees a clear message instead of an empty dropdown.
- API: checks `category.category_name`, `staff.department` and `staff.status` before calling the existing Oracle `sp_assign_complaint`. A forged direct API request naming a plumber for an Electrical complaint is rejected with HTTP 400.
- Tests: updates the existing positive assignment unit test and adds four tests for matching, mismatch, inactive and missing staff.
- **No Oracle tables, procedures, triggers, sequences or views have been modified.**

The API check protects normal Django calls but is **not an Oracle-level constraint**: a separate direct SQL client calling the stored procedure could still assign across departments. If database-level enforcement is later required, the Oracle procedure or trigger needs a separately reviewed migration.

## Installation (Windows PowerShell)

1. Stop `python manage.py runserver` with `Ctrl+C`.
2. Back up your current `hostel/views.py`, `hostel/static/hostel/app.js`, and `tests/test_api.py`.
3. From the Django folder (containing `manage.py`):

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\Smart_Hostel_Staff_Department_Assignment_Fix.zip" -DestinationPath . -Force
python manage.py check
python manage.py test tests
python manage.py check_oracle
python manage.py runserver
```

No `migrate`, `run_all.sql`, or reinstallation of the Oracle schema is needed.

## Ravi login

`ravi@hostel.edu` is the login email. The sample SQL created the account with `hashed_pw`, which is not a Django password hash. Log in as warden -> **Maintenance Team** -> Ravi -> **Reset password**, enter a new strong password, then use the Maintenance role to sign in. To discover his actual staff ID:

```sql
SELECT staff_id, name, email, department, status
FROM staff WHERE email IN ('ravi@hostel.edu', 'mani@hostel.edu');
```

## Acceptance check

- Sign in as warden and open complaint #1005 (Electrical, OPEN).
- Select **Assign Staff**; Ravi Electrician should appear if ACTIVE, Mani Plumber should not.
- Assign Ravi, confirm `ASSIGNED` status and a new `COMPLAINT_ASSIGNMENT` row.
- Sign out and sign in as Ravi with the password you set, then continue the maintenance workflow.

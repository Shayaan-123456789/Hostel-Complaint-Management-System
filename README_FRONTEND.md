# Smart Hostel frontend, integrated into Django

This checkpoint adds a responsive frontend to the **verified Oracle ODBC backend**. All application data comes from the existing Oracle database through Django. No new Oracle tables, indexes, sequences, procedures or triggers; no Django ORM migrations; no Node, npm, React or other frontend framework needed.

## 1. Safest installation on your existing Windows project

You already have a functioning `.env`, ODBC DSN `SmartHostelOracle`, schema `HOSTEL_OWNER`, and a working warden login. **Keep those files and database records. Do not run `run_all.sql` or `python manage.py migrate`.**

Use the **Smart_Hostel_Frontend_Patch.zip** supplied alongside the full project. Back up your existing project folder. Close the Django server with Ctrl+C. In PowerShell, adjust `$project` to your real path, then run:

```powershell
$project = 'C:\Users\PC\Downloads\Smart_Hostel_Django_ODBC_Diagnostics\Smart_Hostel_Django_Backend'
$patch = "$env:USERPROFILE\Downloads\Smart_Hostel_Frontend_Patch.zip"
Expand-Archive -Path $patch -DestinationPath $project -Force
Set-Location $project
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py test tests
python manage.py check_oracle
python manage.py runserver
```

If the virtual environment is already active, the `Activate.ps1` step can be skipped. There is no new pip package required beyond your working backend requirements.

**Open http://127.0.0.1:8000/** in your web browser. This is the new frontend page; the existing `/api/` endpoints continue to work.

A clean installation can instead use the complete `Smart_Hostel_Frontend_Django_Integrated.zip`, copy/create `.env` from the existing working project (never publish passwords), install `requirements.txt`, and start Django. Existing Oracle objects must already be installed. The full ZIP deliberately includes only `.env.example`, not your private `.env`.

## 2. Login and roles

| Role | Login identifier | How it is created | Frontend permissions |
|---|---|---|---|
| WARDEN | `warden` by default, defined by `HOSTEL_ADMIN_USERNAME` in `.env` | Generate the hash using `python scripts/generate_admin_hash.py` and place it in `.env` | Dashboard, all complaints, assignment, status changes and close, overdue escalation, staff, rooms, categories, students |
| STUDENT | Student email | Select **Student → Create an account**, choose an available room | Submit and view own complaints, photo uploads, resolution feedback, change password |
| STAFF | Maintenance staff email | Warden → Maintenance team → Add staff | Assigned complaints, progress and resolution updates, workload, change password |

The sample SQL accounts inserted with the literal password `hashed_pw` are **not** authenticatable. Create a real student and maintenance account via the web frontend, or set a proper Django password hash using your existing backend APIs. Do not store plain text passwords in Oracle.

## 3. Included pages and functions

**All roles:** Login, session restore via `/api/auth/me/`, sign out, role-appropriate navigation, complaint list and detail, status history, private photo viewing, account/profile page, password change for STUDENT and STAFF.

**WARDEN:** KPI dashboard with live Oracle counts, category workload visualization, complaint priority/status/category/block filters, assign active staff, move assigned work through permitted lifecycle, close resolved complaints, escalate overdue complaints, manage staff (create, edit, reset password), view students, create rooms and categories, inspect room occupancy.

**STUDENT:** New account registration with room availability, submit a complaint with optional photo, add another photo while complaint remains unresolved, see status timeline, assignments, resolution remarks, and submit a 1–5 rating and comments after resolution.

**STAFF:** Role-scoped active workload, assigned complaint list, status change from ASSIGNED to IN_PROGRESS, resolve an IN_PROGRESS complaint with required remarks, view historical work.

All status and permissions restrictions continue to be enforced by Django and the existing Oracle procedures/triggers. Hiding a control in the browser **does not** replace backend permissions.

## 4. Code changes

- `hostel/templates/hostel/index.html` — Django page, loads assets via `{% static %}`
- `hostel/static/hostel/app.css` — responsive theme, tables, forms, timeline and dialogs
- `hostel/static/hostel/app.js` — API client, role-aware pages, form handling, validation feedback, bearer token session
- `smart_hostel/settings.py` — enables Django `staticfiles` and a collectstatic destination
- `smart_hostel/urls.py` — mounts frontend at `/` and adds `/api/complaints/summary/`
- `hostel/views.py` — adds read-only authenticated `complaint_summary` endpoint (uses the original complaint and assignment tables; no migrations)
- `tests/test_frontend.py` — tests frontend root and verifies summary scope for student/staff/warden
- `scripts/frontend_smoke.cjs` — optional dependency-free JavaScript smoke test (only if Node.js is installed)

Existing Oracle DDL, triggers, stored procedures, app-user authentication, ODBC code and all original tests are retained.

## 5. Test commands

```powershell
python manage.py check
python manage.py test tests
python manage.py check_oracle
python manage.py runserver
```

Expected on a correctly installed backend: Django reports no system check issues; unit tests pass; `check_oracle` shows the same correct object access you already established. If Node.js is installed, run:

```powershell
node --check hostel\static\hostel\app.js
node scripts\frontend_smoke.cjs
```

The Node smoke test uses mocked API responses; it does **not** add complaints or staff to Oracle. Perform one real UI test by signing in as the already working warden and opening **Complaints**, **Maintenance team**, and **Rooms**. Then register a fresh student and submit a low-priority test complaint with no photo, assign active staff, resolve and collect feedback. Check the record in SQL*Plus. Do this on a development database.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| Browser root page returns 404 | Confirm `smart_hostel/urls.py` was replaced and Django was restarted |
| CSS/JavaScript 404 | Confirm `django.contrib.staticfiles` is in `INSTALLED_APPS`; `DEBUG=1` for local testing; assets under `hostel/static/hostel/` |
| API shows connection issue | `python manage.py check_oracle`; verify the working `.env` has not been replaced |
| Warden login fails | `.env` must include `HOSTEL_ADMIN_USERNAME` and a valid `HOSTEL_ADMIN_PASSWORD_HASH`; restart Django |
| Student/staff login fails | SQL demo `hashed_pw` is not a valid password hash; create accounts via the API/frontend |
| `403` on a button | Role or active assignment is not authorized; check status lifecycle and login identity |
| `400` on status update | Only permitted transitions are valid; resolving needs a nonempty `resolution_remark` |
| Photo missing | Photos uploaded through the old SQL demo are *paths only* and may not exist in `private_media`; new Django uploads are stored privately |
| Tests fail on existing project | Apply the full frontend patch including `views.py`, `urls.py`, and `settings.py`; test against the updated files |

## 7. Deployment limitations

This is a development-ready frontend, **not an audited production deployment**. It has been checked with syntax/static checks and mocked JavaScript runtime tests. Live browser interaction with the user's Windows Oracle instance cannot be tested in this execution environment. Production setup should use HTTPS, `DJANGO_DEBUG=0`, secure host configuration, `python manage.py collectstatic`, a production static-file server, proper user/warden credential management, rate limiting, and persistent private-media backup. The JWT bearer token is stored in browser **sessionStorage** and cleared on sign-out or tab session end; users should sign out on shared computers. No secret `.env` is included in either ZIP.

## 8. Handover checkpoint

- Database: Oracle 21c XE `XEPDB1`; nine original Smart Hostel tables, nine sequences, two views, thirteen procedures, fifteen triggers (user reported VALID).
- Backend: Django/pyodbc; `HOSTEL_OWNER` schema; user reported `check_oracle` success (22 pass, 0 fail) and warden login success.
- Frontend: Django-hosted HTML/CSS/vanilla JS; no Node build; same-origin fetch, no CORS configuration needed locally.
- New endpoint: `/api/complaints/summary/` supplies accurate status counts for the authenticated role, using `EXISTS` for STAFF to avoid duplicate assignments.
- Verified here: Python source AST/syntax, frontend JavaScript syntax, Node mock runtime smoke. Django/Oracle live integration and browser UI acceptance remain to be run on Windows.
- Next: Execute the four validation commands above, then sign in at `/`, test end-to-end student/staff/warden lifecycle, save error logs if any, and harden for deployment.

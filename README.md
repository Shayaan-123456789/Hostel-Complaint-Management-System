# Smart Hostel Complaint Management System — Django Backend

A working **Django project scaffold and REST-style API implementation** mapped to the *fixed nine-table Oracle schema* in `oracle_sql/`. The interface uses **Python ODBC (`pyodbc`)**, in keeping with the submitted project PDF. No Django ORM models, migrations, `auth_user` table, or additional Oracle tables are required.

> **Verification status:** Python syntax and dependency-independent static checks have been run. Django/pyodbc could not be installed in the authoring environment, and no Oracle instance was available; full Django tests and Oracle compilation/integration tests must be run on your machine. Do not treat the sample SQL data or this scaffold as a production security audit.

## 1. Roles and implementation

| Role | Where stored | Capabilities |
|---|---|---|
| `STUDENT` | `STUDENT` Oracle table | Register, log in, list own complaints, submit complaints with optional photo, upload more photos, track status/history, view resolution, submit rating/feedback after resolution, change password |
| `STAFF` | `STAFF` Oracle table | Log in, list own assigned complaints, see details/photos, move assigned complaints to `IN_PROGRESS` then `RESOLVED` with a remark, see workload, change password |
| `WARDEN`/`ADMIN` | `.env` admin username and password **hash** | Log in, search/filter every complaint, assign active staff, update/close complaints, inspect photos/status history, dashboard summaries, create rooms/categories/staff, manage staff, list students, escalate overdue priority |

**Why `.env` for the warden?** The conceptual schema defines only `STUDENT` and `STAFF` login tables; adding an admin table would violate the fixed schema. This approach supports **one configured warden/admin**. Multiple dynamically managed wardens would need a different schema or an external identity provider and are not provided here.

Authentication uses PBKDF2 hashes produced by Django's `make_password()` and signed, expiring JWTs sent as `Authorization: Bearer <token>`. Each request re-reads the student's/staff member's active status and password-hash fingerprint so deactivation and password changes invalidate tokens. Routes also verify complaint ownership or assignment. The Oracle database account is an *application service account*, not the end-user identity.

## 2. Requirements and installation (Windows)

**Prerequisites:** Python 3.11+ (use a version supported by Django 5.2), Oracle Database already set up, SQL*Plus or SQLcl, Oracle Instant Client **ODBC** driver matching Python's 64-bit architecture, and a functioning Oracle DSN. The Oracle ODBC driver must be registered with the 64-bit ODBC Data Source Administrator.

1. In your **development-only** Oracle schema, install/review the SQL scripts in `oracle_sql/`. `run_all.sql` **deletes and recreates all project tables and data**. Do not run it on a populated database; see the SQL-fixes README from the prior ZIP before upgrading existing data.
2. Check for SQL compilation errors in SQL*Plus:

   ```sql
   SELECT object_name, object_type, status FROM user_objects WHERE status = 'INVALID';
   SELECT name, type, line, position, text FROM user_errors ORDER BY name, sequence;
   ```

3. Create a 64-bit ODBC DSN called **SmartHostelOracle** in Windows > ODBC Data Sources (64-bit). Choose the installed Oracle ODBC driver and enter the Oracle server/service details. Test the connection. Use a schema with access to these tables, views, sequences and stored procedures. The simplest project/demo setup is using the same Oracle schema that ran the SQL files; for deployment create a narrower-permission application user and review required grants.
4. In the backend folder, run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

5. Edit `.env` with the **real DSN**, database username/password, two **different random secret keys**, CORS origins and admin username. Generate secrets with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

   Use that command twice and set `DJANGO_SECRET_KEY` and `HOSTEL_JWT_SECRET`. Do not use the sample placeholder secrets in a deployed system.
6. Generate the warden's secure password hash:

   ```powershell
   python scripts/generate_admin_hash.py
   ```

   Paste the generated hash as `HOSTEL_ADMIN_PASSWORD_HASH` in `.env` (no surrounding quotes required); never put the actual password in `.env` as the admin hash.
7. Start Django:

   ```powershell
   python manage.py check
   python manage.py test tests
   python manage.py runserver 127.0.0.1:8000
   ```

   Test `http://127.0.0.1:8000/api/health/` and confirm `{"status":"ok","oracle":"connected"}`. If it returns HTTP 503, fix the DSN/driver/Oracle listener/user credentials.

**Do not run `python manage.py migrate`.** Django's database backend is intentionally disabled; application data lives only in the original nine Oracle tables and is accessed through ODBC. Likewise, Django's standard `/admin/` is not enabled; the warden uses the provided JSON endpoints.

## 3. How to add real users

The sample Oracle fixture in `04_test_data.sql` uses the literal fake password string `hashed_pw`. **Those demo student/staff accounts cannot log in using the Django authentication endpoint.** Register a real student via `POST /api/auth/register/` or create a staff account using the authenticated warden endpoint `POST /api/admin/staff/create/`. Those endpoints generate real password hashes automatically.

The registration endpoint currently permits public student self-registration into rooms with remaining capacity. For a campus production deployment, restrict registration to verified institutional identities or make it invitation-only.

## 4. Main API routes

All endpoints begin with `http://127.0.0.1:8000`. All JSON POST/PATCH requests use `Content-Type: application/json`; multipart photo uploads use `multipart/form-data`. Unless specified public, pass `Authorization: Bearer ACCESS_TOKEN`.

| Method | Route | Allowed role | Purpose |
|---|---|---|---|
| GET | `/api/health/` | Public | Check Oracle connectivity |
| GET | `/api/rooms/` | Public | Rooms with capacity/available places |
| GET | `/api/categories/` | Public | Complaint categories |
| POST | `/api/auth/register/` | Public | Register student; respects room capacity |
| POST | `/api/auth/login/` | Public | Obtain role-bound bearer token |
| GET | `/api/auth/me/` | All logged in | Current account/role |
| POST | `/api/auth/password/` | Student/Staff | Change password |
| GET | `/api/complaints/` | All logged in | Student: own; staff: assigned; warden: all; filters/pagination |
| POST | `/api/complaints/` | Student | Submit complaint; optional photo |
| GET | `/api/complaints/{id}/` | Authorized viewer | Complaint details, history, photos, assignments, feedback |
| POST | `/api/complaints/{id}/photos/` | Complaint owner | Add photo before resolution |
| GET | `/api/complaints/{id}/photos/{photo_id}/` | Authorized viewer | Private image download |
| POST | `/api/complaints/{id}/assign/` | Warden | Assign active staff |
| POST | `/api/complaints/{id}/status/` | Assigned staff/Warden | Update complaint lifecycle |
| POST | `/api/complaints/{id}/feedback/` | Complaint owner | One rating/feedback after resolution |
| GET | `/api/admin/dashboard/` | Warden | Status/category/rating summaries |
| POST | `/api/admin/rooms/` | Warden | Create room |
| POST | `/api/admin/categories/` | Warden | Create category |
| GET | `/api/admin/staff/` | Warden | Staff directory and workload |
| POST | `/api/admin/staff/create/` | Warden | Create staff account |
| PATCH | `/api/admin/staff/{id}/` | Warden | Update staff details/active status |
| POST | `/api/admin/staff/{id}/reset-password/` | Warden | Reset staff password |
| GET | `/api/admin/students/` | Warden | Student directory |
| POST | `/api/admin/escalate/` | Warden | Escalate old complaint priorities |
| GET | `/api/staff/workload/` | Staff/Warden | Personal/team pending assignment workload |

`GET /api/complaints/` supports `status`, `priority`, `category` (category name), `block`, `limit` (1–100) and `offset`. Results are constrained to the role, regardless of filters.

## 5. Sample request bodies

### Register a student

`POST /api/auth/register/`

```json
{"name":"Sara","email":"sara@example.edu","password":"ExamplePass123","phone":"9876543210","room_id":1}
```

### Log in

`POST /api/auth/login/`:

```json
{"role":"STUDENT","email":"sara@example.edu","password":"ExamplePass123"}
```

For maintenance staff, use `"role":"STAFF"` and a staff email/password created by the warden. For warden/admin:

```json
{"role":"WARDEN","username":"warden","password":"your-warden-password"}
```

### Submit a complaint

`POST /api/complaints/`:

```json
{"category_id":1,"title":"Fan not working","description":"Ceiling fan stopped running in my room.","priority":"HIGH"}
```

To submit an optional image with this request, send **multipart/form-data** fields (`category_id`, `title`, `description`, `priority`) and an upload field named `photo`. The file is saved under `private_media/complaints/`; Oracle only stores its relative path. Images are not exposed by a public `/media/` URL.

### Assign / start work / resolve / close

```text
POST /api/complaints/1001/assign/       {"staff_id": 2}                       WARDEN
POST /api/complaints/1001/status/       {"status": "IN_PROGRESS"}            assigned STAFF/WARDEN
POST /api/complaints/1001/status/       {"status": "RESOLVED", "resolution_remark": "Capacitor replaced."} assigned STAFF/WARDEN
POST /api/complaints/1001/status/       {"status": "CLOSED"}                  WARDEN
POST /api/complaints/1001/feedback/     {"rating": 5, "comments": "Fixed"} STUDENT owner
```

The final Oracle procedure and triggers control legal status transitions, complete assignments and append status history in the same Oracle transaction.

## 6. Database integration details

The app calls these existing stored procedures via parameterized ODBC anonymous PL/SQL blocks:

- `sp_register_student` and `sp_submit_complaint` use local PL/SQL OUT variables followed by `seq_student.CURRVAL` and `seq_complaint.CURRVAL` on the **same ODBC connection** to retrieve generated IDs.
- `sp_add_photo`, `sp_assign_complaint`, `sp_update_status`, `sp_submit_feedback`, and `sp_escalate_overdue` are invoked as stored procedures.
- Application listing/search uses the PDF-compatible `v_complaint_details` and `v_dashboard_summary` views with prepared SQL parameters and role filters. The reporting `SYS_REFCURSOR` procedures remain available for SQL*Plus demonstrations, but direct ODBC fetching of Oracle-specific output cursor variables is deliberately avoided.
- All writes are committed by the Django request transaction manager. Errors trigger rollbacks. Image files created before a transaction failure are cleaned up when possible.

The ODBC application account must be able to read the relevant tables/views, use the relevant sequences, execute the project procedures and perform warden-authorized room/category/staff changes and password updates. Grant no more permissions than necessary for the deployment. **End-user role checks happen in Django**, since the existing SQL procedures accept actor IDs/strings and do not by themselves authenticate students or staff.

## 7. Test plan

First run `python manage.py test tests` (mocked, no database). Then, with a disposable Oracle database and running server, perform this live workflow:

1. Register student in a room; log in and check `/api/auth/me/`.
2. Create staff account as warden; log in as staff.
3. Submit complaint, optionally with a real image; confirm unique ID and initial `OPEN` history.
4. Student sees only own complaint; different student receives HTTP 404 on its details.
5. Warden assigns the complaint; staff sees it and progresses through `IN_PROGRESS` and `RESOLVED` with a remark.
6. Student submits one 1–5 rating; second feedback is rejected.
7. Warden closes; attempts to update/close again fail.
8. Validate search filters, room capacity, private photo permissions, staff workload, and dashboard counts.
9. Run the SQL verification script `oracle_sql/06_verify_objects.sql` in SQL*Plus.
10. Test two simultaneous registrations to the last place in a room, invalid status transitions, and failed DB writes to confirm rollback/cleanup behavior.

### Limitations and production considerations

- No Oracle/Django runtime integration was performed in the authoring environment; test the particular Oracle ODBC driver, its parameter binding behavior and SQL scripts before use.
- JWT access tokens expire after the configured hours. There is no token-denylist/logout server state because no session tables are permitted; clients should discard tokens on logout. Password changes/deactivation invalidate relevant tokens. No refresh-token endpoint is provided.
- Enable HTTPS, origin allowlisting, login throttling/rate limiting at the ingress, secure secret handling, auditing/monitoring, private backups and anti-malware/PII policies before campus deployment.
- Multiple admins, staff reassignments, complaint reopening and advanced identity-provider integrations are not in the fixed schema/workflow.
- The PDF describes Django plus ODBC; this code uses ODBC rather than Django's Oracle ORM precisely to avoid extra schema/migration tables.

---

## Oracle/ODBC connectivity and permission verification (Windows)

These steps are **non-destructive** and work with the original nine tables. You do
not need to run `run_all.sql` to test the connection. That script drops data.

### Step 1. Install the prerequisites

Use **64-bit Python** and install a **64-bit Oracle ODBC driver** with its
compatible Oracle Client/Instant Client installation. For Oracle Instant Client,
follow Oracle's ODBC installation steps; installing `pyodbc` alone does not
install the Oracle ODBC driver.

Open **64-bit ODBC Data Source Administrator**:

```powershell
C:\Windows\System32\odbcad32.exe
```

Create or check an Oracle **System DSN** (for a service) or **User DSN** (for
interactive development), for example `SmartHostelOracle`. In the DSN, enter
the hostname, port (often `1521`), and your actual Oracle **service name**
(not necessarily the SID). Test the DSN with your Oracle account. Verify the
listener and PDB service are running as applicable to your setup.

### Step 2. Configure `.env`

In the folder containing `manage.py`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your own local values (never send your password):

```dotenv
ORACLE_ODBC_DSN=SmartHostelOracle
ORACLE_DB_USER=YOUR_ORACLE_USERNAME
ORACLE_DB_PASSWORD=YOUR_ORACLE_PASSWORD
# Leave empty if the login owns the nine project tables.
ORACLE_SCHEMA_OWNER=
```

**Owner matters:** The installed SQL uses unqualified table, view, sequence,
and procedure names. If your login owns the project objects, leave
`ORACLE_SCHEMA_OWNER` empty and use that login. If another Oracle user owns the
objects, set `ORACLE_SCHEMA_OWNER` to its unquoted schema name (typically
uppercase), and have the owner directly grant the required privileges to your
app login. `ALTER SESSION SET CURRENT_SCHEMA` changes name resolution only;
it does **not** grant database access. See `oracle_sql/08_example_direct_grants.sql`
for a restricted, owner-run example. It assumes the separate app login already
exists. Do not blindly use SYSTEM/SYS as application credentials.

For the API's independent warden login, generate a hash and configure the
additional values in `.env` as explained above in the authentication section.
Use a long random `DJANGO_SECRET_KEY` and a different
`HOSTEL_JWT_SECRET`.

### Step 3. Perform the read-only preflight

```powershell
python -c "import struct; print('Python bitness:', struct.calcsize('P')*8)"
python -c "import pyodbc; print('Drivers:', pyodbc.drivers()); print('DSNs:', pyodbc.dataSources())"
python manage.py check
python manage.py check_oracle
```

`check_oracle` is **read-only**: it verifies DSN discovery, logs in using
`hostel.database._connect()`, inspects Oracle session/current schema identity,
checks nine tables, two views, nine sequences, 13 procedures and 15 triggers,
checks for invalid objects, runs zero-row SELECTs on tables/views, verifies
ODBC PL/SQL bind placeholders, and checks direct object grants if the login
user differs from the owner. It does not run INSERT/UPDATE/DELETE,
call business procedures, commit, or advance sequence `NEXTVAL`.

If the report says `FAIL`, fix that before proceeding to API tests. The
command exits with nonzero status on failures. It deliberately reports only
safe error codes and advice, not raw connection strings or credentials.

As an independent SQL*Plus/SQLcl permission report, connect using **the same
Oracle login as `.env`** and run:

```sql
@oracle_sql/07_read_only_permission_audit.sql
```

For the owner account, inspect any compilation problems with:

```sql
SELECT name, type, line, position, text FROM user_errors ORDER BY name, sequence;
```

### Step 4. Run Django and a real HTTP health check

```powershell
python manage.py test tests
python manage.py runserver 127.0.0.1:8000
```

In another PowerShell window:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health/
```

Expected response after the driver, Oracle listener, DSN and permissions are
configured:

```json
{"status":"ok","oracle":"connected"}
```

**Scope of verification:** That response confirms connectivity and the ability
to query `DUAL`, not all privileges or all workflows. The management preflight
checks read privileges and object metadata. A full end-to-end test of writes,
commits/rollbacks, room capacity concurrency, feedback, and status transitions
requires a dedicated disposable Oracle database and test users. Do not run
business-write tests against production data.

### Common errors and likely fixes

| Error | Where to look |
|---|---|
| IM002 | 64-bit DSN name differs from `.env`, or driver not installed/visible |
| IM003 / IM014 | Client driver installation or Python/driver bitness mismatch |
| ORA-12154 | Oracle Net alias/TNS_ADMIN/DSN configuration |
| ORA-12514 / ORA-12505 | Wrong service name/SID; Oracle listener or PDB service |
| ORA-12541 | Listener stopped or wrong host/port |
| ORA-01017 | Oracle username/password/service mismatch |
| ORA-01045 | DBA must grant CREATE SESSION to the login |
| ORA-01031 | Insufficient object grants; owner should grant only what the app needs |
| ORA-00942 | Missing table/view or incorrect schema/grant; check CURRENT_SCHEMA |
| ORA-02289 | Missing sequence or SELECT privilege for CURRVAL |
| ORA-04098 / ORA-06508 | Invalid trigger/procedure; check schema-owner USER_ERRORS |
| ORA-06550 | PL/SQL binding mismatch, missing EXECUTE, or other compiler errors |

If something fails, share the redacted `[FAIL]` diagnostic lines and Oracle
version/service name. Do not share `.env` passwords or secret keys.

For convenience, the entire preflight can also be run in PowerShell:

```powershell
.\scripts\connection_smoke.ps1
```

It stops at the first fatal installation or connection problem.

# Smart Hostel — Maintenance Department Dropdown + Assignment Fix (v5)

## Scope

This version **combines** the earlier Staff Department Assignment Fix with the maintenance account department dropdown. No Oracle schema, data, tables, views, triggers, stored procedures or sequences are changed.

### Maintenance account form

- **Add Staff** on both the Warden Overview and Maintenance Team pages loads the live category list from `GET /api/categories/` every time it opens. The `department` field is now a required dropdown; no manual text entry.
- **Edit Staff** uses the same dropdown and preselects the current department when it matches an existing category. If a legacy department is not an existing category, the user must select a valid category before saving the edit.
- The list follows existing Oracle categories (`Electrical`, `Plumbing`, `Furniture`, `Cleaning`, `Internet` in the initial sample). Adding a category in Categories will make it available the next time the dropdown opens.
- When no categories exist, the UI explains that the warden must create a category first.
- The Django staff-create and staff-edit API routes validate the department against `CATEGORY` and store its canonical name. The API rejects arbitrary free-text departments, even from non-browser clients.

### Included previous fix: Assignment filtering

- Warden **Assign Staff** shows only active staff whose department matches the complaint's category.
- Django checks the same eligibility server-side and rejects unmatched or inactive staff before calling `SP_ASSIGN_COMPLAINT`.
- An Electrical complaint will list Ravi Electrician if active, but **not** Mani Plumber (Plumbing).

**Limitation:** the assignment restriction is enforced by Django, not by Oracle. Users with direct SQL access to the stored procedure are not subject to the Django department check.

## Recommended installation: combined patch

1. Stop the Django development server (`Ctrl+C`).
2. From PowerShell, adjust `$project` if necessary:

```powershell
$project = "C:\Users\PC\Downloads\Smart_Hostel_Django_ODBC_Diagnostics\Smart_Hostel_Django_Backend"
Set-Location $project
Copy-Item .\hostel\views.py .\hostel\views_before_department_v5.py
Copy-Item .\hostel\static\hostel\app.js .\hostel\static\hostel\app_before_department_v5.js
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\Downloads\hostel_backup" | Out-Null
Copy-Item .\tests\test_api.py "$env:USERPROFILE\Downloads\hostel_backup\test_api_before_department_v5.py"
Expand-Archive -Path "$env:USERPROFILE\Downloads\Smart_Hostel_Staff_Department_Combined_v5_Patch.zip" -DestinationPath $project -Force
```

The `test_api.py` backup is stored outside the Django `tests` directory so Django will not discover it as an extra test module.

3. Use these commands:

```powershell
python manage.py check
python manage.py test tests
python manage.py check_oracle
python manage.py runserver
```

4. Refresh the browser with `Ctrl+Shift+R`. Sign in as warden, open **Maintenance Team > Add Staff**, and verify the `Department` field is a dropdown. Also test **Overview > Add Staff** and **Edit Staff**.

There is no need to run migrations or reinstall/recreate Oracle tables. Keep your existing `.env` unchanged.

## Regression tests

- `tests/test_api.py` (adjusted test for previous assignment validation)
- `tests/test_staff_category_assignment.py` (4 tests for matching and mismatching assignment)
- `tests/test_staff_departments.py` (6 tests for create/edit staff department validation and warden-only permissions)
- `scripts/frontend_smoke.cjs` (existing smoke test)
- `scripts/department_dropdown_smoke.cjs` (live-category dropdown smoke test, no Oracle connection)

For optional JavaScript smoke tests, install Node.js if not already present:

```powershell
node scripts/frontend_smoke.cjs
node scripts/department_dropdown_smoke.cjs
```

### Acceptance test

1. Login as warden. Navigate directly to **Overview > Add Staff** (without visiting Categories). See `Electrical`, `Plumbing`, `Furniture`, `Cleaning`, `Internet` (assuming those categories still exist).
2. Choose `Electrical` and create a **new** technician. Confirm staff appears with department `Electrical`.
3. Edit the new technician. Confirm the department dropdown has `Electrical` selected and can be changed to an existing category.
4. Select an **OPEN** Electrical complaint, such as #1005 if it is still OPEN. Choose **Assign Staff**. Electrical technicians should appear, Plumbing technicians should not.
5. Optionally test an invalid direct API department: it should return HTTP 400 with `Department must match an existing complaint category.`

**Database impact:** creating a technician in this acceptance test inserts a real `STAFF` row. The unit and smoke tests do not write to Oracle.

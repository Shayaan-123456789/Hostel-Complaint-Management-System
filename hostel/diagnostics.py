"""Read-only Oracle ODBC preflight for the fixed Smart Hostel schema.

All checks are performed against the same pyodbc connection used by the API.
This module does not print credentials or issue data-changing SQL.
"""
import os
import re
import struct
from dataclasses import dataclass

EXPECTED = {
    'TABLE': {
        'ROOM', 'STUDENT', 'CATEGORY', 'STAFF', 'COMPLAINT',
        'COMPLAINT_PHOTO', 'COMPLAINT_ASSIGNMENT', 'COMPLAINT_STATUS',
        'COMPLAINT_FEEDBACK',
    },
    'VIEW': {'V_COMPLAINT_DETAILS', 'V_DASHBOARD_SUMMARY'},
    'SEQUENCE': {
        'SEQ_ROOM', 'SEQ_STUDENT', 'SEQ_CATEGORY', 'SEQ_STAFF',
        'SEQ_COMPLAINT', 'SEQ_PHOTO', 'SEQ_ASSIGNMENT',
        'SEQ_STATUS', 'SEQ_FEEDBACK',
    },
    'PROCEDURE': {
        'SP_REGISTER_STUDENT', 'SP_SUBMIT_COMPLAINT', 'SP_ADD_PHOTO',
        'SP_ASSIGN_COMPLAINT', 'SP_UPDATE_STATUS', 'SP_SUBMIT_FEEDBACK',
        'SP_LIST_COMPLAINTS_BY_STATUS', 'SP_COMPLAINT_HISTORY',
        'SP_CATEGORY_SUMMARY', 'SP_STAFF_WORKLOAD',
        'SP_ESCALATE_OVERDUE', 'SP_SEARCH_COMPLAINTS',
        'SP_STUDENT_COMPLAINTS',
    },
    'TRIGGER': {
        'TRG_ROOM_BI', 'TRG_CATEGORY_BI', 'TRG_STAFF_BI',
        'TRG_PHOTO_BI', 'TRG_CSTATUS_BI', 'TRG_ROOM_BU_INTEGRITY',
        'TRG_STUDENT_BI_BU', 'TRG_COMPLAINT_BI_BU',
        'TRG_COMPLAINT_STATUS_LOG', 'TRG_COMPLAINT_BD',
        'TRG_ASSIGNMENT_BI', 'TRG_ASSIGNMENT_BU',
        'TRG_ASSIGNMENT_AI', 'TRG_FEEDBACK_BI',
        'TRG_CSTATUS_IMMUTABLE',
    },
}

# The Django app directly inserts/updates these tables in addition to
# invoking schema-owner procedures. Only check direct grants when the
# login user differs from the schema owner.
DIRECT_DML = {
    'ROOM': {'SELECT', 'INSERT'},
    'STUDENT': {'SELECT', 'UPDATE'},
    'CATEGORY': {'SELECT', 'INSERT'},
    'STAFF': {'SELECT', 'INSERT', 'UPDATE'},
    'COMPLAINT': {'SELECT'},
    'COMPLAINT_PHOTO': {'SELECT'},
    'COMPLAINT_ASSIGNMENT': {'SELECT'},
    'COMPLAINT_STATUS': {'SELECT'},
    'COMPLAINT_FEEDBACK': {'SELECT'},
    'V_COMPLAINT_DETAILS': {'SELECT'},
    'V_DASHBOARD_SUMMARY': {'SELECT'},
    'SEQ_ROOM': {'SELECT'},
    'SEQ_STUDENT': {'SELECT'},
    'SEQ_CATEGORY': {'SELECT'},
    'SEQ_STAFF': {'SELECT'},
    'SEQ_COMPLAINT': {'SELECT'},
}
COLUMN_UPDATES = {
    'STUDENT': {'PASSWORD'},
    'STAFF': {'NAME', 'DEPARTMENT', 'PHONE', 'STATUS', 'PASSWORD'},
}
REQUIRED_EXECUTE = {
    'SP_REGISTER_STUDENT', 'SP_SUBMIT_COMPLAINT', 'SP_ADD_PHOTO',
    'SP_ASSIGN_COMPLAINT', 'SP_UPDATE_STATUS', 'SP_SUBMIT_FEEDBACK',
    'SP_ESCALATE_OVERDUE',
}


def classify_exception(exc):
    """Return safe, actionable error code and explanation; no password output."""
    # db._connect()/db._raise_sql wrap the original pyodbc.Error in __cause__.
    underlying = getattr(exc, '__cause__', None) or exc
    message = str(underlying)
    oracle = re.search(r'ORA-(\d{5})', message)
    # Oracle's ODBC driver can wrap a specific driver-manager error (such as
    # IM002) in the generic HY000 state. Prefer the actionable error code.
    actionable = re.search(r'\b(IM002|IM003|IM014|08001)\b', message)
    state = re.search(r"(?:\[|\()([A-Z0-9]{5})(?:\]|\))", message)
    code = ('ORA-' + oracle.group(1) if oracle else
            actionable.group(1) if actionable else
            state.group(1) if state else 'UNKNOWN')
    explanations = {
        'IM002': 'ODBC DSN not found or no matching 64-bit Oracle ODBC driver. Create a 64-bit System/User DSN.',
        'IM003': 'ODBC driver cannot load. Install/configure the Oracle 64-bit ODBC driver.',
        'IM014': 'ODBC architecture mismatch. Use 64-bit Python with a 64-bit Oracle driver.',
        '08001': 'ODBC network/driver connection failure. Check DSN server, port, and Oracle service.',
        'ORA-01017': 'Invalid Oracle username/password or wrong service/database.',
        'ORA-01031': 'Insufficient privileges. Connect as object owner or grant the required object privileges.',
        'ORA-01045': 'Oracle account lacks CREATE SESSION permission.',
        'ORA-00942': 'Table/view is missing, not visible, or lacks SELECT; verify ORACLE_SCHEMA_OWNER and grants.',
        'ORA-02289': 'Sequence not found or missing SELECT grant.',
        'ORA-04043': 'Procedure/object not found in the selected schema.',
        'ORA-04098': 'A trigger is invalid and failed revalidation; check USER_ERRORS as schema owner.',
        'ORA-06550': 'PL/SQL parse/compile error or missing EXECUTE; inspect USER_ERRORS and procedure signatures.',
        'ORA-06508': 'Called PL/SQL unit is unavailable or invalid; check object status and grants.',
        'ORA-12154': 'Oracle Net service name cannot be resolved. Check DSN/TNS_ADMIN/tnsnames.ora.',
        'ORA-12514': 'Listener does not know this SERVICE_NAME. Check DSN service and PDB service.',
        'ORA-12541': 'Oracle listener not running or wrong host/port.',
        'ORA-12505': 'Listener does not know the configured SID. Prefer the correct SERVICE_NAME.',
        'ORA-28000': 'Oracle account locked; ask database administrator to unlock it.',
        'ORA-28001': 'Oracle account password expired; reset it in Oracle.',
        'ORA-28040': 'Oracle client/server authentication protocol mismatch; update the driver/client.',
    }
    return code, explanations.get(code, 'Inspect Oracle/ODBC configuration and SQL object permissions.')


@dataclass
class Finding:
    level: str
    name: str
    detail: str


class CheckReport:
    def __init__(self):
        self.findings = []

    def add(self, level, name, detail):
        self.findings.append(Finding(level, name, detail))

    @property
    def failed(self):
        return any(f.level == 'FAIL' for f in self.findings)


def inspect_connection(conn, report):
    """Queries never mutate rows or use NEXTVAL. Connection remains open."""
    from . import database as db

    try:
        who = db.one(conn, """SELECT SYS_CONTEXT('USERENV','SESSION_USER') session_user,
              SYS_CONTEXT('USERENV','CURRENT_SCHEMA') current_schema FROM dual""")
    except Exception as exc:
        code, advice = classify_exception(exc)
        report.add('FAIL', 'Oracle identity', f'{code}: {advice}')
        return
    user = str(who['session_user']).upper()
    owner = str(who['current_schema']).upper()
    report.add('PASS', 'Oracle connection', f'Authenticated as {user}; resolving objects in {owner}.')
    if user != owner:
        report.add('WARN', 'Separate Oracle users',
                   f'Logged in as {user}, but using {owner} objects. Direct object grants are required; ALTER SESSION does NOT grant privileges.')

    try:
        objects = db.all_rows(conn, '''SELECT object_name, object_type, status
                FROM all_objects WHERE owner = ? AND object_type IN
                ('TABLE','VIEW','SEQUENCE','PROCEDURE','TRIGGER')''', [owner])
        present = {(str(o['object_type']).upper(), str(o['object_name']).upper()): str(o['status']).upper() for o in objects}
        for kind, names in EXPECTED.items():
            missing = sorted(name for name in names if (kind, name) not in present)
            invalid = sorted(name for name in names if present.get((kind, name)) not in (None, 'VALID'))
            if missing:
                report.add('FAIL', f'{kind} objects', f'Missing/not visible in {owner}: {", ".join(missing)}')
            elif invalid:
                report.add('FAIL', f'{kind} objects', f'INVALID: {", ".join(invalid)}')
            else:
                report.add('PASS', f'{kind} objects', f'All {len(names)} expected objects are visible and valid.')
    except Exception as exc:
        code, advice = classify_exception(exc)
        report.add('FAIL', 'Oracle object inventory', f'{code}: {advice}')

    # No-op SELECT is still compiled by Oracle and verifies object accessibility.
    for name in sorted(EXPECTED['TABLE'] | EXPECTED['VIEW']):
        try:
            db.all_rows(conn, f'SELECT * FROM {name} WHERE 1=0')
        except Exception as exc:
            code, advice = classify_exception(exc)
            report.add('FAIL', f'SELECT {name}', f'{code}: {advice}')
        else:
            report.add('PASS', f'SELECT {name}', 'Query parsing and SELECT privilege succeeded.')

    # Tests PL/SQL anonymous block parameter binding through ODBC without
    # calling any business procedure or writing to a project table.
    try:
        db.run(conn, '''DECLARE v_test NUMBER; BEGIN v_test := ?;
                   IF v_test != 7 THEN RAISE_APPLICATION_ERROR(-20098, 'Binding mismatch'); END IF;
                   END;''', [7])
        report.add('PASS', 'ODBC PL/SQL binds', 'Anonymous PL/SQL block accepted a qmark bind parameter.')
    except Exception as exc:
        code, advice = classify_exception(exc)
        report.add('FAIL', 'ODBC PL/SQL binds', f'{code}: {advice}')

    # Grants are checked from the data dictionary; no INSERT/UPDATE/DELETE is
    # executed, so sequences and application rows remain unchanged.
    if user != owner:
        try:
            grants = db.all_rows(conn, '''SELECT table_name, privilege, grantee
                FROM all_tab_privs WHERE owner = ? AND grantee IN (?, 'PUBLIC')''', [owner, user])
            # UPDATE(column) grants live in ALL_COL_PRIVS, not ALL_TAB_PRIVS.
            # The example grant script grants only the columns Django updates.
            col_grants = db.all_rows(conn, '''SELECT table_name, column_name, privilege, grantee
                FROM all_col_privs WHERE owner = ? AND grantee IN (?, 'PUBLIC')''', [owner, user])
            by_name = {}
            for g in grants:
                by_name.setdefault(str(g['table_name']).upper(), set()).add(str(g['privilege']).upper())
            columns = {}
            for g in col_grants:
                if str(g['privilege']).upper() == 'UPDATE':
                    columns.setdefault(str(g['table_name']).upper(), set()).add(str(g['column_name']).upper())
            for name, wanted in DIRECT_DML.items():
                missing = wanted - by_name.get(name, set())
                if 'UPDATE' in missing:
                    missing_columns = COLUMN_UPDATES.get(name, set()) - columns.get(name, set())
                    if not missing_columns:
                        missing.remove('UPDATE')
                    else:
                        report.add('FAIL', f'Column grants {name}',
                                   f'Missing UPDATE on column(s): {", ".join(sorted(missing_columns))} for {user}.')
                        missing.remove('UPDATE')
                if missing:
                    report.add('FAIL', f'Direct grants {name}', f'Missing: {", ".join(sorted(missing))} for {user}.')
            for name in sorted(REQUIRED_EXECUTE):
                if 'EXECUTE' not in by_name.get(name, set()):
                    report.add('FAIL', f'EXECUTE {name}', f'No direct EXECUTE grant visible for {user}.')
            if not any(f.level == 'FAIL' and (f.name.startswith('Direct grants') or f.name.startswith('Column grants') or f.name.startswith('EXECUTE'))
                       for f in report.findings):
                report.add('PASS', 'Direct object grants', 'Required object privileges appear to be granted directly.')
        except Exception as exc:
            code, advice = classify_exception(exc)
            report.add('WARN', 'Direct privilege inventory', f'{code}: {advice}')
    else:
        report.add('PASS', 'Object ownership', 'Logged-in schema owns the project objects; separate grants are unnecessary.')


def environment_preflight(report):
    try:
        import pyodbc
    except ImportError:
        report.add('FAIL', 'pyodbc package', 'Install requirements.txt into your active Python environment.')
        return False
    report.add('PASS', 'Python architecture', f'{struct.calcsize("P") * 8}-bit Python process.')
    dsn = os.getenv('ORACLE_ODBC_DSN', '').strip()
    user = os.getenv('ORACLE_DB_USER', '').strip()
    password = os.getenv('ORACLE_DB_PASSWORD', '')
    if not dsn or not user or not password or password.startswith('REPLACE_'):
        report.add('FAIL', 'Oracle .env', 'Set ORACLE_ODBC_DSN, ORACLE_DB_USER, ORACLE_DB_PASSWORD in .env.')
        return False
    if not os.getenv('HOSTEL_ADMIN_USERNAME') or os.getenv('HOSTEL_ADMIN_PASSWORD_HASH', '').startswith('REPLACE_') or not os.getenv('HOSTEL_ADMIN_PASSWORD_HASH'):
        report.add('WARN', 'Warden login', 'Configure HOSTEL_ADMIN_USERNAME and HOSTEL_ADMIN_PASSWORD_HASH before testing warden authentication.')
    try:
        drivers = pyodbc.drivers()
        oracle_drivers = [driver for driver in drivers if 'oracle' in driver.lower()]
        if oracle_drivers:
            report.add('PASS', 'Oracle ODBC drivers', ', '.join(oracle_drivers))
        else:
            report.add('WARN', 'Oracle ODBC drivers', 'No driver with Oracle in its name; verify installed drivers.')
        sources = pyodbc.dataSources()
        found = next((name for name in sources if name.lower() == dsn.lower()), None)
        if found:
            report.add('PASS', 'ODBC DSN', f'{found} is registered with driver {sources[found]}.')
        else:
            report.add('WARN', 'ODBC DSN', f'{dsn} not shown in this Python process; verify 32/64-bit User/System DSN visibility.')
    except Exception as exc:
        code, advice = classify_exception(exc)
        report.add('WARN', 'ODBC driver inventory', f'{code}: {advice}')
    return True


def run_diagnostics():
    from . import database as db

    report = CheckReport()
    if not environment_preflight(report):
        return report
    try:
        conn = db._connect()
    except Exception as exc:
        code, advice = classify_exception(exc)
        report.add('FAIL', 'Connect to Oracle', f'{code}: {advice}')
        return report
    try:
        inspect_connection(conn, report)
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()
    return report
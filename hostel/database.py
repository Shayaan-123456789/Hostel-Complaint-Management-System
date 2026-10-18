"""Oracle ODBC adapter: one connection/transaction per request, qmark parameters.

This deliberately avoids Django ORM/migrations, preserving the final nine-table
Oracle schema. For an OUT-ID procedure, read the matching sequence CURRVAL from
this SAME connection after calling the PL/SQL procedure.
"""
import logging
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured

log = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    pass


class DatabaseFailure(Exception):
    def __init__(self, message='Database operation failed.', status=400):
        super().__init__(message)
        self.status = status


# Only expected Oracle application errors are exposed. Unknown SQL errors are not.
BUSINESS_CODES = {str(i) for i in range(20001, 20060)}


def _connect():
    try:
        import pyodbc
    except ImportError as exc:
        raise DatabaseUnavailable('The pyodbc package is not installed.') from exc
    dsn = os.getenv('ORACLE_ODBC_DSN')
    owner = os.getenv('ORACLE_SCHEMA_OWNER', '').strip().upper()
    if owner and not re.fullmatch(r'[A-Z][A-Z0-9_$#]*', owner):
        raise DatabaseUnavailable('ORACLE_SCHEMA_OWNER is not a valid unquoted Oracle schema name.')
    uid = os.getenv('ORACLE_DB_USER')
    pwd = os.getenv('ORACLE_DB_PASSWORD')
    if not all([dsn, uid, pwd]) or pwd.startswith('REPLACE_'):
        raise DatabaseUnavailable('Oracle ODBC connection is not configured.')
    # Oracle in OraDB21Home1 rejected brace-wrapped passwords (ORA-01017)
    # on the verified Windows installation, while the unbraced PWD succeeded.
    # Protect the connection string from delimiter injection instead of wrapping
    # credentials in braces. A password containing a semicolon cannot be safely
    # represented by this driver's proven plain-PWD connection method.
    if any(';' in item or '\r' in item or '\n' in item for item in (dsn, uid, pwd)):
        raise DatabaseUnavailable(
            'An Oracle ODBC connection setting contains a delimiter. '
            'Use credentials without semicolons/newlines for this connection method.'
        )
    conn_str = f'DSN={dsn};UID={uid};PWD={pwd};'
    try:
        conn = pyodbc.connect(conn_str, autocommit=False, timeout=8)
        if owner:
            # CURRENT_SCHEMA controls name resolution, not privileges.
            # Validate the identifier above before including it in SQL.
            try:
                cursor = conn.cursor()
                try:
                    cursor.execute(f'ALTER SESSION SET CURRENT_SCHEMA = {owner}')
                finally:
                    cursor.close()
            except Exception:
                conn.close()
                raise
        return conn
    except pyodbc.Error as exc:
        # Do not log the full ODBC exception, which may contain connection details.
        log.error('Oracle ODBC connection failed (see check_oracle for safe diagnostics).')
        raise DatabaseUnavailable('Cannot connect to Oracle. Run python manage.py check_oracle.') from exc


def _raise_sql(exc):
    msg = str(exc)
    match = re.search(r'ORA-(20\d{3}):\s*([^\r\n]+)', msg)
    if match and match.group(1) in BUSINESS_CODES:
        raise DatabaseFailure(match.group(2).strip()) from exc
    if 'ORA-00001' in msg:
        raise DatabaseFailure('This record already exists.') from exc
    if 'ORA-02291' in msg or 'ORA-02292' in msg:
        raise DatabaseFailure('Referenced record does not exist or is still in use.') from exc
    if 'ORA-01400' in msg or 'ORA-12899' in msg or 'ORA-02290' in msg:
        raise DatabaseFailure('One or more values violate database constraints.') from exc
    log.exception('Unexpected Oracle SQL error')
    raise DatabaseFailure('The database rejected this operation.', status=500) from exc


@contextmanager
def session(write=False):
    conn = _connect()
    try:
        yield conn
        if write:
            conn.commit()
        else:
            conn.rollback()  # end the read transaction explicitly
    except Exception:
        try:
            conn.rollback()
        except Exception:
            log.exception('Oracle rollback failed')
        raise
    finally:
        conn.close()


def _odbc_parameter(value):
    """Avoid passing Oracle NUMBER integer IDs back as Decimal bind values.

    Keep fractional Decimal values intact to avoid silently changing their
    meaning. The per-role actor normalization is the primary safeguard.
    """
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    return value


def _execute(conn, sql, params=()):
    import pyodbc
    cursor = conn.cursor()
    try:
        cursor.execute(sql, tuple(_odbc_parameter(item) for item in params))
        return cursor
    except pyodbc.Error as exc:
        cursor.close()
        _raise_sql(exc)


def all_rows(conn, sql, params=()):
    cursor = _execute(conn, sql, params)
    try:
        cols = [c[0].lower() for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def one(conn, sql, params=()):
    cursor = _execute(conn, sql, params)
    try:
        cols = [c[0].lower() for c in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row is not None else None
    finally:
        cursor.close()


def value(conn, sql, params=()):
    cursor = _execute(conn, sql, params)
    try:
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def run(conn, sql, params=()):
    cursor = _execute(conn, sql, params)
    try:
        return cursor.rowcount
    finally:
        cursor.close()


def call(conn, procedure_name, params=()):
    # Names are hard-coded by the application, never derived from user input.
    if procedure_name not in {
        'sp_add_photo', 'sp_assign_complaint', 'sp_update_status',
        'sp_submit_feedback', 'sp_escalate_overdue',
    }:
        raise ValueError('Procedure not whitelisted')
    placeholders = ', '.join(['?'] * len(params))
    run(conn, f'BEGIN {procedure_name}({placeholders}); END;', params)


def call_with_id(conn, procedure_name, params):
    sequence = {
        'sp_register_student': 'seq_student',
        'sp_submit_complaint': 'seq_complaint',
    }.get(procedure_name)
    if not sequence:
        raise ValueError('Procedure not whitelisted')
    placeholders = ', '.join(['?'] * len(params))
    # The OUT argument is a local PL/SQL variable. Oracle ODBC does not need
    # to bind a Python OUT parameter; CURRVAL returns the ID created in this session.
    run(conn, f'DECLARE v_new_id NUMBER; BEGIN {procedure_name}({placeholders}, v_new_id); END;', params)
    result = value(conn, f'SELECT {sequence}.CURRVAL FROM dual')
    if result is None:
        raise DatabaseFailure('Cannot obtain the new record ID.', status=500)
    return int(result)


def page(conn, base_sql, params, limit, offset):
    """Oracle 11g-compatible pagination; ORDER BY must appear inside base_sql."""
    sql = f'''SELECT * FROM (
      SELECT q.*, ROWNUM AS page_row_number FROM ({base_sql}) q WHERE ROWNUM <= ?
    ) WHERE page_row_number > ?'''
    rows = all_rows(conn, sql, [*params, offset + limit, offset])
    for row in rows:
        row.pop('page_row_number', None)
    return rows


def json_ready(obj):
    if isinstance(obj, dict):
        return {k: json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_ready(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj

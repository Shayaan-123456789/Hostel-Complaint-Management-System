"""Role tokens: all users live in the fixed STUDENT/STAFF tables or .env."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password

from . import database as db


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _normalize_numeric_id(raw):
    """Convert Oracle NUMBER primary keys to Python int before API/ODBC use.

    Oracle ODBC may return NUMBER IDs as decimal.Decimal. Some Oracle driver
    builds reject Decimal bind parameters even though integer binds work.
    Only integral, positive identifiers are accepted here.
    """
    if isinstance(raw, bool):
        raise ApiError('Invalid account identifier.', 401)
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ApiError('Invalid account identifier.', 401) from exc
    if value <= 0 or (isinstance(raw, Decimal) and (not raw.is_finite() or raw != value)):
        raise ApiError('Invalid account identifier.', 401)
    return value


def admin_config():
    username = os.getenv('HOSTEL_ADMIN_USERNAME', '').strip().lower()
    pw_hash = os.getenv('HOSTEL_ADMIN_PASSWORD_HASH', '')
    return username, pw_hash


def jwt_secret():
    raw = os.getenv('HOSTEL_JWT_SECRET', '')
    if not raw or raw.startswith('REPLACE_'):
        if settings.DEBUG:
            return settings.SECRET_KEY
        raise ApiError('Token secret is not configured.', 503)
    return raw


def pw_version(pw_hash):
    return hashlib.sha256(pw_hash.encode('utf-8')).hexdigest()[:20]


def issue_token(role, identity, pw_hash):
    now = datetime.now(timezone.utc)
    ttl = max(1, min(24, int(os.getenv('HOSTEL_TOKEN_HOURS', '4'))))
    claims = {
        'sub': f'{role}:{identity}', 'role': role,
        'iat': now, 'nbf': now, 'exp': now + timedelta(hours=ttl),
        'iss': 'smart-hostel-api', 'aud': 'smart-hostel-frontend',
        'pwd': pw_version(pw_hash),
    }
    return jwt.encode(claims, jwt_secret(), algorithm='HS256')


def authenticate(conn, request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or len(auth) > 4096:
        raise ApiError('Authentication required. Supply a Bearer token.', 401)
    try:
        claims = jwt.decode(
            auth[7:], jwt_secret(), algorithms=['HS256'],
            audience='smart-hostel-frontend', issuer='smart-hostel-api',
            options={'require': ['sub', 'role', 'iat', 'nbf', 'exp', 'pwd']},
        )
    except jwt.PyJWTError as exc:
        raise ApiError('Invalid or expired authentication token.', 401) from exc
    role = claims.get('role')
    subject = claims.get('sub')
    if role not in ('STUDENT', 'STAFF', 'WARDEN') or not isinstance(subject, str):
        raise ApiError('Invalid authentication token.', 401)
    prefix = f'{role}:'
    if not subject.startswith(prefix):
        raise ApiError('Invalid authentication token.', 401)
    identity = subject[len(prefix):]
    if role == 'WARDEN':
        username, pw_hash = admin_config()
        if identity != username or not pw_hash or pw_hash.startswith('REPLACE_'):
            raise ApiError('Administrator account unavailable.', 401)
        actor = {'role': role, 'id': username, 'name': username, 'email': None}
    else:
        if not identity.isdigit():
            raise ApiError('Invalid authentication token.', 401)
        table = 'student' if role == 'STUDENT' else 'staff'
        pk = 'student_id' if role == 'STUDENT' else 'staff_id'
        actor = db.one(conn, f'SELECT {pk} AS id, name, email, status, password FROM {table} WHERE {pk} = ?', [int(identity)])
        if not actor or actor['status'] != 'ACTIVE':
            raise ApiError('Account is inactive or unavailable.', 401)
        actor['id'] = _normalize_numeric_id(actor['id'])
        pw_hash = actor.pop('password')
        actor.pop('status', None)
        # The database projection has no role column. Every authenticated
        # actor must carry the verified JWT role for authorization and
        # role-scoped complaint queries (student AND staff).
        actor['role'] = role
    if not hmac.compare_digest(claims.get('pwd', ''), pw_version(pw_hash)):
        raise ApiError('Authentication expired following a password change.', 401)
    return actor


def verify_login(conn, role, identifier, password):
    role = (role or '').strip().upper()
    identifier = (identifier or '').strip().lower()
    if role == 'WARDEN':
        username, pw_hash = admin_config()
        if not username or not pw_hash or pw_hash.startswith('REPLACE_'):
            raise ApiError('Administrator login is not configured.', 503)
        # One common error message prevents credential enumeration.
        if not hmac.compare_digest(identifier, username) or not check_password(password, pw_hash):
            raise ApiError('Invalid credentials or account type.', 401)
        actor = {'role': 'WARDEN', 'id': username, 'name': username, 'email': None}
    elif role in ('STUDENT', 'STAFF'):
        table = 'student' if role == 'STUDENT' else 'staff'
        pk = 'student_id' if role == 'STUDENT' else 'staff_id'
        row = db.one(conn, f'SELECT {pk} AS id, name, email, password, status FROM {table} WHERE LOWER(email) = ?', [identifier])
        if not row or row['status'] != 'ACTIVE' or not check_password(password, row['password']):
            raise ApiError('Invalid credentials or account type.', 401)
        row['id'] = _normalize_numeric_id(row['id'])
        pw_hash = row.pop('password')
        row.pop('status')
        actor = {'role': role, **row}
    else:
        raise ApiError('Role must be STUDENT, STAFF, or WARDEN.')
    token = issue_token(actor['role'], actor['id'], pw_hash)
    return {'access_token': token, 'token_type': 'Bearer', 'expires_in_hours': max(1, min(24, int(os.getenv('HOSTEL_TOKEN_HOURS', '4')))), 'user': actor}

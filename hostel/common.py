"""Django request / response helpers and strict input validation."""
import json
import logging
import re
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import database as db
from .security import ApiError, authenticate

log = logging.getLogger(__name__)


def response(data, status=200):
    return JsonResponse(db.json_ready(data), status=status, safe=isinstance(data, dict))


def endpoint(methods=('GET',), roles=(), write=False, public=False):
    """Every nonpublic endpoint authenticates before accessing business data."""
    def decorator(handler):
        @wraps(handler)
        @csrf_exempt  # Stateless Authorization: Bearer, never cookies; restrict CORS origins.
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                r = response({'error': 'Method not allowed.'}, 405)
                r['Allow'] = ', '.join(methods)
                return r
            request._hostel_saved_paths = []
            try:
                with db.session(write=write) as conn:
                    actor = None if public else authenticate(conn, request)
                    if roles and actor and actor['role'] not in roles:
                        raise ApiError('You do not have permission to perform this action.', 403)
                    result = handler(request, conn, actor, *args, **kwargs)
                return result
            except ApiError as exc:
                _cleanup_paths(request)
                return response({'error': str(exc)}, exc.status)
            except db.DatabaseFailure as exc:
                _cleanup_paths(request)
                return response({'error': str(exc)}, exc.status)
            except db.DatabaseUnavailable as exc:
                _cleanup_paths(request)
                log.error('Database unavailable: %s', exc)
                return response({'error': 'Database temporarily unavailable.'}, 503)
            except Exception:
                _cleanup_paths(request)
                log.exception('Unexpected API error')
                return response({'error': 'Internal server error.'}, 500)
        return wrapped
    return decorator


def payload(request):
    content_type = request.content_type or ''
    if content_type == 'application/json' or content_type.endswith('+json'):
        try:
            parsed = json.loads(request.body or '{}')
        except (ValueError, UnicodeDecodeError):
            raise ApiError('Invalid JSON body.')
        if not isinstance(parsed, dict):
            raise ApiError('Request body must be a JSON object.')
        return parsed
    if content_type.startswith('multipart/form-data') or content_type == 'application/x-www-form-urlencoded':
        return request.POST.dict()
    raise ApiError('Use application/json or multipart/form-data.')


def required(data, key, max_len=None):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f'{key} is required.')
    value = value.strip()
    if max_len and len(value) > max_len:
        raise ApiError(f'{key} must be at most {max_len} characters.')
    return value


def optional(data, key, max_len=None):
    value = data.get(key)
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ApiError(f'{key} must be text.')
    value = value.strip()
    if max_len and len(value) > max_len:
        raise ApiError(f'{key} must be at most {max_len} characters.')
    return value or None


def integer(data, key, low=1, high=99999999):
    raw = data.get(key)
    if isinstance(raw, bool):
        raise ApiError(f'{key} must be a whole number.')
    try:
        n = int(raw)
        if str(n) != str(raw).strip():
            raise ValueError()
    except (TypeError, ValueError):
        raise ApiError(f'{key} must be a whole number.')
    if not low <= n <= high:
        raise ApiError(f'{key} must be between {low} and {high}.')
    return n


def password_strength(password):
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        raise ApiError('Password must contain 10–128 characters.')
    if not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        raise ApiError('Password must contain a letter and a digit.')
    return password


def email_address(value):
    value = value.strip().lower()
    if len(value) > 120 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise ApiError('Provide a valid email address.')
    return value


def paging(request):
    limit = integer(request.GET, 'limit', 1, 100) if 'limit' in request.GET else 25
    offset = integer(request.GET, 'offset', 0, 1000000) if 'offset' in request.GET else 0
    return limit, offset


def choice(data, key, allowed, default=None):
    value = data.get(key, default)
    if not isinstance(value, str) or value.strip().upper() not in allowed:
        raise ApiError(f'{key} must be one of: {", ".join(sorted(allowed))}.')
    return value.strip().upper()


def _cleanup_paths(request):
    from .media import delete_photo
    for path in getattr(request, '_hostel_saved_paths', []):
        try:
            delete_photo(path)
        except Exception:
            log.exception('Failed to clean orphaned upload: %s', path)

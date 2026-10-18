from django.conf import settings
from django.http import HttpResponse


class AllowedOriginsMiddleware:
    """Exact-match CORS allowlist, including restricted preflight endpoints."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        allowed = origin in settings.HOSTEL_ALLOWED_ORIGINS
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            response = HttpResponse(status=204 if allowed else 403)
        else:
            response = self.get_response(request)
        if allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Vary'] = 'Origin'
            response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, OPTIONS'
            response['Access-Control-Max-Age'] = '600'
        return response

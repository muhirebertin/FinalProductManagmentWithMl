# analytics/api/auth.py
"""
Authentication, permissions and JSON envelope helpers for the REST API.

Authentication (in this order):
  1. API key   - header  `X-API-Key: <key>`  or  `Authorization: Api-Key <key>`
  2. Session   - a user logged in to the web app (used by the dashboard's AJAX).
                 Unsafe methods (POST) with session auth must send the CSRF token.
Permissions:
  * read  (GET)  : any authenticated user
  * write (POST) : staff users only (managers / admins)
Response envelope:
  success -> {"status": "ok", "data": ..., "meta": {...}}
  error   -> {"status": "error", "error": {"code": "...", "message": "...", "details": {...}}}
"""
import json
import logging
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("analytics")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def ok(data=None, status=200, **meta):
    meta.setdefault("generated_at", timezone.now().isoformat())
    return JsonResponse({"status": "ok", "data": data, "meta": meta}, status=status,
                        json_dumps_params={"ensure_ascii": False})


def error(code, message, status=400, details=None):
    body = {"status": "error", "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JsonResponse(body, status=status)


def read_json(request):
    """Parse a JSON body (or fall back to form data). Raises ValueError on bad JSON."""
    if request.content_type == "application/json":
        raw = request.body.decode("utf-8") or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data
    return request.POST.dict()


def _extract_key(request):
    key = request.META.get("HTTP_X_API_KEY", "")
    if not key:
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        for prefix in ("Api-Key ", "Bearer "):
            if auth.startswith(prefix):
                key = auth[len(prefix):]
    return key.strip()


def api_endpoint(methods=("GET",), public=False, staff_methods=UNSAFE):
    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            from analytics.models import APIKey

            if request.method not in methods:
                resp = error("method_not_allowed", f"Method {request.method} not allowed.", 405)
                resp["Allow"] = ", ".join(methods)
                return resp

            user, via = None, None
            raw_key = _extract_key(request)
            if raw_key:
                key = APIKey.authenticate(raw_key)
                if key is None:
                    return error("invalid_api_key", "The API key is invalid or has been revoked.", 401)
                user, via = key.user, "api_key"
            elif request.user.is_authenticated:
                user, via = request.user, "session"
                if request.method in UNSAFE:
                    rejected = CsrfViewMiddleware(lambda r: None).process_view(request, None, (), {})
                    if rejected is not None:
                        return error("csrf_failed", "CSRF token missing or incorrect.", 403)

            if user is None and not public:
                return error("not_authenticated",
                             "Authentication required. Send an 'X-API-Key' header or log in.", 401)
            if user is not None and request.method in staff_methods and not user.is_staff:
                return error("permission_denied", "Only staff users (managers) can perform this action.", 403)

            request.api_user, request.api_auth = user, via
            try:
                return view(request, *args, **kwargs)
            except Exception as exc:  # never return an HTML error page to API clients
                logger.exception("API error on %s", request.path)
                message = str(exc) if settings.DEBUG else "Internal server error."
                return error("server_error", message, 500)
        wrapper.api_methods = methods
        return wrapper
    return decorator

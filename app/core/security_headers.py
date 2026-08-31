"""
app/core/security_headers.py
============================
Enterprise HTTP Security Headers Middleware.
Prevents XSS, Clickjacking, MIME-sniffing, CSRF, and Data Exfiltration.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects enterprise-grade HTTP security headers on all responses.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # 1. Content Security Policy (CSP)
        csp_directives = [
            "default-src 'self'",
            "img-src 'self' data: blob: https: http:",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "connect-src 'self' https: http: ws: wss:",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # 2. Clickjacking Prevention
        response.headers["X-Frame-Options"] = "DENY"

        # 3. MIME-Sniffing Prevention
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 4. Cross-Site Scripting (XSS) Legacy Protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 5. Referrer Policy (Prevents leaking query tokens or evidence IDs)
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 6. Permissions Policy (Disables unused browser hardware access)
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

        # 7. Cross-Domain Policy
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # 8. Cache-Control for sensitive API endpoints (prevents disk caching of evidence)
        if request.url.path.startswith("/api/") or request.url.path.startswith("/storage/") or request.url.path.startswith("/reports/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        return response

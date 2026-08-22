"""
app/core/rate_limiter.py
========================
High-Performance In-Memory Sliding Window Rate Limiter & DDoS Mitigation Middleware.
Throttles brute-force login attempts, evidence upload flooding, and API abuse.
"""
import time
import logging
from collections import defaultdict
from typing import Dict, List, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Tracks request timestamps per IP and enforces sliding-window quotas."""
    def __init__(self):
        # ip -> list of timestamps
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, ip: str, limit: int, window_seconds: float = 60.0) -> Tuple[bool, int, float]:
        now = time.time()
        cutoff = now - window_seconds

        # Prune older timestamps
        self.requests[ip] = [t for t in self.requests[ip] if t > cutoff]

        
        # Memory safety: prune empty IP records periodically
        if len(self.requests) > 5000:
            inactive_ips = [k for k, v in self.requests.items() if not v or v[-1] < cutoff]
            for k in inactive_ips[:1000]:
                del self.requests[k]
        current_count = len(self.requests[ip])
        if current_count >= limit:
            oldest = self.requests[ip][0]
            retry_after = round(window_seconds - (now - oldest), 1)
            return False, current_count, max(1.0, retry_after)

        self.requests[ip].append(now)
        return True, current_count + 1, 0.0


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Applies route-specific rate limits to protect authentication and forensic resources.
    """
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self.auth_limiter = SlidingWindowRateLimiter()      # 20 req / min (Auth login/register/otp)
        self.upload_limiter = SlidingWindowRateLimiter()    # 40 req / min (Evidence Uploads)
        self.api_limiter = SlidingWindowRateLimiter()       # 240 req / min (General API)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Get client IP (support reverse proxies / Cloudflare headers)
        ip = (
            request.headers.get("CF-Connecting-IP") or
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            (request.client.host if request.client else "127.0.0.1")
        )

        path = request.url.path

        # 1. Auth Endpoints Rate Limit (Anti-Brute-Force: 25 attempts/min)
        if path.startswith("/api/auth/login") or path.startswith("/api/auth/register") or path.startswith("/api/auth/verify-email"):
            allowed, count, retry_after = self.auth_limiter.is_allowed(ip, limit=25, window_seconds=60.0)
            if not allowed:
                logger.warning(f"Rate limit triggered for Auth from IP {ip} ({count} reqs)")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "detail": f"Too many authentication attempts. Please wait {int(retry_after)} seconds.",
                        "retry_after_seconds": retry_after
                    },
                    headers={"Retry-After": str(int(retry_after))}
                )

        # 2. Evidence Upload Rate Limit (Anti-Flooding: 50 uploads/min)
        elif path.startswith("/api/evidence/upload"):
            allowed, count, retry_after = self.upload_limiter.is_allowed(ip, limit=50, window_seconds=60.0)
            if not allowed:
                logger.warning(f"Rate limit triggered for Upload from IP {ip}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "UPLOAD_RATE_LIMIT_EXCEEDED",
                        "detail": f"Evidence intake rate limit exceeded. Please wait {int(retry_after)} seconds.",
                        "retry_after_seconds": retry_after
                    },
                    headers={"Retry-After": str(int(retry_after))}
                )

        # 3. General API Rate Limit (300 req/min)
        elif path.startswith("/api/"):
            allowed, count, retry_after = self.api_limiter.is_allowed(ip, limit=300, window_seconds=60.0)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "API_RATE_LIMIT_EXCEEDED",
                        "detail": f"Request quota exceeded. Please slow down.",
                        "retry_after_seconds": retry_after
                    },
                    headers={"Retry-After": str(int(retry_after))}
                )

        return await call_next(request)

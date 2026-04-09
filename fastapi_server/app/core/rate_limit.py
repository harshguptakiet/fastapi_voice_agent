from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request
import time
from collections import defaultdict

RATE_LIMIT = 30  # requests
RATE_PERIOD = 60  # seconds

class SimpleRateLimiter(BaseHTTPMiddleware):
    _buckets = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        now = time.time()
        bucket = self._buckets[ip]
        # Remove old requests
        bucket[:] = [t for t in bucket if now - t < RATE_PERIOD]
        if len(bucket) >= RATE_LIMIT:
            return JSONResponse({"error": "Rate limit exceeded. Try again later."}, status_code=429)
        bucket.append(now)
        return await call_next(request)

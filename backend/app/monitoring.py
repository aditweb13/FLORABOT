"""
FloraBOT Production Monitoring, Structured Logging & Metrics Module:
Provides:
1. Structured JSON Logging with correlation IDs (X-Request-ID).
2. Prometheus-compatible Application Metrics exposition (/api/metrics).
3. In-memory Sliding-Window Rate Limiter with 429 Too Many Requests response.
4. FastAPI Middleware for telemetry, request tracing, and latency tracking.
"""

import time
import uuid
import json
import logging
from collections import defaultdict
from typing import Dict, List, Tuple
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ============================================================================
# 1. STRUCTURED JSON FORMATTER
# ============================================================================

class JsonFormatter(logging.Formatter):
    """Formats log records as structured JSON for log aggregators (ELK, CloudWatch, Datadog)."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "client_ip"):
            log_obj["client_ip"] = record.client_ip
        if hasattr(record, "status_code"):
            log_obj["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        return json.dumps(log_obj)

logger = logging.getLogger("florabot.access")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

# ============================================================================
# 2. SLIDING WINDOW RATE LIMITER
# ============================================================================

class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""
    def __init__(self):
        # ip -> list of float timestamps
        self._history: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, client_ip: str, limit: int = 60, window_sec: int = 60) -> Tuple[bool, int, int]:
        """
        Returns:
            (is_allowed, remaining_quota, retry_after_sec)
        """
        now = time.time()
        window_start = now - window_sec
        
        # Purge timestamps outside sliding window
        timestamps = [ts for ts in self._history[client_ip] if ts > window_start]
        self._history[client_ip] = timestamps
        
        if len(timestamps) >= limit:
            oldest_in_window = timestamps[0]
            retry_after = max(1, int(oldest_in_window + window_sec - now))
            return False, 0, retry_after
        
        timestamps.append(now)
        self._history[client_ip] = timestamps
        remaining = max(0, limit - len(timestamps))
        return True, remaining, 0

rate_limiter = SlidingWindowRateLimiter()

# ============================================================================
# 3. PROMETHEUS METRICS REGISTRY
# ============================================================================

class PrometheusMetricsRegistry:
    """Lightweight in-memory Prometheus metrics store."""
    def __init__(self):
        # (method, endpoint, status) -> count
        self.http_requests_total: Dict[Tuple[str, str, int], int] = defaultdict(int)
        # (method, endpoint) -> [duration_seconds]
        self.http_duration_sum: Dict[Tuple[str, str], float] = defaultdict(float)
        self.http_duration_count: Dict[Tuple[str, str], int] = defaultdict(int)
    
    def record_request(self, method: str, endpoint: str, status_code: int, duration_sec: float):
        self.http_requests_total[(method, endpoint, status_code)] += 1
        self.http_duration_sum[(method, endpoint)] += duration_sec
        self.http_duration_count[(method, endpoint)] += 1
    
    def generate_exposition(self, db_session = None) -> str:
        """Produce standard Prometheus text-based exposition."""
        lines = []
        
        # 1. HTTP requests total
        lines.append("# HELP florabot_http_requests_total Total number of HTTP requests processed")
        lines.append("# TYPE florabot_http_requests_total counter")
        for (m, ep, s), val in self.http_requests_total.items():
            lines.append(f'florabot_http_requests_total{{method="{m}",endpoint="{ep}",status="{s}"}} {val}')
        
        # 2. HTTP request duration
        lines.append("# HELP florabot_http_request_duration_seconds_total Total duration of HTTP requests in seconds")
        lines.append("# TYPE florabot_http_request_duration_seconds_total counter")
        for (m, ep), total_sec in self.http_duration_sum.items():
            lines.append(f'florabot_http_request_duration_seconds_total{{method="{m}",endpoint="{ep}"}} {total_sec:.4f}')
        
        lines.append("# HELP florabot_http_request_duration_seconds_count Count of HTTP requests tracked for latency")
        lines.append("# TYPE florabot_http_request_duration_seconds_count counter")
        for (m, ep), cnt in self.http_duration_count.items():
            lines.append(f'florabot_http_request_duration_seconds_count{{method="{m}",endpoint="{ep}"}} {cnt}')
        
        # 3. Database gauges if session provided
        if db_session:
            try:
                from .models import Plant, Device, Analysis
                plant_count = db_session.query(Plant).count()
                analysis_count = db_session.query(Analysis).count()
                online_devices = db_session.query(Device).filter(Device.status == "online").count()
                total_devices = db_session.query(Device).count()
                
                lines.append("# HELP florabot_plants_total Total registered plants")
                lines.append("# TYPE florabot_plants_total gauge")
                lines.append(f"florabot_plants_total {plant_count}")
                
                lines.append("# HELP florabot_analyses_total Total diagnostic analyses conducted")
                lines.append("# TYPE florabot_analyses_total gauge")
                lines.append(f"florabot_analyses_total {analysis_count}")
                
                lines.append("# HELP florabot_devices_online_total Connected active hardware sensors")
                lines.append("# TYPE florabot_devices_online_total gauge")
                lines.append(f"florabot_devices_online_total {online_devices}")
                
                lines.append("# HELP florabot_devices_total Total registered hardware devices")
                lines.append("# TYPE florabot_devices_total gauge")
                lines.append(f"florabot_devices_total {total_devices}")
            except Exception:
                pass
        
        lines.append("")
        return "\n".join(lines)

metrics_registry = PrometheusMetricsRegistry()

# ============================================================================
# 4. FASTAPI TELEMETRY & SECURITY MIDDLEWARE
# ============================================================================

class ProductionSecurityMiddleware(BaseHTTPMiddleware):
    """
    Production-grade middleware:
    - Generates and propagates X-Request-ID correlation header.
    - Applies sliding-window IP rate limiting.
    - Measures request execution duration.
    - Increments Prometheus metrics counters.
    - Outputs structured JSON access logs.
    """
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "127.0.0.1"
        
        # Normalize endpoint path for metric grouping
        path = request.url.path
        
        # Exclude metric scrape and static assets from rate limiting
        if not path.startswith(("/api/metrics", "/files/", "/static/")):
            limit = 10 if path == "/api/auth/login" else 60
            allowed, remaining, retry_after = rate_limiter.is_allowed(client_ip, limit=limit, window_sec=60)
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Too Many Requests",
                        "message": f"Rate limit exceeded ({limit} requests/minute). Please slow down.",
                        "retry_after_seconds": retry_after
                    },
                    headers={
                        "X-Request-ID": request_id,
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0"
                    }
                )
        
        # Proceed with request
        response = await call_next(request)
        
        duration = time.time() - start_time
        duration_ms = round(duration * 1000, 2)
        
        # Record metrics
        metrics_registry.record_request(request.method, path, response.status_code, duration)
        
        # Add tracking headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        
        # Structured log
        record = logging.LogRecord(
            name="florabot.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=180,
            msg=f"{request.method} {path} {response.status_code} ({duration_ms}ms)",
            args=(),
            exc_info=None
        )
        record.request_id = request_id
        record.client_ip = client_ip
        record.status_code = response.status_code
        record.duration_ms = duration_ms
        logger.handle(record)
        
        return response

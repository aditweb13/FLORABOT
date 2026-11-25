"""
FloraBOT Phase 9 Automated Test Suite:
Validates Security, Authentication, RBAC, Deployment Readiness,
Monitoring, Database Backup & Recovery, and Infrastructure Hardening:
1. Salted Password Hashing & Constant-Time Verification
2. Standard RFC 7519 JWT (HS256) Token Lifecycle & Expiration
3. User Registration, Login & Audit Trail Persistence
4. Role-Based Access Control (RBAC) & IoT Device Authentication
5. In-Memory Sliding-Window Rate Limiting
6. Structured JSON Logging & Prometheus Metrics Exposition
7. Automated Database Live Backup, SHA-256 Checksum & Recovery Drill
8. PostgreSQL Migration Schema Ordering & Reflection
9. Production Nginx Reverse Proxy Configuration & Security Directive Audit
"""

import sys
import os
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, User, AuditLog, Plant, Device
from app.auth import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_api_key, require_role, verify_device_api_key, log_audit_event
)
from app.monitoring import (
    JsonFormatter, SlidingWindowRateLimiter, PrometheusMetricsRegistry
)
from app.config import settings
from scripts.db_backup_restore import create_backup, restore_backup, calculate_sha256
from scripts.migrate_sqlite_to_postgres import TABLE_MIGRATION_ORDER

TEST_DB_PATH = backend_dir / "data" / "test_phase9.db"

def get_test_db():
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
    TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{TEST_DB_PATH}", echo=False)
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)

# ============================================================================
# 1. PASSWORD HASHING TESTS
# ============================================================================

def test_password_hashing():
    print("[1/9] Testing Salted Password Hashing & Constant-Time Verification...")
    raw_pass = "FloraBot_SuperSecret_2026!"
    h1 = hash_password(raw_pass)
    h2 = hash_password(raw_pass)
    
    assert h1.startswith("pbkdf2_sha256$100000$"), "Invalid hash prefix or iterations"
    assert h1 != h2, "Unique salts must generate distinct hashes"
    
    assert verify_password(raw_pass, h1) is True, "Password verification failed for valid password"
    assert verify_password("WrongPassword123", h1) is False, "Password verification erroneously accepted wrong password"
    assert verify_password(raw_pass, "corrupted$hash$value") is False, "Corrupted hash must be rejected safely"
    print("  -> Passed password hashing and salt verification tests.")

# ============================================================================
# 2. JWT TOKEN LIFECYCLE TESTS
# ============================================================================

def test_jwt_token_lifecycle():
    print("[2/9] Testing RFC 7519 JWT (HS256) Minting, Claims & Expiration...")
    claims = {"sub": "botanist_jane", "user_id": 42, "role": "admin"}
    token = create_access_token(claims, expires_delta=timedelta(hours=2))
    
    # Verify structure
    parts = token.split(".")
    assert len(parts) == 3, "JWT must consist of header, payload, and signature"
    
    # Decode and verify claims
    decoded = decode_access_token(token)
    assert decoded["sub"] == "botanist_jane"
    assert decoded["user_id"] == 42
    assert decoded["role"] == "admin"
    assert decoded["exp"] > decoded["iat"]
    
    # Tampered signature detection
    tampered_token = token[:-5] + ("AAAAA" if token[-5:] != "AAAAA" else "BBBBB")
    tamper_detected = False
    try:
        decode_access_token(tampered_token)
    except Exception:
        tamper_detected = True
    assert tamper_detected is True, "Tampered signature was not rejected"
    
    # Expired token rejection
    expired_token = create_access_token(claims, expires_delta=timedelta(seconds=-10))
    expired_rejected = False
    try:
        decode_access_token(expired_token)
    except Exception:
        expired_rejected = True
    assert expired_rejected is True, "Expired token was not rejected"
    print("  -> Passed JWT minting, claim verification, tampering and expiration tests.")

# ============================================================================
# 3. USER REGISTRATION, LOGIN & AUDIT LOGGING
# ============================================================================

def test_user_auth_and_audit(db: Session):
    print("[3/9] Testing User Registration, Authentication Flow & Audit Logs...")
    # Register user
    username = "lead_agronomist"
    email = "agronomist@florabot.org"
    password = "GreenThumbPassword#1"
    
    hashed = hash_password(password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed,
        full_name="Dr. Jane Botanist",
        role="operator",
        is_active=True,
        api_key=generate_api_key()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.id is not None
    
    # Log audit event
    log_audit_event(db, actor=username, action="USER_REGISTERED", resource=f"user:{user.id}", details={"role": "operator"}, ip_address="192.168.1.50")
    
    # Verify login credential validation
    queried_user = db.query(User).filter(User.username == username).first()
    assert queried_user is not None
    assert verify_password(password, queried_user.hashed_password) is True
    
    # Check audit log entry
    audit = db.query(AuditLog).filter(AuditLog.actor_username == username).first()
    assert audit is not None
    assert audit.action == "USER_REGISTERED"
    assert audit.ip_address == "192.168.1.50"
    print(f"  -> Passed User creation (ID: {user.id}) and Audit trail persistence.")

# ============================================================================
# 4. RBAC & IOT DEVICE AUTHENTICATION
# ============================================================================

def test_rbac_and_device_auth(db: Session):
    print("[4/9] Testing Role-Based Access Control (RBAC) & IoT Device Authentication...")
    # Create admin and viewer users
    admin_user = User(username="admin_user", email="admin@florabot.org", hashed_password=hash_password("admin123"), role="admin")
    operator_user = User(username="operator_user", email="op@florabot.org", hashed_password=hash_password("op123"), role="operator")
    viewer_user = User(username="viewer_user", email="view@florabot.org", hashed_password=hash_password("view123"), role="viewer")
    db.add_all([admin_user, operator_user, viewer_user])
    db.commit()
    
    admin_checker = require_role(["admin"])
    # With enable_auth temporarily enabled for testing
    orig_auth = settings.enable_auth
    settings.enable_auth = True
    try:
        # Admin user allowed
        assert admin_checker(admin_user).role == "admin"
        
        # Viewer denied from admin action
        denied = False
        try:
            admin_checker(viewer_user)
        except Exception:
            denied = True
        assert denied is True, "Viewer must be denied access to admin role endpoints"
    finally:
        settings.enable_auth = orig_auth
    
    # IoT Device API Key Authentication test
    class MockRequest:
        def __init__(self, headers=None, query_params=None):
            self.headers = headers or {}
            self.query_params = query_params or {}
    
    valid_req = MockRequest(headers={"X-API-Key": settings.device_api_key})
    invalid_req = MockRequest(headers={"X-API-Key": "invalid-secret-key-123"})
    missing_req = MockRequest()
    
    assert verify_device_api_key(valid_req) is True, "Valid IoT device key must be accepted"
    assert verify_device_api_key(invalid_req) is False, "Invalid device key must be rejected"
    assert verify_device_api_key(missing_req) is False, "Missing device key must be rejected"
    print("  -> Passed RBAC role gating and IoT device pre-shared key authentication.")

# ============================================================================
# 5. IN-MEMORY SLIDING-WINDOW RATE LIMITING
# ============================================================================

def test_sliding_window_rate_limiting():
    print("[5/9] Testing In-Memory Sliding-Window Rate Limiter...")
    limiter = SlidingWindowRateLimiter()
    test_ip = "10.0.0.99"
    limit = 5
    
    # First 5 requests must pass
    for i in range(limit):
        allowed, rem, retry = limiter.is_allowed(test_ip, limit=limit, window_sec=60)
        assert allowed is True, f"Request {i+1} should be permitted"
        assert rem == (limit - i - 1)
    
    # 6th request must be throttled with HTTP 429 semantics
    allowed, rem, retry = limiter.is_allowed(test_ip, limit=limit, window_sec=60)
    assert allowed is False, "Request exceeding limit must be throttled"
    assert rem == 0
    assert retry >= 1, "Retry-After seconds must be provided"
    
    # Other IP addresses must not be blocked
    other_ip = "10.0.0.100"
    allowed_other, _, _ = limiter.is_allowed(other_ip, limit=limit, window_sec=60)
    assert allowed_other is True, "Different IP should have independent quota"
    print(f"  -> Passed rate limiter tests: allowed {limit} reqs, throttled 6th with retry_after={retry}s.")

# ============================================================================
# 6. STRUCTURED JSON LOGGING & PROMETHEUS METRICS
# ============================================================================

def test_monitoring_and_metrics(db: Session):
    print("[6/9] Testing Structured JSON Logging & Prometheus Metrics Exposition...")
    formatter = JsonFormatter()
    record = os.sys.modules["logging"].LogRecord(
        name="florabot.test",
        level=20, # INFO
        pathname=__file__,
        lineno=120,
        msg="GET /api/plants 200 (12.4ms)",
        args=(),
        exc_info=None
    )
    record.request_id = "req-uuid-test-1234"
    record.client_ip = "127.0.0.1"
    record.status_code = 200
    record.duration_ms = 12.4
    
    json_output = formatter.format(record)
    parsed = json.loads(json_output)
    assert parsed["level"] == "INFO"
    assert parsed["request_id"] == "req-uuid-test-1234"
    assert parsed["client_ip"] == "127.0.0.1"
    assert parsed["status_code"] == 200
    assert parsed["duration_ms"] == 12.4
    
    # Prometheus Metrics Registry
    registry = PrometheusMetricsRegistry()
    registry.record_request("GET", "/api/plants", 200, 0.0124)
    registry.record_request("POST", "/api/camera/upload", 202, 0.0452)
    
    # Add dummy plant to db for gauge test
    p = Plant(name="Metric Plant", species="Epipremnum aureum")
    db.add(p)
    db.commit()
    
    exposition = registry.generate_exposition(db)
    assert "# TYPE florabot_http_requests_total counter" in exposition
    assert 'florabot_http_requests_total{method="GET",endpoint="/api/plants",status="200"} 1' in exposition
    assert "florabot_plants_total" in exposition
    print("  -> Passed structured JSON log formatting and Prometheus metrics exposition.")

# ============================================================================
# 7. DATABASE BACKUP & RECOVERY DRILL
# ============================================================================

def test_database_backup_and_recovery():
    print("[7/9] Testing Live Online SQLite Backup, Checksum & Disaster Recovery...")
    test_src_db = backend_dir / "data" / "drill_source.db"
    backup_dir = backend_dir / "data" / "drill_backups"
    restore_target = backend_dir / "data" / "drill_restored.db"
    
    for f in [test_src_db, restore_target]:
        if f.exists():
            f.unlink()
    
    # Create sample sqlite source db
    conn = sqlite3.connect(str(test_src_db))
    c = conn.cursor()
    c.execute("CREATE TABLE plants (id INTEGER PRIMARY KEY, name TEXT);")
    c.execute("INSERT INTO plants (name) VALUES ('Backup Test Monstera');")
    c.execute("INSERT INTO plants (name) VALUES ('Backup Test Pothos');")
    conn.commit()
    conn.close()
    
    # Perform backup
    backup_archive = create_backup(test_src_db, backup_dir)
    assert backup_archive.exists()
    assert backup_archive.name.endswith(".db.gz")
    
    # Verify sha256 manifest file
    checksum_file = backup_archive.with_name(f"{backup_archive.name}.sha256")
    assert checksum_file.exists()
    expected_hash = checksum_file.read_text(encoding="utf-8").strip().split()[0]
    actual_hash = calculate_sha256(backup_archive)
    assert expected_hash == actual_hash, "Checksum manifest must match archive sha256"
    
    # Perform recovery drill
    success = restore_backup(backup_archive, restore_target)
    assert success is True
    assert restore_target.exists()
    
    # Verify data in restored database
    r_conn = sqlite3.connect(str(restore_target))
    r_cur = r_conn.cursor()
    r_cur.execute("SELECT name FROM plants ORDER BY id;")
    rows = r_cur.fetchall()
    r_conn.close()
    
    assert len(rows) == 2
    assert rows[0][0] == "Backup Test Monstera"
    assert rows[1][0] == "Backup Test Pothos"
    print(f"  -> Passed backup generation ({backup_archive.name}), checksum verification, and restore recovery drill.")

# ============================================================================
# 8. POSTGRESQL MIGRATION SCHEMA ORDERING
# ============================================================================

def test_postgres_migration_ordering():
    print("[8/9] Testing PostgreSQL Migration Schema & Dependency Ordering...")
    # Check that foreign key dependents come strictly after their parents
    assert TABLE_MIGRATION_ORDER.index("plants") < TABLE_MIGRATION_ORDER.index("analyses")
    assert TABLE_MIGRATION_ORDER.index("devices") < TABLE_MIGRATION_ORDER.index("analyses")
    assert TABLE_MIGRATION_ORDER.index("analyses") < TABLE_MIGRATION_ORDER.index("reports")
    assert TABLE_MIGRATION_ORDER.index("conversations") < TABLE_MIGRATION_ORDER.index("chat_messages")
    assert "users" in TABLE_MIGRATION_ORDER
    assert "audit_logs" in TABLE_MIGRATION_ORDER
    print(f"  -> Passed PostgreSQL migration schema ordering for all {len(TABLE_MIGRATION_ORDER)} tables.")

# ============================================================================
# 9. PRODUCTION NGINX CONFIGURATION & SECURITY AUDIT
# ============================================================================

def test_nginx_security_configuration():
    print("[9/9] Testing Production Nginx Reverse Proxy Configuration & Security Directives...")
    nginx_conf_path = backend_dir.parent / "nginx" / "florabot.conf"
    assert nginx_conf_path.exists(), f"Nginx configuration {nginx_conf_path} not found"
    
    conf_text = nginx_conf_path.read_text(encoding="utf-8")
    
    # 1. Rate limiting directives
    assert "limit_req_zone" in conf_text, "Missing limit_req_zone directive"
    assert "florabot_api_limit" in conf_text
    assert "florabot_auth_limit" in conf_text
    
    # 2. Hardened TLS directives
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in conf_text, "Must enforce TLSv1.2 and TLSv1.3"
    assert "ssl_prefer_server_ciphers on;" in conf_text
    
    # 3. Security headers
    assert "Strict-Transport-Security" in conf_text, "Missing HSTS header"
    assert "X-Content-Type-Options \"nosniff\"" in conf_text, "Missing nosniff header"
    assert "X-Frame-Options \"SAMEORIGIN\"" in conf_text, "Missing X-Frame-Options header"
    assert "Content-Security-Policy" in conf_text, "Missing Content-Security-Policy"
    
    # 4. Proxy buffering off for camera streaming
    assert "proxy_buffering off;" in conf_text, "Streaming endpoint must disable proxy buffering"
    assert "client_max_body_size 20M;" in conf_text, "Must configure max body size"
    print("  -> Passed Nginx reverse proxy configuration audit: TLS 1.2/1.3, HSTS, CSP, rate limits, and unbuffered streaming.")

# ============================================================================
# MAIN RUNNER
# ============================================================================

def main():
    print("\n========================================================")
    print("  FLORABOT PHASE 9 TEST SUITE (SECURITY & PRODUCTION)")
    print("========================================================\n")
    db = get_test_db()
    try:
        test_password_hashing()
        test_jwt_token_lifecycle()
        test_user_auth_and_audit(db)
        test_rbac_and_device_auth(db)
        test_sliding_window_rate_limiting()
        test_monitoring_and_metrics(db)
        test_database_backup_and_recovery()
        test_postgres_migration_ordering()
        test_nginx_security_configuration()
        print("\n========================================================")
        print("  ALL PHASE 9 TESTS COMPLETED AND VERIFIED SUCCESSFULLY!")
        print("========================================================\n")
    finally:
        db.close()

if __name__ == "__main__":
    main()

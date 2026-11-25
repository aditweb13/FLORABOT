"""
FloraBOT Authentication and Authorization Module:
Provides enterprise-grade, dependency-free security features:
1. Cryptographically salted password hashing (PBKDF2-HMAC-SHA256, 100,000 iterations).
2. RFC 7519 standard JSON Web Token (JWT) minting, verification, and expiration handling (HS256).
3. Role-Based Access Control (RBAC) supporting 'admin', 'operator', and 'viewer' roles.
4. IoT Device API Key authentication (X-API-Key header) for ESP32-CAM and telemetry push.
5. FastAPI OAuth2 Password Bearer dependency integration.
"""

import hmac
import hashlib
import secrets
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User, AuditLog

security_scheme = HTTPBearer(auto_error=False)

# ============================================================================
# 1. PASSWORD HASHING (PBKDF2-HMAC-SHA256)
# ============================================================================

def hash_password(password: str) -> str:
    """Generate salted PBKDF2-HMAC-SHA256 password hash with 100,000 iterations."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password using constant-time comparison."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_hex = parts[3]
        computed_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(computed_key.hex(), expected_hex)
    except Exception:
        return False

# ============================================================================
# 2. JWT MINTING & VERIFICATION (HS256)
# ============================================================================

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def _base64url_decode(data_str: str) -> bytes:
    padding = b"=" * ((4 - len(data_str) % 4) % 4)
    return base64.urlsafe_b64decode(data_str.encode("utf-8") + padding)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create signed HS256 JSON Web Token."""
    to_encode = data.copy()
    now_ts = int(time.time())
    if expires_delta:
        exp_ts = now_ts + int(expires_delta.total_seconds())
    else:
        exp_ts = now_ts + int(settings.jwt_expiration_minutes * 60)
    
    to_encode.update({"iat": now_ts, "exp": exp_ts})
    
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_json = json.dumps(to_encode, separators=(",", ":")).encode("utf-8")
    
    header_b64 = _base64url_encode(header_json)
    payload_b64 = _base64url_encode(payload_json)
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    
    signature = hmac.new(settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_access_token(token: str) -> Dict[str, Any]:
    """Verify and decode an HS256 JWT, enforcing expiration."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token structure")
        
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        
        expected_sig = hmac.new(settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _base64url_decode(sig_b64)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signature verification failed")
        
        payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        exp_ts = payload.get("exp")
        if exp_ts and int(time.time()) > exp_ts:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
        
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token decode error: {str(e)}")

def generate_api_key() -> str:
    """Generate cryptographically strong API key for IoT devices or services."""
    return f"fb_live_{secrets.token_hex(24)}"

# ============================================================================
# 3. FASTAPI DEPENDENCY INJECTION & RBAC
# ============================================================================

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Retrieve authenticated user from JWT Bearer token."""
    if not credentials:
        if not settings.enable_auth:
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    payload = decode_access_token(token)
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token payload missing subject")
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account")
    
    return user

def require_role(required_roles: list[str]):
    """Enforce Role-Based Access Control (e.g. ['admin'], ['admin', 'operator'])."""
    def role_checker(user: Optional[User] = Depends(get_current_user)) -> Optional[User]:
        if not settings.enable_auth:
            return user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        if user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: required role in {required_roles}, current role is '{user.role}'"
            )
        return user
    return role_checker

def verify_device_api_key(request: Request) -> bool:
    """Verify IoT device API key from X-API-Key header or query parameter."""
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not api_key:
        return False
    return hmac.compare_digest(api_key, settings.device_api_key)

def log_audit_event(db: Session, actor: str, action: str, resource: str, details: dict, ip_address: str = ""):
    """Record an audit trail event for security compliance."""
    try:
        audit = AuditLog(
            actor_username=actor,
            action=action,
            resource=resource,
            details_json=json.dumps(details),
            ip_address=ip_address
        )
        db.add(audit)
        db.commit()
    except Exception:
        db.rollback()

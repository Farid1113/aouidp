"""Opaque, DB-backed sessions. HttpOnly cookies; CSRF for state changes."""
import hashlib
import secrets
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from argon2 import PasswordHasher, exceptions
from app.core.db import get_db
from app.core.config import get_settings
from app.models.tables import AuthSession, Admin, User, Role

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_COOKIE = 'ds_session'
_attempts: dict[str, deque[float]] = defaultdict(deque)

def password_hash(value: str) -> str: return hasher.hash(value)

def password_verify(stored: str, candidate: str) -> bool:
    try:
        return hasher.verify(stored, candidate)
    except (exceptions.VerificationError, exceptions.InvalidHashError):
        return False

def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def throttle(name: str, limit: int = 8, window: int = 300):
    now = time.monotonic()
    data = _attempts[name]
    while data and data[0] < now - window: data.popleft()
    if len(data) >= limit:
        raise HTTPException(429, 'Too many attempts. Retry later.')
    data.append(now)

def make_session(db: Session, response: Response, admin_id: int | None = None, user_id: int | None = None):
    raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=get_settings().session_days)
    db.add(AuthSession(token_hash=token_digest(raw), csrf_token=csrf, admin_id=admin_id,
                       user_id=user_id, expires_at=expires))
    db.commit()
    response.set_cookie(SESSION_COOKIE, raw, max_age=get_settings().session_days*86400,
                        httponly=True, secure=get_settings().cookie_secure,
                        samesite='lax', path='/')
    return csrf

def session_or_401(request: Request, db: Session):
    raw = request.cookies.get(SESSION_COOKIE, '')
    if not raw: raise HTTPException(401, 'Login required')
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, 'Session expired')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        provided = request.headers.get('x-csrf-token', '')
        if not secrets.compare_digest(provided, session.csrf_token):
            raise HTTPException(403, 'Invalid CSRF token')
    return session

def admin_required(request: Request, db: Session = Depends(get_db)) -> Admin:
    session = session_or_401(request, db)
    if not session.admin_id: raise HTTPException(403, 'Admin account required')
    admin = db.get(Admin, session.admin_id)
    if not admin or not admin.active: raise HTTPException(403, 'Admin account disabled')
    return admin

def customer_required(request: Request, db: Session = Depends(get_db)) -> User:
    session = session_or_401(request, db)
    if not session.user_id: raise HTTPException(403, 'Customer account required')
    customer = db.get(User, session.user_id)
    if not customer or not customer.active: raise HTTPException(403, 'Customer account disabled')
    return customer

def manager_required(admin: Admin = Depends(admin_required), db: Session = Depends(get_db)) -> Admin:
    role = db.get(Role, admin.role_id)
    if role.name not in ('super_admin', 'manager'):
        raise HTTPException(403, 'Manager permission required')
    return admin

def super_required(admin: Admin = Depends(admin_required), db: Session = Depends(get_db)) -> Admin:
    if db.get(Role, admin.role_id).name != 'super_admin':
        raise HTTPException(403, 'Super admin permission required')
    return admin

def clear_session(request: Request, response: Response, db: Session):
    raw = request.cookies.get(SESSION_COOKIE, '')
    if raw:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
        if session: db.delete(session); db.commit()
    response.delete_cookie(SESSION_COOKIE, path='/', secure=get_settings().cookie_secure, samesite='lax')

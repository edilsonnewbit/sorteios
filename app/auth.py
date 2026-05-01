"""Auth utilities: password hashing, session tokens, guards."""
import bcrypt
import json
import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request
from fastapi.responses import RedirectResponse

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-CHANGE-IN-PRODUCTION-abc123xyz")
SESSION_COOKIE = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days
_signer = URLSafeTimedSerializer(SECRET_KEY, salt="user-session-v1")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session_token(user_id: int, role: str, name: str) -> str:
    payload = json.dumps({"id": user_id, "role": role, "name": name}, ensure_ascii=False)
    return _signer.dumps(payload)


def decode_session_token(token: str) -> dict | None:
    try:
        payload = _signer.loads(token, max_age=SESSION_MAX_AGE)
        return json.loads(payload)
    except (BadSignature, SignatureExpired, Exception):
        return None


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return decode_session_token(token)


def admin_guard(request: Request):
    """Returns user dict if admin, else returns RedirectResponse to /login."""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        return None
    return user


def organizer_guard(request: Request):
    """Returns user dict if approved organizer or admin, else None."""
    user = get_current_user(request)
    if not user or user.get("role") not in ("admin", "organizer"):
        return None
    return user


def set_session_cookie(response, user_id: int, role: str, name: str):
    token = create_session_token(user_id, role, name)
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax",
        max_age=SESSION_MAX_AGE, secure=False,  # set True in prod with HTTPS
    )


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE)

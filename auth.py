"""User accounts: sign-up, sign-in, sessions, and the request dependency.

Passwords are hashed with scrypt from the standard library (no extra service and
no extra dependency). Sessions are opaque random tokens; only a SHA-256 hash of
the token is stored, so a database leak does not hand over live sessions.
"""
import asyncio
import hashlib
import hmac
import os
import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from monitor import db
from ratelimit import limiter

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "30"))

# scrypt parameters (interactive login cost, well under a second).
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split(":")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bearer_token(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: resolve the Authorization bearer token to an account."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    user = await asyncio.to_thread(db.user_for_session, _hash_token(token))
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    return user


def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(user_id, _hash_token(token), SESSION_DAYS)
    return token


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


@router.post("/register", status_code=201)
@limiter.limit("10/minute")
async def register(request: Request, body: RegisterRequest):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    password_hash = await asyncio.to_thread(hash_password, body.password)
    try:
        user = await asyncio.to_thread(
            db.create_user, email, body.name.strip() if body.name else None, password_hash)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    token = await asyncio.to_thread(_new_session, user["id"])
    return {"token": token, "user": user}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    account = await asyncio.to_thread(db.get_user_by_email, body.email)
    ok = account is not None and await asyncio.to_thread(
        verify_password, body.password, account["password_hash"])
    if not ok:
        raise HTTPException(status_code=401, detail="That email and password do not match.")
    token = await asyncio.to_thread(_new_session, account["id"])
    return {"token": token, "user": {k: v for k, v in account.items() if k != "password_hash"}}


@router.post("/logout")
@limiter.limit("30/minute")
async def logout(request: Request, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    if token:
        await asyncio.to_thread(db.delete_session, _hash_token(token))
    return {"status": "ok"}


@router.get("/me")
@limiter.limit("60/minute")
async def me(request: Request, user: dict = Depends(get_current_user)):
    return {"user": user}

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
AUTH_TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", "3600"))

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must not be empty.")
if len(AUTH_SECRET) < 32 or AUTH_SECRET == "replace-with-a-long-random-secret":
    raise RuntimeError("Set AUTH_SECRET to a random secret of at least 32 characters.")
if AUTH_TOKEN_TTL < 1:
    raise RuntimeError("AUTH_TOKEN_TTL must be a positive number of seconds.")

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(credentials: LoginRequest):
    username_valid = secrets.compare_digest(credentials.username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8"))
    password_valid = secrets.compare_digest(credentials.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))
    if not (username_valid and password_valid):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": ADMIN_USERNAME,
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(seconds=AUTH_TOKEN_TTL),
        },
        AUTH_SECRET,
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "admin": {"username": ADMIN_USERNAME, "role": "admin"},
    }


@router.get("/me")
def current_admin(request: Request):
    return request.state.admin


def decode_access_token(token: str):
    try:
        claims = jwt.decode(
            token,
            AUTH_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "role"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.") from exc

    if claims["sub"] != ADMIN_USERNAME or claims["role"] != "admin":
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    return {"username": claims["sub"], "role": claims["role"]}

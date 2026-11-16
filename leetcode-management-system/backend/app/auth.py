import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, func, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import engine

load_dotenv()

DEVELOPER_AUTH_TABLE = "developer_auth_accounts"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
AUTH_TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", "3600"))
PASSWORD_HASH_ITERATIONS = 600_000

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must not be empty.")
if len(AUTH_SECRET) < 32 or AUTH_SECRET == "replace-with-a-long-random-secret":
    raise RuntimeError("Set AUTH_SECRET to a random secret of at least 32 characters.")
if AUTH_TOKEN_TTL < 1:
    raise RuntimeError("AUTH_TOKEN_TTL must be a positive number of seconds.")

router = APIRouter(prefix="/api/auth", tags=["authentication"])
developer_router = APIRouter(prefix="/api/developer", tags=["developer"])
auth_metadata = MetaData()
developer_accounts = Table(
    DEVELOPER_AUTH_TABLE,
    auth_metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(254), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class LoginRequest(BaseModel):
    username: str = Field(max_length=254)
    password: str


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        username = value.strip().lower()
        is_email = "@" in username and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username)
        if is_email:
            return username
        if not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
            raise ValueError("Enter a valid email or a 3-80 character username.")
        return username


def create_access_token(username, role):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": username,
            "role": role,
            "iat": now,
            "exp": now + timedelta(seconds=AUTH_TOKEN_TTL),
        },
        AUTH_SECRET,
        algorithm="HS256",
    )


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, encoded_hash):
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 1_000_000:
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def developer_accounts_unavailable(exc):
    raise HTTPException(
        status_code=503,
        detail="Developer accounts are not initialized. Apply the developer-account database migration.",
    ) from exc


def account_identity(username, role):
    return {"username": username, "role": role}


@router.post("/login")
def login(credentials: LoginRequest):
    username_valid = secrets.compare_digest(credentials.username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8"))
    if username_valid:
        password_valid = secrets.compare_digest(credentials.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))
        if not password_valid:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        username, role = ADMIN_USERNAME, "admin"
    else:
        try:
            with engine.connect() as conn:
                account = conn.execute(
                    select(developer_accounts.c.username, developer_accounts.c.password_hash).where(
                        developer_accounts.c.username == credentials.username.strip().lower()
                    )
                ).mappings().first()
        except SQLAlchemyError as exc:
            developer_accounts_unavailable(exc)
        if account is None or not verify_password(credentials.password, account["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        username, role = account["username"], "developer"

    identity = account_identity(username, role)
    result = {
        "access_token": create_access_token(username, role),
        "token_type": "bearer",
        "user": identity,
    }
    if role == "admin":
        result["admin"] = identity
    return result


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(credentials: SignupRequest):
    username = credentials.username
    if hmac.compare_digest(username.casefold().encode("utf-8"), ADMIN_USERNAME.casefold().encode("utf-8")):
        raise HTTPException(status_code=409, detail="This username is reserved.")

    try:
        with engine.begin() as conn:
            conn.execute(insert(developer_accounts).values(
                username=username,
                password_hash=password_hash(credentials.password),
            ))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username is already registered.") from exc
    except SQLAlchemyError as exc:
        developer_accounts_unavailable(exc)

    return {"message": "Developer account created.", "developer": account_identity(username, "developer")}


@router.get("/me")
def current_user(request: Request):
    return request.state.current_user


@developer_router.get("/me")
def current_developer(request: Request):
    username = request.state.current_user["username"]
    try:
        with engine.connect() as conn:
            account = conn.execute(
                select(developer_accounts.c.username, developer_accounts.c.created_at).where(
                    developer_accounts.c.username == username
                )
            ).mappings().first()
    except SQLAlchemyError as exc:
        developer_accounts_unavailable(exc)
    if account is None:
        raise HTTPException(status_code=404, detail="Developer account not found.")
    created_at = account["created_at"]
    return {
        "username": account["username"],
        "role": "developer",
        "created_at": created_at.isoformat() if created_at else None,
    }


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

    username = claims["sub"]
    role = claims["role"]
    if not isinstance(username, str) or role not in {"admin", "developer"}:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    if role == "admin" and username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    if role == "developer" and username.casefold() == ADMIN_USERNAME.casefold():
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    return account_identity(username, role)

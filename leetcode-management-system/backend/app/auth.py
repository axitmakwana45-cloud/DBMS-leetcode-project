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
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, func, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import engine

load_dotenv()

DEVELOPER_AUTH_TABLE = "developer_auth_accounts"
COMPANY_AUTH_TABLE = "company_auth_accounts"
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
companies = Table("company", auth_metadata, Column("company_id", Integer, primary_key=True))
company_accounts = Table(
    COMPANY_AUTH_TABLE,
    auth_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("company_id", Integer, ForeignKey("company.company_id", ondelete="CASCADE"), nullable=False, unique=True),
)
developer_accounts = Table(
    DEVELOPER_AUTH_TABLE,
    auth_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("username", String(254), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("developer_id", Integer, ForeignKey("developer.developer_id", ondelete="CASCADE"), nullable=False, unique=True),
)
developers = Table(
    "developer",
    auth_metadata,
    Column("developer_id", Integer, primary_key=True),
    Column("username", String(40), nullable=False, unique=True),
    Column("full_name", String(100), nullable=False),
    Column("email", String(254), unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("country", String(60), nullable=False),
    Column("rating", Integer, nullable=False, server_default="1500"),
    Column("joined_on", Date, nullable=False),
)


class LoginRequest(BaseModel):
    username: str = Field(max_length=254)
    password: str


class CompanySignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    company_name: str = Field(min_length=2, max_length=120)
    industry: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_company_email(cls, value):
        username = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username):
            raise ValueError("Enter a valid company email address.")
        return username

    @field_validator("company_name", "industry")
    @classmethod
    def trim_company_fields(cls, value):
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be empty.")
        return normalized


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        username = value.strip().lower()
        is_email = "@" in username and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", username)
        if is_email:
            return username
        raise ValueError("Enter a valid email address.")

    @field_validator("full_name", "country")
    @classmethod
    def trim_required_profile_fields(cls, value):
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field cannot be empty.")
        return normalized


def create_access_token(username, role, developer_id=None, company_id=None):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=AUTH_TOKEN_TTL),
    }
    if developer_id is not None:
        claims["developer_id"] = developer_id
    if company_id is not None:
        claims["company_id"] = company_id
    return jwt.encode(claims, AUTH_SECRET, algorithm="HS256")


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
    username = credentials.username.strip()
    if secrets.compare_digest(username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8")):
        if not secrets.compare_digest(credentials.password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        role, developer_id, company_id = "admin", None, None
    else:
        normalized = username.lower()
        try:
            with engine.connect() as conn:
                developer = conn.execute(
                    select(developer_accounts.c.username, developer_accounts.c.password_hash, developer_accounts.c.developer_id)
                    .where(developer_accounts.c.username == normalized)
                ).mappings().first()
                if developer and verify_password(credentials.password, developer["password_hash"]):
                    username, role, developer_id, company_id = developer["username"], "developer", developer["developer_id"], None
                else:
                    company = conn.execute(
                        select(company_accounts.c.email, company_accounts.c.password_hash, company_accounts.c.company_id)
                        .where(company_accounts.c.email == normalized)
                    ).mappings().first()
                    if not company or not verify_password(credentials.password, company["password_hash"]):
                        raise HTTPException(status_code=401, detail="Invalid username or password.")
                    username, role, developer_id, company_id = company["email"], "company", None, company["company_id"]
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Account tables are not initialized. Apply the required database migrations.") from exc

    identity = account_identity(username, role)
    if role == "company":
        identity["company_id"] = company_id
    result = {
        "access_token": create_access_token(username, role, developer_id, company_id),
        "token_type": "bearer",
        "user": identity,
    }
    if role == "admin":
        result["admin"] = identity
    return result




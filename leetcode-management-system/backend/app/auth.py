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
    website: str = Field(default="", max_length=255)
    location: str = Field(default="", max_length=160)
    country: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_company_email(cls, value):
        username = value.strip().lower()
        if not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", username):
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


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(credentials: SignupRequest):
    username = credentials.username
    if hmac.compare_digest(username.casefold().encode("utf-8"), ADMIN_USERNAME.casefold().encode("utf-8")):
        raise HTTPException(status_code=409, detail="This username is reserved.")

    try:
        with engine.begin() as conn:
            hashed_password = password_hash(credentials.password)
            base_username = re.sub(r"[^a-z0-9_.-]", "", username.split("@", 1)[0])[:30] or "developer"
            developer_username = f"{base_username}_{secrets.token_hex(4)}"
            developer_id = conn.execute(
                insert(developers).values(
                    username=developer_username,
                    full_name=credentials.full_name,
                    email=username,
                    password_hash=hashed_password,
                    country=credentials.country,
                    joined_on=datetime.now(timezone.utc).date(),
                ).returning(developers.c.developer_id)
            ).scalar_one()
            conn.execute(
                insert(developer_accounts).values(
                    username=username,
                    password_hash=hashed_password,
                    developer_id=developer_id,
                )
            )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username is already registered.") from exc
    except SQLAlchemyError as exc:
        developer_accounts_unavailable(exc)

    return {"message": "Developer account created.", "developer": account_identity(username, "developer")}


@router.post("/company-signup", status_code=status.HTTP_201_CREATED)
def company_signup(credentials: CompanySignupRequest):
    from .database import refresh_metadata

    try:
        company_table = refresh_metadata().tables.get("company")
        if company_table is None:
            raise HTTPException(status_code=503, detail="The existing company table was not found.")
        company_id_col = next((company_table.c[name] for name in ("company_id", "id") if name in company_table.c), None)
        if company_id_col is None:
            raise HTTPException(status_code=503, detail="The company table needs a company_id primary key.")
        values = {}
        for candidates, value in [
            (("name", "company_name"), credentials.company_name),
            (("industry", "sector", "company_type"), credentials.industry),
            (("email", "contact_email"), credentials.email),
            (("website", "website_url"), credentials.website or None),
            (("location", "headquarters", "city"), credentials.location or None),
        ]:
            target = next((company_table.c[name] for name in candidates if name in company_table.c), None)
            if target is not None:
                values[target.name] = value

        # Resolve Country explicitly from the reflected company table. This keeps
        # the required profile field mapped even if SQLAlchemy column keys differ
        # from their displayed database column names.
        country_column = next(
            (
                column
                for column in company_table.columns
                if column.name.strip().casefold() == "country"
                or str(column.key).strip().casefold() == "country"
            ),
            None,
        )
        if country_column is not None:
            values[country_column.name] = credentials.country.strip()

        missing = [column.name for column in company_table.columns if not column.nullable and column.default is None and column.server_default is None and not column.primary_key and column.name not in values]
        if missing:
            raise HTTPException(status_code=422, detail=f"Company profile needs additional required fields: {missing}")
        with engine.begin() as conn:
            company_id = conn.execute(insert(company_table).values(**values).returning(company_id_col)).scalar_one()
            conn.execute(insert(company_accounts).values(
                email=credentials.email,
                password_hash=password_hash(credentials.password),
                company_id=company_id,
            ))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A company account with this email or company identity already exists.") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Company account setup failed. Check the company table schema and apply migration 006.") from exc
    return {"message": "Company account created. You can now sign in.", "company": {"email": credentials.email, "role": "company", "company_id": company_id}}


@router.get("/me")
def current_user(request: Request):
    return request.state.current_user


@developer_router.get("/me")
def current_developer(request: Request):
    username = request.state.current_user["username"]
    try:
        with engine.connect() as conn:
            account = conn.execute(
                select(
                    developer_accounts.c.username,
                    developer_accounts.c.created_at,
                    developers.c.developer_id,
                    developers.c.full_name,
                    developers.c.email,
                    developers.c.country,
                    developers.c.rating,
                    developers.c.joined_on,
                ).select_from(
                    developer_accounts.join(
                        developers,
                        developer_accounts.c.developer_id == developers.c.developer_id,
                    )
                ).where(
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
        "developer_id": account["developer_id"],
        "full_name": account["full_name"],
        "email": account["email"],
        "country": account["country"],
        "rating": account["rating"],
        "joined_on": account["joined_on"].isoformat() if account["joined_on"] else None,
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
    if not isinstance(username, str) or role not in {"admin", "developer", "company"}:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    if role == "admin" and username != ADMIN_USERNAME:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    developer_id = claims.get("developer_id")
    if role == "company":
        company_id = claims.get("company_id")
        if not isinstance(company_id, int) or company_id < 1:
            raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    if role == "developer" and (
        username.casefold() == ADMIN_USERNAME.casefold()
        or not isinstance(developer_id, int)
        or developer_id < 1
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    identity = account_identity(username, role)
    if developer_id is not None:
        identity["developer_id"] = developer_id
    if role == "company":
        identity["company_id"] = claims["company_id"]
    return identity

import json
import os
import re
from urllib.parse import unquote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import case, delete, func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from .auth import (
    DEVELOPER_AUTH_TABLE,
    COMPANY_AUTH_TABLE,
    decode_access_token,
    developer_router,
    router as auth_router,
)
from .database import engine, refresh_metadata
from .user_api import router as user_platform_router
from .company_api import router as company_portal_router
from .utils import row_dict

load_dotenv()
app = FastAPI(title="LeetCode Management System API", version="1.0.0")

DEFAULT_TABLES = [
    "developer",
    "company",
    "administrator",
    "programming_problem",
    "tag",
    "test_case",
    "programming_language",
    "language_family",
    "submission",
    "contest",
    "contest_problem",
    "contest_participant",
    "leaderboard",
    "badge",
    "developer_badge",
    "discussion",
    "editorial",
    "report",
    "notification",
    "assessment",
    "assessment_problem",
    "assessment_language",
    "collection",
    "assessment_participation",
    "solves",
    "targets",
    "problem_tag",
    "records_performance",
]

origins = list(dict.fromkeys([
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *[x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()],
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_API_PATHS = {"/api/health", "/api/auth/login", "/api/auth/signup", "/api/auth/company-signup"}


@app.middleware("http")
async def require_admin_authentication(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in PUBLIC_API_PATHS:
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})

    try:
        current_user = decode_access_token(token.strip())
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    request.state.current_user = current_user
    if path == "/api/auth/me":
        return await call_next(request)
    if path.startswith("/api/company/"):
        if current_user["role"] != "company":
            return JSONResponse(status_code=403, content={"detail": "Company access required."})
        return await call_next(request)
    developer_paths = (
        "/api/developer/",
        "/api/user/",
        "/api/problems",
        "/api/submissions",
        "/api/languages",
        "/api/leaderboard",
        "/api/contests",
    )
    if path.startswith(developer_paths):
        if current_user["role"] != "developer":
            return JSONResponse(status_code=403, content={"detail": "Developer access required."})
        return await call_next(request)
    if current_user["role"] != "admin":
        return JSONResponse(status_code=403, content={"detail": "Administrator access required."})
    return await call_next(request)


app.include_router(auth_router)
app.include_router(developer_router)
app.include_router(user_platform_router)
app.include_router(company_portal_router)


def normalize_name(name):
    value = str(name or "").strip().lower()
    return re.sub(r"[^a-z0-9_]+", "_", value).strip("_")


def configured_names(raw_value, fallback):
    items = [item.strip() for item in (raw_value or "").split(",") if item.strip()]
    if not items:
        items = fallback
    return {normalize_name(item) for item in items}


CRUD_TABLES = configured_names(os.getenv("CRUD_TABLES"), DEFAULT_TABLES)
def get_tables():
    try:
        tables = refresh_metadata().tables
        return {name: table for name, table in tables.items() if name not in {DEVELOPER_AUTH_TABLE, COMPANY_AUTH_TABLE}}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database metadata error: {exc}")


def resolve_table_name(name: str):
    if not name:
        raise HTTPException(status_code=400, detail="Table name is required.")
    tables = get_tables()
    raw_name = str(name).strip()
    if raw_name in tables:
        return raw_name
    lookup = {normalize_name(table_name): table_name for table_name in tables.keys()}
    key = normalize_name(raw_name)
    if key in lookup:
        return lookup[key]
    raise HTTPException(status_code=404, detail=f"Table '{raw_name}' was not found in the connected database.")


def get_table(name: str, require_crud: bool = False):
    tables = get_tables()
    actual_name = resolve_table_name(name)
    if actual_name not in tables:
        raise HTTPException(status_code=404, detail=f"Table '{actual_name}' was not found in the connected database.")
    normalized = normalize_name(actual_name)
    if require_crud and normalized not in CRUD_TABLES:
        raise HTTPException(status_code=403, detail=f"Write access to table '{actual_name}' is disabled in CRUD_TABLES.")
    return tables[actual_name]


def pk_columns(table):
    return list(table.primary_key.columns)


def parse_key(table, raw):
    try:
        data = json.loads(unquote(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid primary key JSON.")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Primary key must be a JSON object.")
    pks = pk_columns(table)
    if not pks:
        raise HTTPException(status_code=400, detail="This table has no declared primary key; safe update/delete is disabled.")
    if any(c.name not in data for c in pks):
        raise HTTPException(status_code=400, detail=f"Primary key fields required: {[c.name for c in pks]}")
    return {c.name: data[c.name] for c in pks}


def pk_where(table, values):
    return [table.c[name] == value for name, value in values.items()]


def find_col(table, candidates):
    lower = {c.name.lower(): c for c in table.columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


@app.get("/api/tables")
def list_tables():
    tables = get_tables()
    result = []
    for name in sorted(tables.keys()):
        table = tables[name]
        result.append({
            "name": name,
            "exists": True,
            "columns": [{
                "name": c.name,
                "type": str(c.type),
                "nullable": c.nullable,
                "primary_key": c.primary_key,
                "default": str(c.default.arg) if c.default and c.default.is_scalar else None,
            } for c in table.columns],
            "primary_key": [c.name for c in pk_columns(table)],
            "editable": normalize_name(name) in CRUD_TABLES,
        })
    return result


@app.get("/api/data/{table_name}")
def read_rows(table_name: str, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    table = get_table(table_name)
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(table)).scalar_one()
        stmt = select(table)
        primary_keys = pk_columns(table)
        if primary_keys:
            stmt = stmt.order_by(*primary_keys)
        stmt = stmt.offset(skip).limit(limit)
        rows = conn.execute(stmt).mappings().all()
    return {
        "items": [row_dict(r) for r in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
        "primary_key": [c.name for c in pk_columns(table)],
    }


@app.post("/api/data/{table_name}")
def create_row(table_name: str, payload: dict):
    table = get_table(table_name, require_crud=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Request body cannot be empty.")
    unknown = set(payload) - set(table.c.keys())
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown columns: {sorted(unknown)}")
    try:
        with engine.begin() as conn:
            result = conn.execute(insert(table).values(**payload))
            inserted = {}
            if result.inserted_primary_key:
                inserted = {c.name: v for c, v in zip(pk_columns(table), result.inserted_primary_key)}
        return {"message": "Record created", "primary_key": inserted}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc.orig if getattr(exc, "orig", None) else exc))


@app.put("/api/data/{table_name}/{key}")
def update_row(table_name: str, key: str, payload: dict):
    table = get_table(table_name, require_crud=True)
    if not pk_columns(table):
        raise HTTPException(status_code=400, detail="Table has no primary key.")
    values = parse_key(table, key)
    if not payload:
        raise HTTPException(status_code=400, detail="Request body cannot be empty.")
    unknown = set(payload) - set(table.c.keys())
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown columns: {sorted(unknown)}")
    if set(payload) & set(values):
        raise HTTPException(status_code=400, detail="Primary key fields cannot be changed.")
    try:
        with engine.begin() as conn:
            result = conn.execute(update(table).where(*pk_where(table, values)).values(**payload))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found.")
        return {"message": "Record updated"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc.orig if getattr(exc, "orig", None) else exc))


@app.delete("/api/data/{table_name}/{key}")
def delete_row(table_name: str, key: str):
    table = get_table(table_name, require_crud=True)
    values = parse_key(table, key)
    try:
        with engine.begin() as conn:
            result = conn.execute(delete(table).where(*pk_where(table, values)))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found.")
        return {"message": "Record deleted"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=409, detail=str(exc.orig if getattr(exc, "orig", None) else exc))


@app.get("/api/analytics/overview")
def analytics_overview():
    tables = get_tables()
    counts = {}
    table_counts = []
    with engine.connect() as conn:
        for table_name, table in sorted(tables.items(), key=lambda item: normalize_name(item[0])):
            count = conn.execute(select(func.count()).select_from(table)).scalar_one()
            normalized = normalize_name(table_name)
            counts[normalized] = count
            table_counts.append({
                "name": table_name,
                "normalized_name": normalized,
                "count": count,
                "editable": normalized in CRUD_TABLES,
            })

        submission_table = next(
            (table for name, table in tables.items() if normalize_name(name) == "submission"),
            None,
        )
        if submission_table is not None:
            status_col = find_col(submission_table, ["status", "submission_status", "result", "verdict"])
            if status_col is not None:
                counts["accepted_submissions"] = conn.execute(
                    select(func.count())
                    .select_from(submission_table)
                    .where(status_col.ilike("accepted%"))
                ).scalar_one()
                counts["rejected_submissions"] = conn.execute(
                    select(func.count())
                    .select_from(submission_table)
                    .where(status_col.ilike("rejected%"))
                ).scalar_one()
    counts["tables"] = table_counts
    return counts


@app.get("/api/analytics/distributions")
def analytics_distributions():
    tables = get_tables()
    preferred_columns = re.compile(
        r"(difficulty|status|role|country|industry|type|language|category|is_read|is_hidden|reason)$",
        re.IGNORECASE,
    )
    sensitive_columns = re.compile(r"(password|email|code|content|description|message|url)", re.IGNORECASE)
    distributions = []

    with engine.connect() as conn:
        for table_name, table in sorted(tables.items(), key=lambda item: normalize_name(item[0])):
            table_distributions = []
            candidates = [
                column for column in table.columns
                if preferred_columns.search(column.name) and not sensitive_columns.search(column.name)
            ][:3]
            for column in candidates:
                rows = conn.execute(
                    select(column.label("label"), func.count().label("count"))
                    .group_by(column)
                    .order_by(func.count().desc())
                    .limit(12)
                ).all()
                if rows:
                    table_distributions.append({
                        "column": column.name,
                        "items": [
                            {"label": str(row.label) if row.label is not None else "NULL", "count": row.count}
                            for row in rows
                        ],
                    })
            if table_distributions:
                distributions.append({"table": table_name, "breakdowns": table_distributions})

    return {"distributions": distributions}


@app.get("/api/analytics/dashboard")
def analytics_dashboard(
    date_from: str | None = None,
    date_to: str | None = None,
    country: str | None = None,
    difficulty: str | None = None,
    language_id: int | None = Query(None, ge=1),
):
    tables = get_tables()
    normalized_tables = {normalize_name(name): table for name, table in tables.items()}

    def table_for(name):
        return normalized_tables.get(name)

    def column(table, *names):
        return find_col(table, names) if table is not None else None

    def in_date_range(column_ref):
        if column_ref is None:
            return []
        conditions = []
        if date_from:
            conditions.append(column_ref >= date_from)
        if date_to:
            conditions.append(column_ref < date_to)
        return conditions

    def count_rows(conn, table, conditions=()):
        if table is None:
            return 0
        statement = select(func.count()).select_from(table)
        if conditions:
            statement = statement.where(*conditions)
        return conn.execute(statement).scalar_one()

    def grouped(conn, table, group_column, conditions=(), value_column=None, aggregate="count", limit=12):
        if table is None or group_column is None:
            return []
        if aggregate != "count" and value_column is None:
            return []
        metric = func.count() if aggregate == "count" else func.avg(value_column)
        statement = (
            select(group_column.label("label"), metric.label("value"))
            .select_from(table)
            .group_by(group_column)
            .order_by(metric.desc() if aggregate == "count" else metric.asc())
            .limit(limit)
        )
        if conditions:
            statement = statement.where(*conditions)
        return [
            {
                "label": str(row.label) if row.label is not None else "NULL",
                "value": round(float(row.value or 0), 2),
            }
            for row in conn.execute(statement).all()
        ]

    developer = table_for("developer")
    problem = table_for("programming_problem")
    submission = table_for("submission")
    contest = table_for("contest")
    report = table_for("report")
    solves = table_for("solves")
    company = table_for("company")
    programming_language = table_for("programming_language")
    tag = table_for("tag")
    problem_tag = table_for("problem_tag")
    participant = table_for("contest_participant")
    assessment = table_for("assessment")
    assessment_participation = table_for("assessment_participation")
    badge = table_for("badge")
    developer_badge = table_for("developer_badge")
    discussion = table_for("discussion")
    editorial = table_for("editorial")
    test_case = table_for("test_case")
    administrator = table_for("administrator")
    notification = table_for("notification")
    assessment_problem = table_for("assessment_problem")
    contest_problem = table_for("contest_problem")
    language_family = table_for("language_family")
    records_performance = table_for("records_performance")

    submission_status = column(submission, "status", "submission_status", "result", "verdict")
    submitted_at = column(submission, "submitted_at", "created_at", "submission_time")
    submission_language_id = column(submission, "language_id", "programming_language_id")
    developer_country = column(developer, "country")
    developer_rating = column(developer, "rating")
    developer_joined = column(developer, "joined_on", "created_at", "joined_at")
    problem_difficulty = column(problem, "difficulty", "level", "problem_difficulty")
    problem_acceptance = column(problem, "acceptance_rate", "success_rate")
    contest_status = column(contest, "status")
    report_status = column(report, "status")
    problem_table_link = column(discussion, "problem_id")
    discussion_upvotes = column(discussion, "upvotes", "votes")
    contest_id = column(participant, "contest_id")
    assessment_company_id = column(assessment, "company_id")
    assessment_id = column(assessment, "assessment_id")
    assessment_score = column(assessment_participation, "score", "marks")
    assessment_state = column(assessment_participation, "status")

    submission_filters = in_date_range(submitted_at)
    if language_id is not None and submission_language_id is not None:
        submission_filters.append(submission_language_id == language_id)
    problem_filters = [problem_difficulty == difficulty] if difficulty and problem_difficulty is not None else []
    developer_filters = [developer_country == country] if country and developer_country is not None else []
    developer_filters.extend(in_date_range(developer_joined))

    with engine.connect() as conn:
        total_developers = count_rows(conn, developer, developer_filters)
        total_problems = count_rows(conn, problem, problem_filters)
        total_submissions = count_rows(conn, submission, submission_filters)
        accepted_submissions = (
            count_rows(conn, submission, [*submission_filters, submission_status.ilike("accepted%")])
            if submission_status is not None else 0
        )
        active_contests = count_rows(
            conn, contest, [contest_status.ilike("running%")] if contest_status is not None else []
        )
        open_reports = count_rows(
            conn,
            report,
            [report_status.in_(["OPEN", "IN_REVIEW"])] if report_status is not None else [],
        )
        acceptance_rate = round(100 * accepted_submissions / total_submissions, 2) if total_submissions else 0

        charts = {
            "submission_status": grouped(conn, submission, submission_status, submission_filters),
            "daily_submissions": grouped(
                conn, submission, func.date(submitted_at) if submitted_at is not None else None, submission_filters, limit=30
            ),
            "problems_by_difficulty": grouped(conn, problem, problem_difficulty, problem_filters),
            "acceptance_by_difficulty": grouped(
                conn, problem, problem_difficulty, problem_filters, problem_acceptance, "average"
            ),
            "developer_country": grouped(conn, developer, developer_country, developer_filters),
            "developer_signups": grouped(
                conn, developer, func.date(developer_joined) if developer_joined is not None else None,
                developer_filters, limit=30,
            ),
            "admin_roles": grouped(conn, administrator, column(administrator, "role")),
            "language_versions": grouped(conn, programming_language, column(programming_language, "name")),
            "company_industry": grouped(conn, company, column(company, "industry")),
            "company_country": grouped(conn, company, column(company, "country")),
            "company_onboarding": grouped(
                conn, company,
                func.date(column(company, "created_at", "joined_on")) if column(company, "created_at", "joined_on") is not None else None,
                limit=30,
            ),
            "top_solvers": [],
            "solves_attempts": grouped(
                conn, solves, column(solves, "problem_id"),
                value_column=column(solves, "attempts"), aggregate="average",
            ),
            "solves_over_time": grouped(
                conn, solves,
                func.date(column(solves, "solved_on", "created_at")) if column(solves, "solved_on", "created_at") is not None else None,
                limit=30,
            ),
            "problems_per_tag": [],
            "contest_participants": [],
            "contest_problem_points": grouped(
                conn, contest_problem, column(contest_problem, "contest_id"),
                value_column=column(contest_problem, "points"), aggregate="average",
            ),
            "contest_status": grouped(conn, contest, contest_status),
            "contests_timeline": grouped(
                conn, contest,
                func.date(column(contest, "start_time", "created_at")) if column(contest, "start_time", "created_at") is not None else None,
                limit=30,
            ),
            "assessment_status": grouped(conn, assessment_participation, assessment_state),
            "assessment_avg_score": grouped(
                conn, assessment_participation, column(assessment_participation, "assessment_id"),
                value_column=assessment_score, aggregate="average",
            ),
            "language_popularity": [],
            "language_success_rate": [],
            "badge_popularity": [],
            "reports_status": grouped(conn, report, report_status),
            "reports_resolved_by_admin": [],
            "editorial_coverage": [],
            "most_discussed": [],
            "top_upvoted_discussions": [],
            "test_case_visibility": grouped(conn, test_case, column(test_case, "is_hidden", "hidden")),
            "notification_types": grouped(conn, notification, column(notification, "type")),
            "notification_read": grouped(conn, notification, column(notification, "is_read", "read")),
            "badge_earned_over_time": grouped(
                conn, developer_badge,
                func.date(column(developer_badge, "earned_on", "created_at")) if column(developer_badge, "earned_on", "created_at") is not None else None,
                limit=30,
            ),
            "rating_distribution": [],
            "hardest_problems": [],
            "leaderboard_top": [],
            "assessments_per_company": [],
            "assessment_points": grouped(
                conn, assessment_problem, column(assessment_problem, "assessment_id"),
                value_column=column(assessment_problem, "points"), aggregate="average",
            ),
            "runtime_by_language": [],
        }

        if developer is not None and developer_rating is not None:
            rating_rows = conn.execute(
                select(developer_rating).where(*developer_filters).order_by(developer_rating)
            ).scalars().all()
            buckets = {}
            for rating in rating_rows:
                lower = (int(rating) // 500) * 500
                label = f"{lower}-{lower + 499}"
                buckets[label] = buckets.get(label, 0) + 1
            charts["rating_distribution"] = [
                {"label": label, "value": value} for label, value in sorted(buckets.items())
            ]

        if problem is not None and problem_acceptance is not None:
            title = column(problem, "title", "name")
            acceptance_statement = (
                select(title.label("label"), problem_acceptance.label("value"))
                .where(problem_acceptance.is_not(None), *problem_filters)
                .order_by(problem_acceptance.asc())
                .limit(10)
            )
            charts["hardest_problems"] = [
                {"label": str(row.label or "Untitled"), "value": round(float(row.value), 2)}
                for row in conn.execute(acceptance_statement).all()
            ]

        if solves is not None and developer is not None:
            solved_developer_id = column(solves, "developer_id")
            developer_id = column(developer, "developer_id")
            developer_name = column(developer, "username", "full_name", "name")
            if solved_developer_id is not None and developer_id is not None and developer_name is not None:
                statement = (
                    select(developer_name.label("label"), func.count().label("value"))
                    .select_from(solves.join(developer, solved_developer_id == developer_id))
                    .group_by(developer_name)
                    .order_by(func.count().desc())
                    .limit(10)
                )
                if developer_filters:
                    statement = statement.where(*developer_filters)
                charts["top_solvers"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        if problem_tag is not None and tag is not None:
            link_tag_id = column(problem_tag, "tag_id")
            tag_id = column(tag, "tag_id")
            tag_name = column(tag, "name")
            if link_tag_id is not None and tag_id is not None and tag_name is not None:
                statement = (
                    select(tag_name.label("label"), func.count().label("value"))
                    .select_from(problem_tag.join(tag, link_tag_id == tag_id))
                    .group_by(tag_name)
                    .order_by(func.count().desc())
                    .limit(15)
                )
                charts["problems_per_tag"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        if participant is not None and contest is not None and contest_id is not None:
            joined_contest_id = column(contest, "contest_id")
            contest_title = column(contest, "title", "name")
            if joined_contest_id is not None and contest_title is not None:
                statement = (
                    select(contest_title.label("label"), func.count().label("value"))
                    .select_from(participant.join(contest, contest_id == joined_contest_id))
                    .group_by(contest_title)
                    .order_by(func.count().desc())
                    .limit(12)
                )
                charts["contest_participants"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        if participant is not None and developer is not None and contest is not None:
            participant_developer_id = column(participant, "developer_id")
            developer_id = column(developer, "developer_id")
            participant_contest_id = column(participant, "contest_id")
            contest_primary_id = column(contest, "contest_id")
            participant_rank = column(participant, "rank_position", "rank")
            participant_score = column(participant, "total_score", "score")
            developer_name = column(developer, "username", "full_name", "name")
            contest_name = column(contest, "title", "name")
            if all(value is not None for value in (
                participant_developer_id, developer_id, participant_contest_id, contest_primary_id,
                participant_score, developer_name, contest_name,
            )):
                joined = participant.join(developer, participant_developer_id == developer_id).join(
                    contest, participant_contest_id == contest_primary_id
                )
                statement = (
                    select(
                        developer_name.label("developer"),
                        contest_name.label("contest"),
                        participant_score.label("score"),
                        participant_rank.label("rank") if participant_rank is not None else participant_score.label("rank"),
                    )
                    .select_from(joined)
                    .order_by(participant_rank.asc() if participant_rank is not None else participant_score.desc())
                    .limit(10)
                )
                charts["leaderboard_top"] = [
                    {
                        "label": f"{row.developer} · {row.contest}",
                        "value": row.score or 0,
                        "rank": row.rank,
                    }
                    for row in conn.execute(statement).all()
                ]

        if submission is not None and programming_language is not None and submission_language_id is not None:
            language_id_column = column(programming_language, "language_id", "id")
            language_name = column(programming_language, "name", "language")
            if language_id_column is not None and language_name is not None:
                language_table_join = submission.join(
                    programming_language, submission_language_id == language_id_column
                )
                count_statement = (
                    select(language_name.label("label"), func.count().label("value"))
                    .select_from(language_table_join)
                    .group_by(language_name)
                    .order_by(func.count().desc())
                )
                if submission_filters:
                    count_statement = count_statement.where(*submission_filters)
                charts["language_popularity"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(count_statement).all()
                ]
                if submission_status is not None:
                    success_statement = (
                        select(
                            language_name.label("label"),
                            (
                                100.0
                                * func.sum(case((submission_status.ilike("accepted%"), 1), else_=0))
                                / func.nullif(func.count(), 0)
                            ).label("value"),
                        )
                        .select_from(language_table_join)
                        .group_by(language_name)
                        .order_by(text("value DESC"))
                    )
                    if submission_filters:
                        success_statement = success_statement.where(*submission_filters)
                    charts["language_success_rate"] = [
                        {"label": str(row.label), "value": round(float(row.value or 0), 2)}
                        for row in conn.execute(success_statement).all()
                    ]
                    runtime_column = column(submission, "runtime_ms", "runtime")
                    if runtime_column is not None:
                        runtime_statement = (
                            select(language_name.label("label"), func.avg(runtime_column).label("value"))
                            .select_from(language_table_join)
                            .where(runtime_column.is_not(None))
                            .group_by(language_name)
                            .order_by(func.avg(runtime_column).asc())
                        )
                        if submission_filters:
                            runtime_statement = runtime_statement.where(*submission_filters)
                        charts["runtime_by_language"] = [
                            {"label": str(row.label), "value": round(float(row.value or 0), 2)}
                            for row in conn.execute(runtime_statement).all()
                        ]

        if developer_badge is not None and badge is not None:
            link_badge_id = column(developer_badge, "badge_id")
            badge_id = column(badge, "badge_id")
            badge_name = column(badge, "name")
            if link_badge_id is not None and badge_id is not None and badge_name is not None:
                statement = (
                    select(badge_name.label("label"), func.count().label("value"))
                    .select_from(developer_badge.join(badge, link_badge_id == badge_id))
                    .group_by(badge_name)
                    .order_by(func.count().desc())
                    .limit(10)
                )
                charts["badge_popularity"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        if problem is not None and editorial is not None:
            problem_id = column(problem, "problem_id", "id")
            editorial_problem_id = column(editorial, "problem_id")
            if problem_id is not None and editorial_problem_id is not None:
                editorial_count = conn.execute(
                    select(func.count(func.distinct(editorial_problem_id)))
                ).scalar_one()
                total_problem_count = count_rows(conn, problem)
                charts["editorial_coverage"] = [
                    {"label": "With editorial", "value": editorial_count},
                    {"label": "Without editorial", "value": max(0, total_problem_count - editorial_count)},
                ]

        if discussion is not None and problem is not None and problem_table_link is not None:
            problem_id = column(problem, "problem_id", "id")
            problem_title = column(problem, "title", "name")
            discussion_id = column(discussion, "discussion_id", "id")
            if problem_id is not None and problem_title is not None and discussion_id is not None:
                statement = (
                    select(problem_title.label("label"), func.count(discussion_id).label("value"))
                    .select_from(discussion.join(problem, problem_table_link == problem_id))
                    .group_by(problem_title)
                    .order_by(func.count(discussion_id).desc())
                    .limit(10)
                )
                charts["most_discussed"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]
        if discussion is not None:
            discussion_title = column(discussion, "title", "discussion_title")
            upvotes = column(discussion, "upvotes", "votes")
            if discussion_title is not None and upvotes is not None:
                statement = (
                    select(discussion_title.label("label"), upvotes.label("value"))
                    .order_by(upvotes.desc())
                    .limit(10)
                )
                charts["top_upvoted_discussions"] = [
                    {"label": str(row.label), "value": row.value or 0}
                    for row in conn.execute(statement).all()
                ]

        if report is not None and administrator is not None:
            report_admin_id = column(report, "admin_id", "administrator_id")
            admin_id = column(administrator, "admin_id", "administrator_id")
            admin_name = column(administrator, "name", "full_name")
            if report_admin_id is not None and admin_id is not None and admin_name is not None and report_status is not None:
                statement = (
                    select(admin_name.label("label"), func.count().label("value"))
                    .select_from(report.join(administrator, report_admin_id == admin_id))
                    .where(report_status == "RESOLVED")
                    .group_by(admin_name)
                    .order_by(func.count().desc())
                )
                charts["reports_resolved_by_admin"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        if assessment is not None and company is not None and assessment_company_id is not None:
            company_id_column = column(company, "company_id", "id")
            company_name = column(company, "name", "company_name")
            if company_id_column is not None and company_name is not None:
                statement = (
                    select(company_name.label("label"), func.count(assessment_id).label("value"))
                    .select_from(assessment.join(company, assessment_company_id == company_id_column))
                    .group_by(company_name)
                    .order_by(func.count(assessment_id).desc())
                    .limit(12)
                )
                charts["assessments_per_company"] = [
                    {"label": str(row.label), "value": row.value} for row in conn.execute(statement).all()
                ]

        limitations = []
        if submission is not None and column(submission, "problem_id") is None:
            limitations.append("Problem-wise submission metrics are unavailable: submission has no problem_id. Use solves.attempts and programming_problem.acceptance_rate instead.")
        if discussion is not None and column(discussion, "developer_id") is None:
            limitations.append("Top discussion contributors are unavailable: discussion has no developer_id.")
        if report is not None and column(report, "reporter_id", "developer_id") is None:
            limitations.append("Reporter rankings are unavailable: report has no reporter identifier.")
        if report is not None and column(report, "resolved_at", "closed_at", "completed_at") is None:
            limitations.append("Average report resolution time is unavailable: report has no resolution timestamp.")

        language_options = []
        if programming_language is not None:
            language_id_column = column(programming_language, "language_id", "id")
            language_name = column(programming_language, "name", "language")
            if language_id_column is not None and language_name is not None:
                version_column = column(programming_language, "version")
                language_options = [
                    {
                        "id": row.id,
                        "name": f"{row.name} {row.version}" if row.version is not None else str(row.name),
                    }
                    for row in conn.execute(
                        select(
                            language_id_column.label("id"),
                            language_name.label("name"),
                            version_column.label("version") if version_column is not None else text("NULL").label("version"),
                        )
                        .order_by(language_name)
                    ).all()
                ]

        country_options = []
        if developer_country is not None:
            country_options = [
                str(value)
                for value in conn.execute(
                    select(developer_country).where(developer_country.is_not(None)).distinct().order_by(developer_country)
                ).scalars().all()
            ]

    return {
        "kpis": {
            "developers": total_developers,
            "problems": total_problems,
            "submissions": total_submissions,
            "acceptance_rate": acceptance_rate,
            "active_contests": active_contests,
            "open_reports": open_reports,
        },
        "charts": charts,
        "filters": {"countries": country_options, "languages": language_options},
        "limitations": limitations,
    }


@app.get("/api/analytics/problems")
def problem_analytics():
    table = get_table("programming_problem")
    difficulty = find_col(table, ["difficulty", "level", "problem_difficulty"])
    result = {"total": 0, "difficulty": []}
    with engine.connect() as conn:
        result["total"] = conn.execute(select(func.count()).select_from(table)).scalar_one()
        if difficulty is not None:
            rows = conn.execute(
                select(difficulty.label("label"), func.count().label("count"))
                .group_by(difficulty)
                .order_by(func.count().desc())
            ).all()
            result["difficulty"] = [{"label": str(r.label), "count": r.count} for r in rows]
    return result


@app.get("/api/analytics/submissions")
def submission_analytics():
    table = get_table("submission")
    status = find_col(table, ["status", "submission_status", "result", "verdict"])
    result = {"total": 0, "status": []}
    with engine.connect() as conn:
        result["total"] = conn.execute(select(func.count()).select_from(table)).scalar_one()
        if status is not None:
            rows = conn.execute(
                select(status.label("label"), func.count().label("count"))
                .group_by(status)
                .order_by(func.count().desc())
            ).all()
            result["status"] = [{"label": str(r.label), "count": r.count} for r in rows]
    return result


def validate_read_only_sql(sql: str, limit: int = 100):
    if not sql or not sql.strip():
        raise ValueError("SQL query is required.")

    cleaned = sql.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        raise ValueError("Only a single SELECT statement is allowed.")

    normalized = re.sub(r"\s+", " ", cleaned).upper()
    without_comments = re.sub(r"/\*.*?\*/|--[^\r\n]*", "", cleaned, flags=re.DOTALL).upper()
    if DEVELOPER_AUTH_TABLE.upper() in without_comments:
        raise ValueError("Authentication tables are not available in the custom SQL tool.")
    disallowed = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "GRANT", "REVOKE", "MERGE", "CALL", "EXEC", "COPY",
    ]
    if not normalized.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed in the custom SQL tool.")
    if any(token in normalized for token in disallowed):
        raise ValueError("Write operations and schema changes are not allowed.")

    limit = max(1, min(int(limit), 250))
    if " LIMIT " not in normalized:
        cleaned = f"{cleaned} LIMIT :limit"
    return cleaned, {"limit": limit}


@app.post("/api/query")
def run_query(payload: dict | None = None):
    if payload is None:
        payload = {}
    sql = str(payload.get("sql", "")).strip()
    limit = int(payload.get("limit", 100) or 100)
    try:
        validated_sql, params = validate_read_only_sql(sql, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(validated_sql), params).mappings().all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc.orig if getattr(exc, "orig", None) else exc)) from exc

    if not rows:
        return {"columns": [], "rows": [], "row_count": 0}

    columns = list(rows[0].keys())
    return {
        "columns": columns,
        "rows": [row_dict(row) for row in rows],
        "row_count": len(rows),
    }

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, or_, select, String, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import engine, refresh_metadata
from .utils import row_dict

router = APIRouter(tags=["developer platform"])


def current_developer_id(request: Request):
    user = request.state.current_user
    developer_id = user.get("developer_id")
    if user.get("role") != "developer" or not developer_id:
        raise HTTPException(status_code=403, detail="Developer access required.")
    return developer_id


def get_platform_tables(*names):
    try:
        tables = refresh_metadata().tables
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not read the platform database schema.") from exc
    missing = [name for name in names if name not in tables]
    if missing:
        raise HTTPException(status_code=503, detail=f"Platform schema is missing required tables: {', '.join(missing)}.")
    return tables


def scalar_count(conn, table, *conditions):
    statement = select(func.count()).select_from(table)
    if conditions:
        statement = statement.where(*conditions)
    return conn.execute(statement).scalar_one()


def solved_condition(solves, developer_id, problem):
    return select(1).select_from(solves).where(
        solves.c.developer_id == developer_id,
        solves.c.problem_id == problem.c.problem_id,
    ).exists()


def activity_streak(solved_dates, today):
    unique_dates = sorted({value.date() if isinstance(value, datetime) else value for value in solved_dates})
    longest = current = 0
    previous = None
    for solved_date in unique_dates:
        current = current + 1 if previous and solved_date == previous + timedelta(days=1) else 1
        longest = max(longest, current)
        previous = solved_date
    current_streak = 0
    check_date = today if today in unique_dates else today - timedelta(days=1)
    date_set = set(unique_dates)
    while check_date in date_set:
        current_streak += 1
        check_date -= timedelta(days=1)
    return current_streak, longest


@router.get("/api/languages")
def list_languages(request: Request):
    current_developer_id(request)
    tables = get_platform_tables("programming_language")
    language = tables["programming_language"]
    with engine.connect() as conn:
        return [
            row_dict(row)
            for row in conn.execute(
                select(language.c.language_id, language.c.name, language.c.version)
                .order_by(language.c.name, language.c.version)
            ).mappings()
        ]


@router.get("/api/problems")
def list_problems(
    request: Request,
    search: str = Query("", max_length=150),
    difficulty: str = Query("", max_length=20),
    topic: str = Query("", max_length=60),
    status: str = Query("all", pattern="^(all|solved|unsolved)$"),
    sort: str = Query("problem_id", pattern="^(problem_id|title|difficulty|acceptance_rate)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("programming_problem", "solves", "problem_tag", "tag")
    problem, solves = tables["programming_problem"], tables["solves"]
    problem_tag, tag = tables["problem_tag"], tables["tag"]
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(problem.c.title.ilike(pattern), problem.c.problem_id.cast(String).ilike(pattern)))
    if difficulty:
        filters.append(func.lower(problem.c.difficulty) == difficulty.lower())
    if status == "solved":
        filters.append(solved_condition(solves, developer_id, problem))
    elif status == "unsolved":
        filters.append(~solved_condition(solves, developer_id, problem))
    if topic:
        filters.append(
            select(1).select_from(problem_tag.join(tag, problem_tag.c.tag_id == tag.c.tag_id)).where(
                problem_tag.c.problem_id == problem.c.problem_id,
                func.lower(tag.c.name) == topic.lower(),
            ).exists()
        )

    sort_column = problem.c[sort]
    sort_column = sort_column.desc().nullslast() if order == "desc" else sort_column.asc().nullslast()
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(problem).where(*filters)).scalar_one()
        rows = conn.execute(
            select(
                problem.c.problem_id,
                problem.c.title,
                problem.c.difficulty,
                problem.c.acceptance_rate,
            ).where(*filters).order_by(sort_column, problem.c.problem_id).offset(skip).limit(limit)
        ).mappings().all()
        problem_ids = [row["problem_id"] for row in rows]
        topic_rows = conn.execute(
            select(problem_tag.c.problem_id, tag.c.name)
            .select_from(problem_tag.join(tag, problem_tag.c.tag_id == tag.c.tag_id))
            .where(problem_tag.c.problem_id.in_(problem_ids))
            .order_by(tag.c.name)
        ).all() if problem_ids else []
        solved_ids = set(conn.execute(
            select(solves.c.problem_id).where(
                solves.c.developer_id == developer_id,
                solves.c.problem_id.in_(problem_ids),
            )
        ).scalars()) if problem_ids else set()
        topics = conn.execute(select(tag.c.name).distinct().order_by(tag.c.name)).scalars().all()

    topics_by_problem = {}
    for problem_id, tag_name in topic_rows:
        topics_by_problem.setdefault(problem_id, []).append(tag_name)
    return {
        "items": [
            {
                **row_dict(row),
                "solved": row["problem_id"] in solved_ids,
                "topics": topics_by_problem.get(row["problem_id"], []),
            }
            for row in rows
        ],
        "topics": topics,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/api/problems/{problem_id}")
def read_problem(problem_id: int, request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("programming_problem", "problem_tag", "tag", "solves", "test_case")
    problem, problem_tag = tables["programming_problem"], tables["problem_tag"]
    with engine.connect() as conn:
        row = conn.execute(
            select(
                problem.c.problem_id,
                problem.c.title,
                problem.c.description,
                problem.c.difficulty,
                problem.c.acceptance_rate,
                problem.c.time_limit_ms,
                problem.c.memory_limit_mb,
            ).where(problem.c.problem_id == problem_id)
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Problem not found.")
        tags = conn.execute(
            select(tables["tag"].c.name)
            .select_from(problem_tag.join(tables["tag"], problem_tag.c.tag_id == tables["tag"].c.tag_id))
            .where(problem_tag.c.problem_id == problem_id)
            .order_by(tables["tag"].c.name)
        ).scalars().all()
        examples = conn.execute(
            select(
                tables["test_case"].c.test_case_no,
                tables["test_case"].c.input,
                tables["test_case"].c.expected_output,
            ).where(
                tables["test_case"].c.problem_id == problem_id,
                tables["test_case"].c.is_hidden.is_(False),
            ).order_by(tables["test_case"].c.test_case_no)
        ).mappings().all()
        is_solved = conn.execute(select(
            select(1).select_from(tables["solves"]).where(
                tables["solves"].c.developer_id == developer_id,
                tables["solves"].c.problem_id == problem_id,
            ).exists()
        )).scalar_one()
        previous = conn.execute(
            select(problem.c.problem_id, problem.c.title)
            .where(problem.c.problem_id < problem_id)
            .order_by(problem.c.problem_id.desc())
            .limit(1)
        ).mappings().first()
        following = conn.execute(
            select(problem.c.problem_id, problem.c.title)
            .where(problem.c.problem_id > problem_id)
            .order_by(problem.c.problem_id)
            .limit(1)
        ).mappings().first()
    return {
        **row_dict(row),
        "topics": tags,
        "examples": [row_dict(example) for example in examples],
        "solved": bool(is_solved),
        "previous": dict(previous) if previous else None,
        "next": dict(following) if following else None,
        "execution_available": False,
    }


class SubmissionCreate(BaseModel):
    problem_id: int = Field(gt=0)
    language_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=100_000)


@router.post("/api/submissions", status_code=201)
def create_submission(payload: SubmissionCreate, request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("submission", "programming_problem", "programming_language")
    submission, problem, language = tables["submission"], tables["programming_problem"], tables["programming_language"]
    try:
        with engine.begin() as conn:
            if conn.execute(select(problem.c.problem_id).where(problem.c.problem_id == payload.problem_id)).first() is None:
                raise HTTPException(status_code=404, detail="Problem not found.")
            if conn.execute(select(language.c.language_id).where(language.c.language_id == payload.language_id)).first() is None:
                raise HTTPException(status_code=400, detail="Unsupported programming language.")
            submission_id = conn.execute(
                insert(submission).values(
                    developer_id=developer_id,
                    problem_id=payload.problem_id,
                    language_id=payload.language_id,
                    code=payload.code,
                    status="PENDING",
                ).returning(submission.c.submission_id)
            ).scalar_one()
        return {
            "submission_id": submission_id,
            "status": "PENDING",
            "evaluated": False,
            "message": "Code saved. This project has no code execution or judge service, so it has not been evaluated.",
        }
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not save this submission.") from exc


@router.get("/api/submissions/me")
def list_my_submissions(
    request: Request,
    problem_id: int | None = Query(None, gt=0),
    status: str = Query("", max_length=25),
    language_id: int | None = Query(None, gt=0),
    search: str = Query("", max_length=150),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("submission", "programming_problem", "programming_language")
    submission, problem = tables["submission"], tables["programming_problem"]
    language = tables["programming_language"]
    filters = [submission.c.developer_id == developer_id]
    if problem_id is not None:
        filters.append(submission.c.problem_id == problem_id)
    if status:
        filters.append(func.lower(submission.c.status) == status.lower())
    if language_id is not None:
        filters.append(submission.c.language_id == language_id)
    if search:
        filters.append(problem.c.title.ilike(f"%{search.strip()}%"))

    statement = (
        select(
            submission.c.submission_id,
            submission.c.problem_id,
            problem.c.title.label("problem_title"),
            submission.c.language_id,
            language.c.name.label("language"),
            submission.c.status,
            submission.c.runtime_ms,
            submission.c.memory_kb,
            submission.c.submitted_at,
        )
        .select_from(
            submission.join(problem, submission.c.problem_id == problem.c.problem_id, isouter=True)
            .join(language, submission.c.language_id == language.c.language_id)
        )
        .where(*filters)
    )
    with engine.connect() as conn:
        total = conn.execute(
            select(func.count()).select_from(
                submission.join(problem, submission.c.problem_id == problem.c.problem_id, isouter=True)
            ).where(*filters)
        ).scalar_one()
        rows = conn.execute(
            statement.order_by(submission.c.submitted_at.desc(), submission.c.submission_id.desc())
            .offset(skip).limit(limit)
        ).mappings().all()
    return {"items": [row_dict(row) for row in rows], "total": total, "skip": skip, "limit": limit}


@router.get("/api/submissions/{submission_id}")
def read_my_submission(submission_id: int, request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("submission", "programming_problem", "programming_language")
    submission, problem, language = tables["submission"], tables["programming_problem"], tables["programming_language"]
    with engine.connect() as conn:
        row = conn.execute(
            select(
                submission.c.submission_id,
                submission.c.problem_id,
                problem.c.title.label("problem_title"),
                language.c.name.label("language"),
                submission.c.code,
                submission.c.status,
                submission.c.runtime_ms,
                submission.c.memory_kb,
                submission.c.submitted_at,
            )
            .select_from(
                submission.join(problem, submission.c.problem_id == problem.c.problem_id, isouter=True)
                .join(language, submission.c.language_id == language.c.language_id)
            )
            .where(submission.c.submission_id == submission_id, submission.c.developer_id == developer_id)
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return row_dict(row)


def personal_summary(conn, tables, developer_id):
    solves, problems, submission = tables["solves"], tables["programming_problem"], tables["submission"]
    solved_rows = conn.execute(
        select(problems.c.difficulty, func.count().label("count"))
        .select_from(solves.join(problems, solves.c.problem_id == problems.c.problem_id))
        .where(solves.c.developer_id == developer_id)
        .group_by(problems.c.difficulty)
    ).all()
    by_difficulty = {str(row.difficulty).lower(): row.count for row in solved_rows}
    total_solved = sum(by_difficulty.values())
    total_problems = scalar_count(conn, problems)
    total_submissions = scalar_count(conn, submission, submission.c.developer_id == developer_id)
    accepted = scalar_count(
        conn,
        submission,
        submission.c.developer_id == developer_id,
        func.upper(submission.c.status) == "ACCEPTED",
    )
    solve_dates = conn.execute(
        select(func.date(solves.c.solved_on).label("day"))
        .where(solves.c.developer_id == developer_id)
        .group_by(func.date(solves.c.solved_on))
    ).scalars().all()
    current_streak, longest_streak = activity_streak(solve_dates, date.today())
    return {
        "total_solved": total_solved,
        "easy_solved": by_difficulty.get("easy", 0),
        "medium_solved": by_difficulty.get("medium", 0),
        "hard_solved": by_difficulty.get("hard", 0),
        "total_problems": total_problems,
        "remaining_problems": max(total_problems - total_solved, 0),
        "total_submissions": total_submissions,
        "accepted_submissions": accepted,
        "acceptance_rate": round(100 * accepted / total_submissions, 2) if total_submissions else None,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def global_summary(conn, tables):
    developer, problem, submission, contest = (
        tables["developer"], tables["programming_problem"], tables["submission"], tables["contest"]
    )
    total_submissions = scalar_count(conn, submission)
    accepted = scalar_count(conn, submission, func.upper(submission.c.status) == "ACCEPTED")
    return {
        "developers": scalar_count(conn, developer),
        "problems": scalar_count(conn, problem),
        "submissions": total_submissions,
        "accepted_submissions": accepted,
        "acceptance_rate": round(100 * accepted / total_submissions, 2) if total_submissions else None,
        "contests": scalar_count(conn, contest),
    }


def global_charts(conn, tables):
    problems, submission = tables["programming_problem"], tables["submission"]
    difficulty = conn.execute(
        select(problems.c.difficulty.label("label"), func.count().label("value"))
        .group_by(problems.c.difficulty).order_by(problems.c.difficulty)
    ).mappings().all()
    status = conn.execute(
        select(submission.c.status.label("label"), func.count().label("value"))
        .group_by(submission.c.status).order_by(func.count().desc())
    ).mappings().all()
    since = date.today() - timedelta(days=29)
    daily = conn.execute(
        select(func.date(submission.c.submitted_at).label("label"), func.count().label("value"))
        .where(func.date(submission.c.submitted_at) >= since)
        .group_by(func.date(submission.c.submitted_at))
        .order_by(func.date(submission.c.submitted_at))
    ).mappings().all()
    most_solved = conn.execute(
        select(
            problems.c.title.label("label"),
            func.count(tables["solves"].c.problem_id).label("value"),
        )
        .select_from(tables["solves"].join(problems, tables["solves"].c.problem_id == problems.c.problem_id))
        .group_by(problems.c.problem_id, problems.c.title)
        .order_by(func.count(tables["solves"].c.problem_id).desc(), problems.c.title)
        .limit(10)
    ).mappings().all()
    return {
        "problems_by_difficulty": [row_dict(row) for row in difficulty],
        "submission_status": [row_dict(row) for row in status],
        "daily_submissions": [row_dict(row) for row in daily],
        "most_solved_problems": [row_dict(row) for row in most_solved],
    }


def activity_data(conn, tables, developer_id, days=365):
    start = date.today() - timedelta(days=days - 1)
    solves, submissions = tables["solves"], tables["submission"]
    solved_rows = conn.execute(
        select(func.date(solves.c.solved_on).label("day"), func.count().label("solved"))
        .where(solves.c.developer_id == developer_id, func.date(solves.c.solved_on) >= start)
        .group_by(func.date(solves.c.solved_on))
    ).mappings().all()
    submission_rows = conn.execute(
        select(func.date(submissions.c.submitted_at).label("day"), func.count().label("submissions"))
        .where(submissions.c.developer_id == developer_id, func.date(submissions.c.submitted_at) >= start)
        .group_by(func.date(submissions.c.submitted_at))
    ).mappings().all()
    per_day = {}
    for row in solved_rows:
        per_day.setdefault(row["day"], {"solved": 0, "submissions": 0})["solved"] = row["solved"]
    for row in submission_rows:
        per_day.setdefault(row["day"], {"solved": 0, "submissions": 0})["submissions"] = row["submissions"]
    return [
        {"date": (start + timedelta(days=offset)).isoformat(), **per_day.get(start + timedelta(days=offset), {"solved": 0, "submissions": 0})}
        for offset in range(days)
    ]


@router.get("/api/user/dashboard")
def user_dashboard(request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables(
        "developer", "programming_problem", "submission", "solves", "problem_tag", "tag", "contest"
    )
    with engine.connect() as conn:
        developer = conn.execute(
            select(tables["developer"].c.username, tables["developer"].c.full_name)
            .where(tables["developer"].c.developer_id == developer_id)
        ).mappings().first()
        if developer is None:
            raise HTTPException(status_code=404, detail="Developer profile not found.")
        personal = personal_summary(conn, tables, developer_id)
        global_data = global_summary(conn, tables)
        charts = global_charts(conn, tables)
        progress = conn.execute(
            select(
                tables["programming_problem"].c.difficulty,
                func.count().label("total"),
            ).group_by(tables["programming_problem"].c.difficulty)
        ).all()
        totals_by_difficulty = {str(row.difficulty).lower(): row.total for row in progress}
        activity = activity_data(conn, tables, developer_id)
        unsolved = ~solved_condition(tables["solves"], developer_id, tables["programming_problem"])
        recommendations = conn.execute(
            select(
                tables["programming_problem"].c.problem_id,
                tables["programming_problem"].c.title,
                tables["programming_problem"].c.difficulty,
            ).where(unsolved)
            .order_by(tables["programming_problem"].c.problem_id)
            .limit(5)
        ).mappings().all()
        recent = conn.execute(
            select(
                tables["submission"].c.submission_id,
                tables["submission"].c.problem_id,
                tables["programming_problem"].c.title.label("problem_title"),
                tables["submission"].c.status,
                tables["submission"].c.submitted_at,
            )
            .select_from(tables["submission"].join(
                tables["programming_problem"],
                tables["submission"].c.problem_id == tables["programming_problem"].c.problem_id,
                isouter=True,
            ))
            .where(tables["submission"].c.developer_id == developer_id)
            .order_by(tables["submission"].c.submitted_at.desc())
            .limit(8)
        ).mappings().all()
    return {
        "developer": row_dict(developer),
        "personal": personal,
        "global": global_data,
        "difficulty_totals": totals_by_difficulty,
        "global_charts": charts,
        "activity": activity,
        "recommendations": [row_dict(row) for row in recommendations],
        "recent_submissions": [row_dict(row) for row in recent],
    }


@router.get("/api/user/activity")
def user_activity(request: Request, days: int = Query(365, ge=7, le=365)):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("solves", "submission")
    with engine.connect() as conn:
        days_data = activity_data(conn, tables, developer_id, days)
        dates = conn.execute(
            select(func.date(tables["solves"].c.solved_on))
            .where(tables["solves"].c.developer_id == developer_id)
            .group_by(func.date(tables["solves"].c.solved_on))
        ).scalars().all()
    current_streak, longest_streak = activity_streak(dates, date.today())
    return {"days": days_data, "current_streak": current_streak, "longest_streak": longest_streak}


@router.get("/api/user/analytics")
def user_analytics(request: Request, days: int = Query(30, ge=7, le=365)):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("developer", "programming_problem", "submission", "solves", "problem_tag", "tag")
    with engine.connect() as conn:
        personal = personal_summary(conn, tables, developer_id)
        activity = activity_data(conn, tables, developer_id, days)
        difficulty = conn.execute(
            select(tables["programming_problem"].c.difficulty.label("label"), func.count().label("value"))
            .select_from(tables["solves"].join(
                tables["programming_problem"],
                tables["solves"].c.problem_id == tables["programming_problem"].c.problem_id,
            ))
            .where(tables["solves"].c.developer_id == developer_id)
            .group_by(tables["programming_problem"].c.difficulty)
        ).mappings().all()
        submission_status = conn.execute(
            select(tables["submission"].c.status.label("label"), func.count().label("value"))
            .where(tables["submission"].c.developer_id == developer_id)
            .group_by(tables["submission"].c.status)
            .order_by(func.count().desc())
        ).mappings().all()
        topics = conn.execute(
            select(tables["tag"].c.name.label("topic"), func.count().label("solved"))
            .select_from(
                tables["solves"]
                .join(tables["problem_tag"], tables["solves"].c.problem_id == tables["problem_tag"].c.problem_id)
                .join(tables["tag"], tables["problem_tag"].c.tag_id == tables["tag"].c.tag_id)
            )
            .where(tables["solves"].c.developer_id == developer_id)
            .group_by(tables["tag"].c.name)
            .order_by(func.count().desc(), tables["tag"].c.name)
        ).mappings().all()
    return {
        "personal": personal,
        "difficulty": [row_dict(row) for row in difficulty],
        "activity": activity,
        "topics": [row_dict(row) for row in topics],
        "submission_status": [row_dict(row) for row in submission_status],
    }


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=100)
    country: str | None = Field(None, min_length=1, max_length=60)


@router.get("/api/user/profile")
def user_profile(request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("developer", "developer_auth_accounts")
    with engine.connect() as conn:
        profile = conn.execute(
            select(
                tables["developer"].c.username,
                tables["developer"].c.full_name,
                tables["developer"].c.email,
                tables["developer"].c.country,
                tables["developer"].c.rating,
                tables["developer"].c.joined_on,
            ).where(tables["developer"].c.developer_id == developer_id)
        ).mappings().first()
        account = conn.execute(
            select(tables["developer_auth_accounts"].c.created_at)
            .where(tables["developer_auth_accounts"].c.developer_id == developer_id)
        ).mappings().first()
    if profile is None or account is None:
        raise HTTPException(status_code=404, detail="Developer profile not found.")
    return {**row_dict(profile), "account_created_at": row_dict(account)["created_at"]}


@router.patch("/api/user/profile")
def update_user_profile(payload: ProfileUpdate, request: Request):
    developer_id = current_developer_id(request)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=400, detail="Provide at least one profile field to update.")
    values = {key: value.strip() if value is not None else value for key, value in values.items()}
    if any(not value for value in values.values()):
        raise HTTPException(status_code=400, detail="Profile fields cannot be blank.")
    table = get_platform_tables("developer")["developer"]
    with engine.begin() as conn:
        result = conn.execute(
            update(table).where(table.c.developer_id == developer_id).values(**values)
        )
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Developer profile not found.")
    return {"message": "Profile updated."}


@router.get("/api/leaderboard")
def leaderboard(request: Request, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    current_developer_id(request)
    tables = get_platform_tables("developer", "solves")
    developer, solves = tables["developer"], tables["solves"]
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                developer.c.username,
                func.count(solves.c.problem_id).label("problems_solved"),
            )
            .select_from(developer.join(solves, developer.c.developer_id == solves.c.developer_id, isouter=True))
            .group_by(developer.c.developer_id, developer.c.username)
            .order_by(func.count(solves.c.problem_id).desc(), developer.c.username)
            .offset(skip).limit(limit)
        ).mappings().all()
    return {
        "items": [{"rank": skip + index + 1, **row_dict(row)} for index, row in enumerate(rows)],
        "skip": skip,
        "limit": limit,
    }


@router.get("/api/contests")
def list_contests(request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("contest", "contest_problem", "contest_participant")
    contest, contest_problem, participant = tables["contest"], tables["contest_problem"], tables["contest_participant"]
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        contests = conn.execute(
            select(
                contest,
                select(func.count()).select_from(contest_problem)
                .where(contest_problem.c.contest_id == contest.c.contest_id).scalar_subquery().label("problem_count"),
                select(func.count()).select_from(participant)
                .where(participant.c.contest_id == contest.c.contest_id).scalar_subquery().label("participant_count"),
                select(func.count()).select_from(participant)
                .where(
                    participant.c.contest_id == contest.c.contest_id,
                    participant.c.developer_id == developer_id,
                ).scalar_subquery().label("is_registered"),
            ).order_by(contest.c.start_time.desc()).limit(100)
        ).mappings().all()
    items = []
    for row in contests:
        item = row_dict(row)
        item["registered"] = item.pop("is_registered") > 0
        start_time = row["start_time"]
        end_time = row["end_time"]
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        item["phase"] = "upcoming" if start_time > now else "active" if end_time > now else "past"
        items.append(item)
    return {"items": items}


@router.post("/api/contests/{contest_id}/join", status_code=201)
def join_contest(contest_id: int, request: Request):
    developer_id = current_developer_id(request)
    tables = get_platform_tables("contest", "contest_participant")
    contest, participant = tables["contest"], tables["contest_participant"]
    try:
        with engine.begin() as conn:
            contest_row = conn.execute(
                select(contest.c.start_time, contest.c.end_time, contest.c.status)
                .where(contest.c.contest_id == contest_id)
            ).mappings().first()
            if contest_row is None:
                raise HTTPException(status_code=404, detail="Contest not found.")
            now = datetime.now(timezone.utc)
            start_time = contest_row["start_time"]
            end_time = contest_row["end_time"]
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if start_time <= now or end_time <= now:
                raise HTTPException(status_code=400, detail="Registration is closed for this contest.")
            conn.execute(insert(participant).values(
                contest_id=contest_id,
                developer_id=developer_id,
                registered_on=datetime.now(timezone.utc),
            ))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="You are already registered for this contest.") from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Could not register for this contest.") from exc
    return {"message": "Registered for contest."}

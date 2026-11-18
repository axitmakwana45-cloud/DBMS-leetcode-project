from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, func, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .database import engine, refresh_metadata

router = APIRouter(prefix="/api/company", tags=["company portal"])


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    start_at: datetime
    end_at: datetime
    duration_minutes: int = Field(ge=1, le=1440)
    problem_ids: list[int] = Field(default_factory=list, max_length=100)
    developer_ids: list[int] = Field(default_factory=list, max_length=500)


def tables():
    return refresh_metadata().tables


def table_named(all_tables, *names):
    for name in names:
        if name in all_tables:
            return all_tables[name]
    return None


def col(table, *names):
    if table is None:
        return None
    for name in names:
        if name in table.c:
            return table.c[name]
    return None


def pk(table):
    if table is None or not table.primary_key.columns:
        return None
    return list(table.primary_key.columns)[0]


def add_if_present(target, candidates, value, values):
    column = col(target, *candidates)
    if column is not None and value is not None:
        values[column.name] = value


def company_record(conn, company_id):
    all_tables = tables()
    company = table_named(all_tables, "company")
    company_pk = col(company, "company_id", "id")
    if company is None or company_pk is None:
        raise HTTPException(status_code=503, detail="Company table or company primary key is missing.")
    row = conn.execute(select(company).where(company_pk == company_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Company profile not found.")
    return dict(row)


@router.get("/me")
def company_me(request: Request):
    with engine.connect() as conn:
        return company_record(conn, request.state.current_user["company_id"])


@router.get("/dashboard")
def company_dashboard(request: Request):
    company_id = request.state.current_user["company_id"]
    all_tables = tables()
    assessment = table_named(all_tables, "assessment")
    assessment_company = col(assessment, "company_id")
    assessment_pk = pk(assessment)
    participation = table_named(all_tables, "assessment_participation")
    assessment_fk = col(participation, "assessment_id")
    developer_fk = col(participation, "developer_id")
    score_col = col(participation, "score", "marks", "total_score")
    status_col = col(participation, "status")
    if assessment is None or assessment_company is None or assessment_pk is None:
        raise HTTPException(status_code=503, detail="Assessment table must contain assessment_id and company_id.")
    with engine.connect() as conn:
        owned = conn.execute(select(assessment).where(assessment_company == company_id)).mappings().all()
        assessment_ids = [row[assessment_pk.name] for row in owned]
        participant_rows = []
        if assessment_ids and participation is not None and assessment_fk is not None:
            participant_rows = conn.execute(select(participation).where(assessment_fk.in_(assessment_ids))).mappings().all()
        now = datetime.now(timezone.utc)
        def get_date(row, *names):
            for name in names:
                value = row.get(name)
                if value is not None:
                    return value
            return None
        active = upcoming = completed = 0
        for row in owned:
            start = get_date(row, "start_at", "start_time", "start_date")
            end = get_date(row, "end_at", "end_time", "end_date", "deadline")
            if start and end and start <= now <= end:
                active += 1
            elif start and start > now:
                upcoming += 1
            elif end and end < now:
                completed += 1
        unique_developers = {row.get(developer_fk.name) for row in participant_rows if developer_fk is not None and row.get(developer_fk.name) is not None}
        scores = [float(row[score_col.name]) for row in participant_rows if score_col is not None and row.get(score_col.name) is not None]
        completed_participants = sum(1 for row in participant_rows if status_col is not None and str(row.get(status_col.name, "")).upper() in {"SUBMITTED", "COMPLETED", "EVALUATED", "ACCEPTED"})
        return {
            "total_assessments": len(owned),
            "active_assessments": active,
            "upcoming_assessments": upcoming,
            "completed_assessments": completed,
            "assigned_developers": len(unique_developers),
            "total_participants": len(participant_rows),
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "completion_rate": round(100 * completed_participants / len(participant_rows), 2) if participant_rows else 0,
            "assessments": [dict(row) for row in owned],
        }


@router.get("/options")
def company_options():
    all_tables = tables()
    developers = table_named(all_tables, "developer")
    problems = table_named(all_tables, "programming_problem")
    if developers is None or problems is None:
        raise HTTPException(status_code=503, detail="Developer or programming_problem table is missing.")
    developer_id = col(developers, "developer_id", "id")
    developer_name = col(developers, "full_name", "username", "name")
    problem_id = col(problems, "problem_id", "id")
    problem_title = col(problems, "title", "name")
    with engine.connect() as conn:
        developer_rows = conn.execute(select(developer_id, developer_name).order_by(developer_name).limit(1000)).all() if developer_id is not None and developer_name is not None else []
        problem_rows = conn.execute(select(problem_id, problem_title).order_by(problem_id).limit(2000)).all() if problem_id is not None and problem_title is not None else []
    return {
        "developers": [{"id": row[0], "name": row[1]} for row in developer_rows],
        "problems": [{"id": row[0], "title": row[1]} for row in problem_rows],
    }


@router.post("/assessments", status_code=201)
def create_assessment(payload: AssessmentCreate, request: Request):
    company_id = request.state.current_user["company_id"]
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=400, detail="End time must be after start time.")
    if not payload.problem_ids:
        raise HTTPException(status_code=400, detail="Select at least one problem.")
    all_tables = tables()
    assessment = table_named(all_tables, "assessment")
    assessment_pk = pk(assessment)
    if assessment is None or assessment_pk is None or col(assessment, "company_id") is None:
        raise HTTPException(status_code=503, detail="Assessment table requires a primary key and company_id.")
    values: dict[str, Any] = {}
    add_if_present(assessment, ("company_id",), company_id, values)
    add_if_present(assessment, ("title", "name", "assessment_name"), payload.title, values)
    add_if_present(assessment, ("description", "details"), payload.description, values)
    add_if_present(assessment, ("start_at", "start_time", "start_date"), payload.start_at, values)
    add_if_present(assessment, ("end_at", "end_time", "end_date", "deadline"), payload.end_at, values)
    add_if_present(assessment, ("duration_minutes", "duration"), payload.duration_minutes, values)
    add_if_present(assessment, ("status"), "SCHEDULED", values)
    add_if_present(assessment, ("created_at", "created_on"), datetime.now(timezone.utc), values)
    missing = [column.name for column in assessment.columns if not column.nullable and column.default is None and column.server_default is None and not column.primary_key and column.name not in values]
    if missing:
        raise HTTPException(status_code=422, detail=f"Assessment schema has required fields not handled by this portal: {missing}")
    try:
        with engine.begin() as conn:
            assessment_id = conn.execute(insert(assessment).values(**values).returning(assessment_pk)).scalar_one()
            assessment_problem = table_named(all_tables, "assessment_problem")
            if assessment_problem is not None:
                ap_assessment = col(assessment_problem, "assessment_id")
                ap_problem = col(assessment_problem, "problem_id")
                if ap_assessment is None or ap_problem is None:
                    raise HTTPException(status_code=503, detail="assessment_problem must contain assessment_id and problem_id.")
                for problem_id in dict.fromkeys(payload.problem_ids):
                    conn.execute(insert(assessment_problem).values({ap_assessment.name: assessment_id, ap_problem.name: problem_id}))
            if payload.developer_ids:
                participation = table_named(all_tables, "assessment_participation")
                part_assessment = col(participation, "assessment_id")
                part_developer = col(participation, "developer_id")
                if participation is None or part_assessment is None or part_developer is None:
                    raise HTTPException(status_code=503, detail="assessment_participation must contain assessment_id and developer_id.")
                for developer_id in dict.fromkeys(payload.developer_ids):
                    part_values = {part_assessment.name: assessment_id, part_developer.name: developer_id}
                    add_if_present(participation, ("status"), "ASSIGNED", part_values)
                    add_if_present(participation, ("assigned_at", "created_at"), datetime.now(timezone.utc), part_values)
                    conn.execute(insert(participation).values(**part_values))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Assessment assignment conflicts with an existing database constraint or selected ID.") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=f"Could not create assessment: {getattr(exc, 'orig', exc)}") from exc
    return {"message": "Assessment created and assignments saved.", "assessment_id": assessment_id}


@router.get("/assessments/{assessment_id}/participants")
def assessment_participants(assessment_id: int, request: Request):
    company_id = request.state.current_user["company_id"]
    all_tables = tables()
    assessment = table_named(all_tables, "assessment")
    assessment_pk = pk(assessment)
    assessment_company = col(assessment, "company_id")
    participation = table_named(all_tables, "assessment_participation")
    part_assessment = col(participation, "assessment_id")
    if assessment_pk is None or assessment_company is None or part_assessment is None:
        raise HTTPException(status_code=503, detail="Assessment participation schema is incomplete.")
    with engine.connect() as conn:
        owned = conn.execute(select(assessment_pk).where(assessment_pk == assessment_id, assessment_company == company_id)).first()
        if owned is None:
            raise HTTPException(status_code=404, detail="Assessment not found for this company.")
        rows = conn.execute(select(participation).where(part_assessment == assessment_id)).mappings().all()
    return {"items": [dict(row) for row in rows], "total": len(rows)}

# LeetCode Management System

A schema-aware CRUD and analytics application for the existing LeetCode Management System PostgreSQL database.

## Stack
- Backend: FastAPI + SQLAlchemy Core reflection
- Frontend: React + Vite
- Database: PostgreSQL
- Role-based JWT authentication

## Important database note
This project discovers tables, columns, and primary keys from your existing PostgreSQL database at runtime. Records are viewable for every discovered table. Writes are limited to tables listed in `CRUD_TABLES` in `backend/.env`.

The dark main dashboard includes date, country, difficulty, and language filters; platform KPIs; and entity-wise activity, problems, developer, contest, hiring, language, engagement, and moderation charts. Analytics are derived from reflected columns and relationships, and unavailable links are explained in the dashboard instead of being inferred. It does **not** create or replace your database schema.

## Requirements
- Python 3.10+
- Node.js 18+
- PostgreSQL database with your existing schema

## Authentication and developer platform
The application has one administrator account configured with `ADMIN_USERNAME` and `ADMIN_PASSWORD`; administrator accounts cannot be created through the public UI. Companies can register using the Company Portal and receive a separate `company` JWT role. The development/demo defaults are username `admin` and password `admin`; change both before deployment. Developers can create their own accounts, but they cannot access administrator CRUD, analytics, or SQL APIs.

The backend signs short-lived HS256 bearer tokens using `AUTH_SECRET`. Set it to a randomly generated secret of at least 32 characters; for example, in PowerShell:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

The frontend stores the bearer token in `sessionStorage`, which limits its lifetime to the browser tab session but remains accessible to JavaScript. Use HTTPS in deployment and do not treat demo credentials or a frontend token as production-grade secret storage.

Developer passwords are stored as PBKDF2 hashes in a separate `developer_auth_accounts` table. Before enabling the platform on an existing database, apply any migrations in `backend/migrations` that have not already been applied, in numeric order, using pgAdmin or `psql`. Do not rerun migrations already applied, including `003_user_platform_relations.sql` and `005_pending_submissions.sql`. Apply `006_company_auth_accounts.sql` once to enable company login. The app does not create or alter the schema automatically. The auth table is hidden from the management tables and unavailable in the SQL query tool.

The developer platform reads the existing developer, problem, tag, solve, submission, language, and contest records. Each account is linked to one developer profile. Developers can browse and filter problems, see public (non-hidden) examples, review only their own submissions and statistics, update their display name/country, join upcoming contests, and view an aggregate leaderboard. Submitting code only stores it with `PENDING` status: **this project has no code execution or judging service**, and a saved submission does not mark a problem solved.

Authentication endpoints:
- `POST /api/auth/login` — accepts `username` and `password`, returns a bearer token and the admin or developer identity.
- `POST /api/auth/signup` — creates a developer account and linked profile; requires `username` (an email address), `full_name`, `country`, and a password of at least 12 characters.
- `GET /api/auth/me` — returns the authenticated identity.
- `GET /api/developer/me` — returns the signed-in developer's own account profile.

Developer platform endpoints (developer token required):
- `GET /api/problems` and `GET /api/problems/{problem_id}` — browse, filter, and read problems and public examples.
- `GET /api/languages` — available submission languages.
- `POST /api/submissions`, `GET /api/submissions/me`, and `GET /api/submissions/{submission_id}` — save code as not-evaluated, and view only the signed-in developer's submissions.
- `GET /api/user/dashboard`, `/api/user/activity`, `/api/user/analytics`, and `/api/user/profile`; `PATCH /api/user/profile` — personal data and profile.
- `GET /api/leaderboard`, `GET /api/contests`, and `POST /api/contests/{contest_id}/join`.

Administrator management APIs require an admin token; developer APIs require a developer token; `/api/company/*` endpoints require a company token. `GET /api/health`, login, developer signup, and company signup are public.\n\nCompany portal endpoints:\n- `POST /api/auth/company-signup` — creates a company profile and linked password account.\n- `GET /api/company/me` and `GET /api/company/dashboard` — company profile and company-owned assessment metrics.\n- `GET /api/company/options` — available developers and programming problems for assignment.\n- `POST /api/company/assessments` — creates an assessment, links selected problems, and assigns selected developers.\n- `GET /api/company/assessments/{assessment_id}/participants` — lists participants for an assessment owned by the signed-in company.

## 1. Configure backend
Open PowerShell in the project folder:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set the database URL and a strong `AUTH_SECRET`:

```env
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/YOUR_DATABASE
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
AUTH_SECRET=PASTE_A_RANDOM_SECRET_HERE
AUTH_TOKEN_TTL=3600
```

Use your actual database name, username, password, host, and port. The `admin/admin` defaults are for local development/demo use only.

## 2. Start backend
From `backend` with virtual environment activated:

```powershell
uvicorn app.main:app --reload
```

Backend: http://127.0.0.1:8000  
Swagger API docs: http://127.0.0.1:8000/docs

## 3. Configure and start frontend
Open a **second PowerShell** window:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Frontend: http://localhost:5173

## 4. Run commands after first setup

Terminal 1:
```powershell
cd leetcode-management-system\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Terminal 2:
```powershell
cd leetcode-management-system\frontend
npm run dev
```

## API overview
- `GET /api/health`
- `GET /api/tables`
- `GET /api/data/{table}?skip=0&limit=20`
- `POST /api/data/{table}`
- `PUT /api/data/{table}/{primary_key_json}`
- `DELETE /api/data/{table}/{primary_key_json}`
- `GET /api/analytics/overview`
- `GET /api/analytics/problems`
- `GET /api/analytics/submissions`
- `GET /api/analytics/distributions`
- `GET /api/analytics/dashboard?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&country=...&difficulty=...&language_id=...`

The dashboard endpoint returns filtered KPIs, chart series, and available filter options. Some problem-level submission and contributor reports are not possible with the supplied schema because `submission.problem_id`, `discussion.developer_id`, and a report reporter ID are not defined.

For update/delete, `primary_key_json` is URL-encoded JSON. The frontend constructs this automatically.

## Troubleshooting
- `relation does not exist`: check PostgreSQL database and exact table names.
- `No primary key`: that table cannot be edited safely until its real key is defined; it will be listed but CRUD actions will be disabled.
- PowerShell blocks activation: run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again.
- Records are view-only unless their table is included in `CRUD_TABLES`; restart the backend after changing the setting.
- CORS: the default configuration permits both `http://localhost:5173` and `http://127.0.0.1:5173`.
- If the dashboard says the database is unavailable, confirm `backend/.env` contains your real `DATABASE_URL`, PostgreSQL is running, and the backend is started before opening the frontend.
- If the backend refuses to start, verify `AUTH_SECRET` is set to a random value at least 32 characters long.
- Do not commit `.env` or publish database credentials, admin credentials, or the signing secret to GitHub.

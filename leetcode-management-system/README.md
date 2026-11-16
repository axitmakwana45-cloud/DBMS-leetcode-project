# LeetCode Management System

A schema-aware CRUD and analytics application for the existing LeetCode Management System PostgreSQL database.

## Stack
- Backend: FastAPI + SQLAlchemy Core reflection
- Frontend: React + Vite
- Database: PostgreSQL
- JWT-based administrator authentication

## Important database note
This project discovers tables, columns, and primary keys from your existing PostgreSQL database at runtime. Records are viewable for every discovered table. Writes are limited to tables listed in `CRUD_TABLES` in `backend/.env`.

The dark main dashboard includes date, country, difficulty, and language filters; platform KPIs; and entity-wise activity, problems, developer, contest, hiring, language, engagement, and moderation charts. Analytics are derived from reflected columns and relationships, and unavailable links are explained in the dashboard instead of being inferred. It does **not** create or replace your database schema.

## Requirements
- Python 3.10+
- Node.js 18+
- PostgreSQL database with your existing schema

## Authentication
The application has one administrator account configured with `ADMIN_USERNAME` and `ADMIN_PASSWORD`; administrator accounts cannot be created through the public UI. The development/demo defaults are username `admin` and password `admin`; change both before deployment. Developers can create their own accounts and sign in, but developer accounts only see a limited profile page and cannot access administrator CRUD, analytics, or SQL APIs.

The backend signs short-lived HS256 bearer tokens using `AUTH_SECRET`. Set it to a randomly generated secret of at least 32 characters; for example, in PowerShell:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

The frontend stores the bearer token in `sessionStorage`, which limits its lifetime to the browser tab session but remains accessible to JavaScript. Use HTTPS in deployment and do not treat demo credentials or a frontend token as production-grade secret storage.

Developer passwords are stored as PBKDF2 hashes in a separate `developer_auth_accounts` table. Before enabling developer signup, apply `backend/migrations/001_developer_auth_accounts.sql` to the configured PostgreSQL database using pgAdmin or `psql`. The app does not create this table automatically. It is hidden from the management tables and unavailable in the SQL query tool.

Authentication endpoints:
- `POST /api/auth/login` — accepts `username` and `password`, returns a bearer token and the admin or developer identity.
- `POST /api/auth/signup` — creates a developer account only; usernames are normalized to lowercase and passwords must contain at least 12 characters.
- `GET /api/auth/me` — returns the authenticated identity.
- `GET /api/developer/me` — returns the signed-in developer's own account profile.
- Administrator management APIs require an admin token. Developer tokens are restricted to the developer profile endpoint. `GET /api/health`, login, and developer signup are public.

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

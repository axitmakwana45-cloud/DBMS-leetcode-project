import React, { useEffect, useMemo, useState } from "react";
import { BarChart, Bar, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import DeveloperPlatform from "./DeveloperPlatform.jsx";
import { request } from "./services/api.js";

const money = (value) => (value === null || value === undefined ? "—" : value);
const defaultQuery = `SELECT COUNT(*) AS total_rows FROM developer;`;

const sqlExamples = [
  { label: "Developer count", sql: "SELECT COUNT(*) AS total_developers FROM developer;" },
  { label: "Problems by difficulty", sql: "SELECT difficulty, COUNT(*) AS total FROM programming_problem GROUP BY difficulty ORDER BY total DESC;" },
  { label: "Recent contests", sql: "SELECT * FROM contest ORDER BY start_time DESC LIMIT 10;" },
  { label: "Open reports", sql: "SELECT * FROM report WHERE status = 'OPEN' LIMIT 20;" },
];

const adminModules = [
  "Developer",
  "Programming Problem",
  "Company",
  "Contest",
  "Submission",
  "Assessment",
  "Badge",
  "Tag",
  "Test Case",
  "Editorial",
  "Report",
  "Notification",
];

export default function App() {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState("checking");
  const [authScreen, setAuthScreen] = useState("login");
  const [signupNotice, setSignupNotice] = useState("");

  useEffect(() => {
    let active = true;
    const handleUnauthorized = () => {
      sessionStorage.removeItem("adminToken");
      setUser(null);
      setAuthStatus("unauthenticated");
    };
    window.addEventListener("admin:unauthorized", handleUnauthorized);

    if (!sessionStorage.getItem("adminToken")) {
      setAuthStatus("unauthenticated");
    } else {
      request("/api/auth/me")
        .then((currentUser) => {
          if (active) {
            setUser(currentUser);
            setAuthStatus("authenticated");
          }
        })
        .catch(() => {
          if (active) {
            sessionStorage.removeItem("adminToken");
            setAuthStatus("unauthenticated");
          }
        });
    }

    return () => {
      active = false;
      window.removeEventListener("admin:unauthorized", handleUnauthorized);
    };
  }, []);

  async function signIn(username, password) {
    const result = await request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }, true);
    if (!result.access_token || result.token_type?.toLowerCase() !== "bearer") {
      throw new Error("The server returned an invalid login response.");
    }

    sessionStorage.setItem("adminToken", result.access_token);
    try {
      const currentUser = await request("/api/auth/me");
      setUser(currentUser);
      setAuthStatus("authenticated");
    } catch (error) {
      sessionStorage.removeItem("adminToken");
      throw error;
    }
  }

  async function signUp(profile, password) {
    const companyMode = authScreen === "company-signup";
    await request(companyMode ? "/api/auth/company-signup" : "/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(companyMode ? {
        email: profile.email,
        company_name: profile.companyName,
        industry: profile.industry,
        website: profile.website,
        location: profile.location,
        password,
      } : {
        username: profile.email,
        full_name: profile.fullName,
        country: profile.country,
        password,
      }),
    }, true);
    setSignupNotice(companyMode ? "Company account created. Sign in with your company email." : "Developer account created. Sign in with your new credentials.");
    setAuthScreen("login");
  }

  function signOut() {
    sessionStorage.removeItem("adminToken");
    setUser(null);
    setAuthStatus("unauthenticated");
  }

  if (authStatus === "checking") {
    return <div className="authLoading" role="status">Verifying session…</div>;
  }
  if (authStatus !== "authenticated") {
    if (authScreen === "signup") {
      return <Signup onSignup={signUp} onShowLogin={() => setAuthScreen("login")} />;
    }
    if (authScreen === "company-signup") {
      return <CompanySignup onSignup={signUp} onShowLogin={() => setAuthScreen("login")} />;
    }
    return <Login
      onLogin={signIn}
      onShowSignup={() => { setSignupNotice(""); setAuthScreen("signup"); }}
      onShowCompanySignup={() => { setSignupNotice(""); setAuthScreen("company-signup"); }}
      notice={signupNotice}
    />;
  }
  if (user.role === "developer") {
    return <DeveloperPlatform user={user} onLogout={signOut} />;
  }
  if (user.role === "company") {
    return <CompanyPortal user={user} onLogout={signOut} />;
  }
  return <DashboardApp admin={user} onLogout={signOut} />;
}

function Login({ onLogin, onShowSignup, onShowCompanySignup, notice }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (loginError) {
      setError(loginError.message || "Unable to sign in. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginCard">
        <div className="loginBrandIcon">LC</div>
        <div className="eyebrow">LEETCODE MANAGEMENT STUDIO</div>
        <h1>Welcome back</h1>
        <p className="loginSubtitle">Administrator, developer or company sign in</p>
        {notice && <div className="loginSuccess" role="status">{notice}</div>}
        <form onSubmit={submit}>
          <label className="loginField">
            <span>Username</span>
            <input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label className="loginField">
            <span>Password</span>
            <div className="passwordInput">
              <input autoComplete="current-password" required type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} />
              <button type="button" className="passwordToggle" onClick={() => setShowPassword((shown) => !shown)} aria-label={showPassword ? "Hide password" : "Show password"}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>
          {error && <div className="loginError" role="alert">{error}</div>}
          <button className="loginSubmit" type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <button className="authSwitch" type="button" onClick={onShowSignup}>Create a developer account</button>
        <button className="authSwitch" type="button" onClick={onShowCompanySignup}>Register your company</button>
        <div className="loginFootnote"><span /> Admin accounts are managed outside public signup</div>
      </section>
    </main>
  );
}

function Signup({ onSignup, onShowLogin }) {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [country, setCountry] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await onSignup({
        email: username.trim().toLowerCase(),
        fullName: fullName.trim(),
        country: country.trim(),
      }, password);
    } catch (signupError) {
      setError(signupError.message || "Unable to create the account. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginCard">
        <div className="loginBrandIcon">LC</div>
        <div className="eyebrow">DEVELOPER ACCESS</div>
        <h1>Create account</h1>
        <p className="loginSubtitle">Create a developer profile. Admin access is not available here.</p>
        <form onSubmit={submit}>
          <label className="loginField">
            <span>Email address</span>
            <input autoComplete="email" autoCapitalize="none" required type="email" maxLength="254" value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label className="loginField">
            <span>Display name</span>
            <input autoComplete="name" required maxLength="100" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          </label>
          <label className="loginField">
            <span>Country</span>
            <input autoComplete="country-name" required maxLength="60" value={country} onChange={(event) => setCountry(event.target.value)} />
          </label>
          <label className="loginField">
            <span>Password <small>(at least 12 characters)</small></span>
            <input autoComplete="new-password" required minLength="12" maxLength="128" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label className="loginField">
            <span>Confirm password</span>
            <input autoComplete="new-password" required minLength="12" maxLength="128" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
          </label>
          {error && <div className="loginError" role="alert">{error}</div>}
          <button className="loginSubmit" type="submit" disabled={loading}>
            {loading ? "Creating account…" : "Create developer account"}
          </button>
        </form>
        <button className="authSwitch" type="button" onClick={onShowLogin}>Back to sign in</button>
        <div className="loginFootnote"><span /> Only developer accounts can be created here</div>
      </section>
    </main>
  );
}

function CompanySignup({ onSignup, onShowLogin }) {
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("");
  const [website, setWebsite] = useState("");
  const [location, setLocation] = useState("");
  const [country, setCountry] = useState("India");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) return setError("Passwords do not match.");
    setLoading(true);
    try {
      await onSignup({ email: email.trim().toLowerCase(), companyName: companyName.trim(), industry: industry.trim(), website: website.trim(), location: location.trim(), country: country.trim() }, password);
    } catch (err) {
      setError(err.message || "Unable to create company account.");
    } finally { setLoading(false); }
  }
  return <main className="loginPage"><section className="loginCard">
    <div className="loginBrandIcon">LC</div><div className="eyebrow">COMPANY ACCESS</div>
    <h1>Register company</h1><p className="loginSubtitle">Create a company account to manage developer assessments.</p>
    <form onSubmit={submit}>
      <label className="loginField"><span>Company name</span><input required minLength="2" maxLength="120" value={companyName} onChange={e => setCompanyName(e.target.value)} /></label>
      <label className="loginField"><span>Work email</span><input required type="email" maxLength="254" value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label className="loginField"><span>Industry</span><input required minLength="2" maxLength="100" placeholder="e.g. Software / IT" value={industry} onChange={e => setIndustry(e.target.value)} /></label>
      <label className="loginField"><span>Website (optional)</span><input type="url" maxLength="255" value={website} onChange={e => setWebsite(e.target.value)} /></label>
      <label className="loginField"><span>Headquarters / Location (optional)</span><input maxLength="160" value={location} onChange={e => setLocation(e.target.value)} /></label>
      <label className="loginField"><span>Country</span><input required minLength="2" maxLength="60" autoComplete="country-name" value={country} onChange={e => setCountry(e.target.value)} /></label>
      <label className="loginField"><span>Password (minimum 12 characters)</span><input required type="password" minLength="12" maxLength="128" value={password} onChange={e => setPassword(e.target.value)} /></label>
      <label className="loginField"><span>Confirm password</span><input required type="password" minLength="12" maxLength="128" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} /></label>
      {error && <div className="loginError" role="alert">{error}</div>}
      <button className="loginSubmit" disabled={loading}>{loading ? "Creating company…" : "Create company account"}</button>
    </form>
    <button className="authSwitch" type="button" onClick={onShowLogin}>Back to sign in</button>
  </section></main>;
}

function CompanyPortal({ user, onLogout }) {
  const [dashboard, setDashboard] = useState(null);
  const [options, setOptions] = useState({ developers: [], problems: [] });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [duration, setDuration] = useState("60");
  const [problemIds, setProblemIds] = useState([]);
  const [developerIds, setDeveloperIds] = useState([]);
  const [participants, setParticipants] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [d, o] = await Promise.all([request("/api/company/dashboard"), request("/api/company/options")]);
      setDashboard(d); setOptions(o); setError("");
    } catch (err) { setError(err.message || "Unable to load company dashboard."); }
  }
  useEffect(() => { load(); }, []);

  function toggle(setter, current, id) {
    setter(current.includes(id) ? current.filter(value => value !== id) : [...current, id]);
  }
  async function createAssessment(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await request("/api/company/assessments", { method: "POST", body: JSON.stringify({
        title, description, start_at: new Date(startAt).toISOString(), end_at: new Date(endAt).toISOString(),
        duration_minutes: Number(duration), problem_ids: problemIds, developer_ids: developerIds
      })});
      setNotice("Assessment created and selected developers assigned.");
      setShowForm(false); setTitle(""); setDescription(""); setProblemIds([]); setDeveloperIds([]);
      await load();
    } catch (err) { setError(err.message || "Could not create assessment."); }
    finally { setBusy(false); }
  }
  async function viewParticipants(id) {
    try { const result = await request(`/api/company/assessments/${id}/participants`); setParticipants({ id, ...result }); }
    catch (err) { setError(err.message); }
  }
  return <main className="userLayout" data-theme="dark"><div className="userMain">
    <header className="userTopbar"><div><div className="eyebrow">COMPANY WORKSPACE</div><h1>Assessment Management</h1><p>{user.username}</p></div><button className="ghost" onClick={onLogout}>Sign out</button></header>
    <div className="userPageContent">
      {error && <div className="userError" role="alert">{error}</div>}
      {notice && <div className="loginSuccess" role="status">{notice}</div>}
      <div className="moduleHeader"><div><h2>Company dashboard</h2><p>Manage assessments, assigned developers and performance.</p></div><button className="primary" onClick={() => setShowForm(value => !value)}>＋ Create assessment</button></div>
      {dashboard && <div className="userStatsGrid">
        <UserStat label="Total assessments" value={dashboard.total_assessments} icon="▣" />
        <UserStat label="Active" value={dashboard.active_assessments} icon="◉" />
        <UserStat label="Upcoming" value={dashboard.upcoming_assessments} icon="◷" />
        <UserStat label="Completed" value={dashboard.completed_assessments} icon="✓" />
        <UserStat label="Assigned developers" value={dashboard.assigned_developers} icon="♙" />
        <UserStat label="Average score" value={dashboard.average_score ?? "—"} icon="%" />
        <UserStat label="Completion rate" value={`${dashboard.completion_rate}%`} icon="↗" />
      </div>}
      {dashboard?.assessment_analytics?.length > 0 && <div className="userTwoColumns">
        <section className="userPanel"><SectionTitle title="Participants by assessment" subtitle="Developer assignments across your assessments." /><div style={{ height: 250 }}>
          <ResponsiveContainer width="100%" height="100%"><BarChart data={dashboard.assessment_analytics}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="title" tick={{ fontSize: 9 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="participants" fill="#526fe5" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer>
        </div></section>
        <section className="userPanel"><SectionTitle title="Average assessment score" subtitle="Based on scores recorded in assessment participation." /><div style={{ height: 250 }}>
          <ResponsiveContainer width="100%" height="100%"><BarChart data={dashboard.assessment_analytics}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="title" tick={{ fontSize: 9 }} /><YAxis /><Tooltip /><Bar dataKey="average_score" fill="#2bbf9b" radius={[5, 5, 0, 0]} /></BarChart></ResponsiveContainer>
        </div></section>
      </div>}
      {showForm && <section className="userPanel">
        <SectionTitle title="Create assessment" subtitle="Choose problems, schedule the assessment and assign developers." />
        <form className="profileEditForm companyAssessmentForm" onSubmit={createAssessment}>
          <label className="loginField"><span>Assessment title</span><input required minLength="2" maxLength="160" value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="loginField"><span>Description</span><textarea rows="3" value={description} onChange={e => setDescription(e.target.value)} /></label>
          <div className="userTwoColumns">
            <label className="loginField"><span>Start date and time</span><input required type="datetime-local" value={startAt} onChange={e => setStartAt(e.target.value)} /></label>
            <label className="loginField"><span>End date and time</span><input required type="datetime-local" value={endAt} onChange={e => setEndAt(e.target.value)} /></label>
          </div>
          <label className="loginField"><span>Duration (minutes)</span><input required type="number" min="1" max="1440" value={duration} onChange={e => setDuration(e.target.value)} /></label>
          <h3>Programming problems ({problemIds.length} selected)</h3>
          <div className="selectionList">{options.problems.map(problem => <label key={problem.id}><input type="checkbox" checked={problemIds.includes(problem.id)} onChange={() => toggle(setProblemIds, problemIds, problem.id)} /> {problem.title} <small>#{problem.id}</small></label>)}</div>
          <h3>Assign developers ({developerIds.length} selected)</h3>
          <div className="selectionList">{options.developers.map(dev => <label key={dev.id}><input type="checkbox" checked={developerIds.includes(dev.id)} onChange={() => toggle(setDeveloperIds, developerIds, dev.id)} /> {dev.name} <small>#{dev.id}</small></label>)}</div>
          <div className="modalFoot"><button type="button" className="ghost" onClick={() => setShowForm(false)}>Cancel</button><button className="primary" disabled={busy || !problemIds.length || !developerIds.length}>{busy ? "Creating…" : "Create and assign"}</button></div>
        </form>
      </section>}
      <section className="userPanel">
        <SectionTitle title="Your assessments" subtitle="Only assessments owned by this company are shown." />
        {dashboard?.assessments?.length ? <div className="userTableScroll"><table className="userTable"><thead><tr><th>ID</th><th>Assessment</th><th>Start</th><th>End</th><th>Actions</th></tr></thead><tbody>
          {dashboard.assessments.map(item => <tr key={item.assessment_id || item.id}><td>{item.assessment_id || item.id}</td><td>{item.title || item.assessment_name || item.name}</td><td>{item.start_at || item.start_time || item.start_date || "—"}</td><td>{item.end_at || item.end_time || item.end_date || "—"}</td><td><button className="ghost" onClick={() => viewParticipants(item.assessment_id || item.id)}>Participants</button></td></tr>)}
        </tbody></table></div> : <p>No assessments created yet.</p>}
      </section>
      {participants && <section className="userPanel"><SectionTitle title={`Participants for assessment #${participants.id}`} /><div className="userTableScroll"><table className="userTable"><thead><tr>{Object.keys(participants.items[0] || {}).map(key => <th key={key}>{key}</th>)}</tr></thead><tbody>{participants.items.map((row, index) => <tr key={index}>{Object.values(row).map((value, i) => <td key={i}>{value == null ? "—" : String(value)}</td>)}</tr>)}</tbody></table></div></section>}
      <button className="ghost" onClick={load}>↻ Refresh dashboard</button>
    </div>
  </div></main>;
}

function DashboardApp({ admin, onLogout }) {
  const [page, setPage] = useState("Dashboard");
  const [tables, setTables] = useState([]);
  const [table, setTable] = useState("programming_problem");
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pageNo, setPageNo] = useState(0);
  const [limit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState({ tables: [] });
  const [dashboardData, setDashboardData] = useState({ kpis: {}, charts: {}, filters: { countries: [], languages: [] }, limitations: [] });
  const [dateRange, setDateRange] = useState("all");
  const [countryFilter, setCountryFilter] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState("");
  const [languageFilter, setLanguageFilter] = useState("");
  const [connection, setConnection] = useState("checking");
  const [modal, setModal] = useState(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All");
  const [querySql, setQuerySql] = useState(defaultQuery);
  const [queryResult, setQueryResult] = useState(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState("");

  const current = tables.find((item) => item.name === table) || tables[0] || null;
  const cols = current?.columns || [];
  const hasDifficulty = cols.some((column) => column.name.toLowerCase().includes("difficulty"));

  async function loadTables() {
    try {
      const [health, data] = await Promise.all([request("/api/health"), request("/api/tables")]);
      const safe = data.filter((item) => item.exists);
      setTables(safe);
      setConnection(health.status === "ok" ? "connected" : "disconnected");
      if (safe.length && !safe.some((item) => item.name === table)) {
        setTable(safe[0].name);
      }
    } catch (e) {
      setConnection("disconnected");
      setError(`Database connection failed. Check backend/.env and start the API: ${e.message}`);
    }
  }

  async function loadDashboard() {
    try {
      const params = new URLSearchParams();
      if (dateRange !== "all") {
        const from = new Date();
        from.setDate(from.getDate() - Number(dateRange));
        params.set("date_from", from.toISOString().slice(0, 10));
      }
      if (countryFilter) params.set("country", countryFilter);
      if (difficultyFilter) params.set("difficulty", difficultyFilter);
      if (languageFilter) params.set("language_id", languageFilter);
      const dashboard = await request(`/api/analytics/dashboard?${params.toString()}`);
      setDashboardData(dashboard);
    } catch (e) {
      setConnection("disconnected");
      setError(`Could not load dashboard analytics: ${e.message}`);
    }
  }

  async function loadOverview() {
    try {
      setOverview(await request("/api/analytics/overview"));
    } catch (e) {
      setError(`Could not load table totals: ${e.message}`);
    }
  }

  async function loadRows() {
    setLoading(true);
    setError("");
    try {
      const data = await request(`/api/data/${table}?skip=${pageNo * limit}&limit=${limit}`);
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setRows([]);
      setTotal(0);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function runCustomQuery() {
    setQueryLoading(true);
    setQueryError("");
    try {
      const result = await request("/api/query", {
        method: "POST",
        body: JSON.stringify({ sql: querySql, limit: 100 }),
      });
      setQueryResult(result);
    } catch (e) {
      setQueryError(e.message);
      setQueryResult(null);
    } finally {
      setQueryLoading(false);
    }
  }

  useEffect(() => {
    loadTables();
    loadOverview();
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [dateRange, countryFilter, difficultyFilter, languageFilter]);

  useEffect(() => {
    if (page === "Records") {
      loadRows();
    }
  }, [page, table, pageNo]);

  const visibleRows = useMemo(() => {
    return rows.filter((row) => {
      const matchesSearch = !search || Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(search.toLowerCase()));
      const difficultyCell = Object.entries(row).find(([key]) => key.toLowerCase().includes("difficulty"));
      const matchesFilter = filter === "All" || (difficultyCell && String(difficultyCell[1]).toLowerCase() === filter.toLowerCase());
      return matchesSearch && matchesFilter;
    });
  }, [rows, search, filter]);

  function keyFor(row) {
    const keys = current?.primary_key || [];
    return Object.fromEntries(keys.map((key) => [key, row[key]]));
  }

  async function saveRecord(values) {
    try {
      if (modal.mode === "create") {
        await request(`/api/data/${table}`, { method: "POST", body: JSON.stringify(values) });
      } else {
        const key = encodeURIComponent(JSON.stringify(keyFor(modal.row)));
        await request(`/api/data/${table}/${key}`, { method: "PUT", body: JSON.stringify(values) });
      }
      setModal(null);
      await loadRows();
      await loadDashboard();
      await loadOverview();
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteRecord(row) {
    if (!confirm("Delete this record? This action cannot be undone.")) return;
    try {
      const key = encodeURIComponent(JSON.stringify(keyFor(row)));
      await request(`/api/data/${table}/${key}`, { method: "DELETE" });
      await loadRows();
      await loadDashboard();
      await loadOverview();
    } catch (e) {
      setError(e.message);
    }
  }

  const statCards = [
    { label: "Total Developers", value: dashboardData.kpis.developers ?? 0, icon: "◎" },
    { label: "Total Problems", value: dashboardData.kpis.problems ?? 0, icon: "⌘" },
    { label: "Total Submissions", value: dashboardData.kpis.submissions ?? 0, icon: "↗" },
    { label: "Acceptance Rate", value: `${dashboardData.kpis.acceptance_rate ?? 0}%`, icon: "✓" },
    { label: "Active Contests", value: dashboardData.kpis.active_contests ?? 0, icon: "◷" },
    { label: "Open Reports", value: dashboardData.kpis.open_reports ?? 0, icon: "!" },
  ];
  const entityCounts = overview.tables || [];
  const managementTables = tables.length ? tables : adminModules.map((name) => ({ name, editable: false }));
  const analysisGroups = [
    { title: "Platform Activity", charts: [["daily_submissions", "Daily Submissions", "line"], ["submission_status", "Submission Status Breakdown", "pie"]] },
    { title: "Problem Content", charts: [["problems_by_difficulty", "Problems by Difficulty", "pie"], ["acceptance_by_difficulty", "Acceptance Rate by Difficulty", "bar"], ["problems_per_tag", "Problems per Tag", "bar"], ["test_case_visibility", "Hidden vs Visible Test Cases", "pie"], ["editorial_coverage", "Editorial Coverage", "pie"], ["solves_attempts", "Average Solve Attempts per Problem", "bar"], ["hardest_problems", "Hardest Problems · Lowest Acceptance", "bar"]] },
    { title: "Developers", charts: [["rating_distribution", "Developer Rating Distribution", "bar"], ["developer_country", "Developers by Country", "bar"], ["developer_signups", "New Developers", "line"], ["admin_roles", "Administrator Roles", "pie"], ["top_solvers", "Top Solvers", "bar"], ["solves_over_time", "Solves Over Time", "line"]] },
    { title: "Contests", charts: [["contest_status", "Contests by Status", "pie"], ["contests_timeline", "Contests Timeline", "line"], ["contest_participants", "Participants per Contest", "bar"], ["contest_problem_points", "Points per Contest Problem", "bar"], ["leaderboard_top", "Contest Leaderboard · Top 10", "bar"]] },
    { title: "Company Assessments", charts: [["company_industry", "Companies by Industry", "bar"], ["company_country", "Companies by Country", "bar"], ["company_onboarding", "Company Onboarding Trend", "line"], ["assessment_status", "Candidate Status Funnel", "bar"], ["assessments_per_company", "Assessments per Company", "bar"], ["assessment_points", "Assessment Points by Problem", "bar"], ["assessment_avg_score", "Average Score per Assessment", "bar"]] },
    { title: "Languages & Engagement", charts: [["language_versions", "Versions per Language", "bar"], ["language_popularity", "Language Popularity", "bar"], ["language_success_rate", "Language Success Rate", "bar"], ["runtime_by_language", "Average Runtime by Language", "bar"], ["badge_popularity", "Most Earned Badges", "bar"], ["badge_earned_over_time", "Badges Earned Over Time", "line"], ["notification_types", "Notifications by Type", "pie"], ["notification_read", "Notifications Read vs Unread", "pie"]] },
    { title: "Moderation", charts: [["reports_status", "Reports by Status", "pie"], ["reports_resolved_by_admin", "Reports Resolved per Admin", "bar"], ["most_discussed", "Most Discussed Problems", "bar"], ["top_upvoted_discussions", "Top Upvoted Discussions", "bar"]] },
  ];
  const dashboardCharts = dashboardData.charts || {};

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandIcon">LC</div>
          <div>
            <b>LeetCode</b>
            <small>Management Studio</small>
          </div>
        </div>

        <div className="navLabel">WORKSPACE</div>
        {['Dashboard', 'Analytics', 'Management', 'Records', 'SQL Query'].map((item) => (
          <button
            key={item}
            className={`nav ${page === item ? 'active' : ''}`}
            title={item}
            onClick={() => {
              setPage(item);
              setError("");
            }}
          >
            <span>{item === 'Dashboard' ? '▦' : item === 'Analytics' ? '◫' : item === 'Management' ? '▤' : item === 'Records' ? '▣' : '⌘'}</span>
            {item}
          </button>
        ))}

        <div className="sideNote">
          <b>Database connected app</b>
          <p>Admin dashboard, analytics, management and SQL reports for the LeetCode schema.</p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">LEETCODE MANAGEMENT SYSTEM</div>
            <h1>{page}</h1>
          </div>
          <div className="topbarRight">
            <div className={`status ${connection === "connected" ? "online" : connection === "disconnected" ? "offline" : ""}`}>
              <i /> {connection === "connected" ? "Database connected" : connection === "disconnected" ? "Database unavailable" : "Checking database"}
            </div>
            <div className="adminControls">
              <div className="adminIdentity"><strong>{admin.username}</strong><span>Administrator</span></div>
              <button className="ghost logoutButton" onClick={onLogout}>Log out</button>
            </div>
          </div>
        </header>

        {error && (
          <div className="error">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        {page === 'Dashboard' && (
          <section>
            <div className="dashboardTitle">
              <div>
                <div className="eyebrow">PLATFORM OVERVIEW</div>
                <h2>LeetCode Management System</h2>
                <p>Live performance, community activity, contests and hiring analytics.</p>
              </div>
              <button className="ghost" onClick={() => { loadTables(); loadDashboard(); loadOverview(); }}>↻ Refresh dashboard</button>
            </div>

            <div className="dashboardFilters">
              <label>Date range<select value={dateRange} onChange={(event) => setDateRange(event.target.value)}><option value="all">All time</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="365">Last year</option></select></label>
              <label>Country<select value={countryFilter} onChange={(event) => setCountryFilter(event.target.value)}><option value="">All countries</option>{dashboardData.filters?.countries?.map((country) => <option key={country} value={country}>{country}</option>)}</select></label>
              <label>Difficulty<select value={difficultyFilter} onChange={(event) => setDifficultyFilter(event.target.value)}><option value="">All difficulties</option><option value="Easy">Easy</option><option value="Medium">Medium</option><option value="Hard">Hard</option></select></label>
              <label>Language<select value={languageFilter} onChange={(event) => setLanguageFilter(event.target.value)}><option value="">All languages</option>{dashboardData.filters?.languages?.map((language) => <option key={language.id} value={language.id}>{language.name}</option>)}</select></label>
            </div>

            <div className="stats">
              {statCards.map((card) => (
                <Stat key={card.label} label={card.label} value={money(card.value)} icon={card.icon} />
              ))}
            </div>

            {dashboardData.limitations?.length > 0 && (
              <div className="schemaNotice">
                <strong>Schema-aware notes</strong>
                {dashboardData.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
              </div>
            )}

            {analysisGroups.map((group) => (
              <section className="dashboardSection" key={group.title}>
                <div className="sectionHeading"><span>{group.title}</span><i /></div>
                <div className="dashboardChartGrid">
                  {group.charts.map(([key, title, type]) => (
                    <DashboardChart key={key} title={title} type={type} items={dashboardCharts[key] || []} />
                  ))}
                </div>
              </section>
            ))}
          </section>
        )}

        {page === 'Analytics' && (
          <section>
            <div className="panel moduleGrid">
              <div className="moduleHeader">
                <div>
                  <div className="eyebrow light dark">ANALYTICS</div>
                  <h3>Full platform analytics</h3>
                </div>
                <button className="ghost" onClick={() => { loadTables(); loadDashboard(); loadOverview(); }}>Refresh metrics</button>
              </div>

              <div className="miniGrid">
                {entityCounts.map((item) => (
                  <div className="miniCard" key={item.normalized_name}>
                    <span>{item.name.replaceAll("_", " ")}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))}
              </div>

              <div className="analysisGroupList">
                {analysisGroups.map((group) => (
                  <section className="dashboardSection" key={group.title}>
                    <div className="sectionHeading"><span>{group.title}</span><i /></div>
                    <div className="dashboardChartGrid">
                      {group.charts.map(([key, title, type]) => (
                        <DashboardChart key={key} title={title} type={type} items={dashboardCharts[key] || []} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          </section>
        )}

        {page === 'Management' && (
          <section>
            <div className="managementPanel panel">
              <div className="moduleHeader">
                <div>
                  <div className="eyebrow light dark">MANAGEMENT</div>
                  <h3>Schema modules</h3>
                </div>
                <button className="primary" onClick={() => setPage('Records')}>Open data explorer</button>
              </div>

              <div className="moduleCards">
                {managementTables.map((entry) => (
                  <div className="managementCard" key={entry.name}>
                    <span className={`chip ${entry.editable ? "" : "readOnlyChip"}`}>{entry.editable ? "Editable" : "Read only"}</span>
                    <h4>{entry.name.replaceAll("_", " ")}</h4>
                    <p>Explore live records{entry.editable ? " and manage this table." : " for this table."}</p>
                    <button className="ghost" onClick={() => { setTable(entry.name); setPageNo(0); setPage('Records'); }}>Open records</button>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {page === 'Records' && (
          <section>
            <div className="toolbar">
              <div className="selectWrap">
                <label>ENTITY</label>
                <select value={table} onChange={(event) => { setTable(event.target.value); setPageNo(0); setSearch(""); setFilter("All"); }}>
                  {tables.map((entry) => <option key={entry.name} value={entry.name}>{entry.name.replaceAll('_', ' ')}</option>)}
                </select>
              </div>

              <div className="searchWrap">
                <label>SEARCH CURRENT PAGE</label>
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search records..." />
              </div>

              {hasDifficulty && <div className="selectWrap smallSelect">
                <label>DIFFICULTY FILTER</label>
                <select value={filter} onChange={(event) => setFilter(event.target.value)}>
                  <option>All</option>
                  <option>Easy</option>
                  <option>Medium</option>
                  <option>Hard</option>
                </select>
              </div>}

              {current?.editable && <button className="primary addBtn" onClick={() => setModal({ mode: 'create' })}>＋ Add record</button>}
            </div>

            {!tables.length && <div className="hint">No tables loaded. Start the backend and configure a valid DATABASE_URL in backend/.env. See backend/.env.example.</div>}
            {current && !current?.exists && <div className="empty">Table not found in the connected database. Verify its name in backend/.env.</div>}
            {current && !current.editable && <div className="hint">This table is view-only. Add it to CRUD_TABLES in backend/.env and restart the API to enable edits.</div>}
            {current?.exists && !current.primary_key?.length && <div className="hint">This table has no declared primary key. Viewing is enabled; update/delete are disabled for safety.</div>}

            <div className="panel tablePanel">
              <div className="tableTitle">
                <div>
                  <h3>{table.replaceAll('_', ' ')}</h3>
                  <p>{total} total records · Showing current page</p>
                </div>
                <button className="ghost" onClick={loadRows}>↻ Refresh</button>
              </div>

              {loading ? (
                <div className="empty">Loading records…</div>
              ) : (
                <div className="tableScroll">
                  <table>
                    <thead>
                      <tr>
                        {cols.map((column) => <th key={column.name}>{column.name}</th>)}
                        <th>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((record, index) => (
                        <tr key={`${record?.id || index}-${index}`}>
                          {cols.map((column) => (
                            <td key={column.name} title={String(record[column.name] ?? '')}>
                              {record[column.name] === null ? <span className="null">NULL</span> : String(record[column.name] ?? '')}
                            </td>
                          ))}
                          <td>
                            <div className="actions">
                              {current?.editable ? <>
                                <button disabled={!current?.primary_key?.length} onClick={() => setModal({ mode: 'edit', row: record })}>Edit</button>
                                <button className="delete" disabled={!current?.primary_key?.length} onClick={() => deleteRecord(record)}>Delete</button>
                              </> : <span className="readOnlyText">Read only</span>}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!visibleRows.length && (
                        <tr>
                          <td colSpan={cols.length + 1}><div className="empty">No records found on this page.</div></td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="pagination">
                <span>Page {pageNo + 1} of {Math.max(1, Math.ceil(total / limit))}</span>
                <div>
                  <button className="ghost" disabled={pageNo === 0} onClick={() => setPageNo((prev) => prev - 1)}>Previous</button>
                  <button className="ghost" disabled={(pageNo + 1) * limit >= total} onClick={() => setPageNo((prev) => prev + 1)}>Next</button>
                </div>
              </div>
            </div>
          </section>
        )}

        {page === 'SQL Query' && (
          <section className="queryPage">
            <div className="panel queryPanel">
              <div className="queryHead">
                <div>
                  <h3>Read-only SQL studio</h3>
                  <p>Only SELECT queries are allowed. No writes, no schema changes.</p>
                </div>
                <button className="primary" onClick={runCustomQuery} disabled={queryLoading}>Run query</button>
              </div>

              <div className="queryExamples">
                {sqlExamples.map((example) => (
                  <button key={example.label} className="ghost" onClick={() => setQuerySql(example.sql)}>{example.label}</button>
                ))}
              </div>

              <textarea
                className="sqlTextarea"
                value={querySql}
                onChange={(event) => setQuerySql(event.target.value)}
                rows={12}
                placeholder="SELECT * FROM developer LIMIT 20;"
              />

              {queryError && <div className="error queryError">{queryError}</div>}
              {queryLoading && <div className="empty">Running query…</div>}

              {queryResult && (
                <div className="queryResultBox">
                  <div className="queryMeta">
                    <strong>{queryResult.row_count || 0} rows</strong>
                    <button className="ghost" onClick={() => downloadCsv(queryResult)}>Export CSV</button>
                  </div>

                  {queryResult.rows?.length ? (
                    <div className="tableScroll narrowTable">
                      <table>
                        <thead>
                          <tr>
                            {queryResult.columns.map((column) => <th key={column}>{column}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {queryResult.rows.map((row, index) => (
                            <tr key={`${index}-${Object.values(row).join('-')}`}>
                              {queryResult.columns.map((column) => (
                                <td key={`${column}-${index}`}>{row[column] === null ? <span className="null">NULL</span> : String(row[column] ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty">No rows returned.</div>
                  )}
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      {modal && <RecordModal mode={modal.mode} row={modal.row} columns={cols} onClose={() => setModal(null)} onSave={saveRecord} />}
    </div>
  );
}

function Stat({ label, value, icon }) {
  return (
    <div className="stat">
      <div className="statIcon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function DashboardChart({ title, type, items }) {
  const colors = ["#6d8dff", "#2dd4bf", "#f7b955", "#b794f6", "#f87187", "#53b5df"];
  const tooltipStyle = { background: "#111b2d", border: "1px solid #293852", borderRadius: 8, color: "#e8eefb" };
  return (
    <div className="panel dashboardChart">
      <div className="panelHead"><div><h3>{title}</h3></div></div>
      {items.length ? (
        <div className="chart">
          <ResponsiveContainer>
            {type === "pie" ? (
              <PieChart>
                <Pie data={items} dataKey="value" nameKey="label" outerRadius={88} label>
                  {items.map((item, index) => <Cell key={`${item.label}-${index}`} fill={colors[index % colors.length]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            ) : type === "line" ? (
              <LineChart data={items} margin={{ top: 10, right: 12, left: -12, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#29364c" />
                <XAxis dataKey="label" tick={{ fill: "#91a0b9", fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#91a0b9", fontSize: 10 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="value" stroke="#6d8dff" strokeWidth={2.5} dot={{ r: 3, fill: "#6d8dff" }} />
              </LineChart>
            ) : (
              <BarChart data={items} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#29364c" />
                <XAxis type="number" allowDecimals tick={{ fill: "#91a0b9", fontSize: 10 }} />
                <YAxis type="category" dataKey="label" width={125} interval={0} tick={{ fill: "#aebbd0", fontSize: 10 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="value" fill="#6d8dff" radius={[0, 5, 5, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      ) : <Empty text="No matching data is available for this chart in the connected schema." />}
    </div>
  );
}

function Empty({ text }) {
  return <div className="empty">{text}</div>;
}

function RecordModal({ mode, row, columns, onClose, onSave }) {
  const [values, setValues] = useState(() => {
    const initial = {};
    (columns || []).forEach((column) => {
      if (mode === 'create') {
        initial[column.name] = '';
      } else if (column.name in (row || {})) {
        initial[column.name] = row[column.name] ?? '';
      }
    });
    return initial;
  });

  function update(key, value) {
    setValues((old) => ({ ...old, [key]: value }));
  }

  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modalHead">
          <div>
            <h2>{mode === 'create' ? 'Add record' : 'Edit record'}</h2>
            <p>Fields are generated from the connected PostgreSQL table.</p>
          </div>
          <button onClick={onClose}>×</button>
        </div>

        <div className="formGrid">
          {(columns || []).map((column) => (
            <label className="field" key={column.name}>
              <span>{column.name}{column.nullable ? '' : ' *'} {column.primary_key ? '(PK)' : ''}</span>
              {column.type.toLowerCase().includes('bool') ? (
                <select disabled={mode === 'edit' && column.primary_key} value={String(values[column.name] ?? '')} onChange={(event) => update(column.name, event.target.value === '' ? null : event.target.value === 'true')}>
                  <option value="">Select</option>
                  <option value="true">True</option>
                  <option value="false">False</option>
                </select>
              ) : column.type.toLowerCase().includes('text') || column.type.toLowerCase().includes('json') ? (
                <textarea disabled={mode === 'edit' && column.primary_key} value={values[column.name] ?? ''} onChange={(event) => update(column.name, event.target.value)} rows="3" />
              ) : (
                <input
                  disabled={mode === 'edit' && column.primary_key}
                  type={column.type.toLowerCase().includes('int') || column.type.toLowerCase().includes('numeric') || column.type.toLowerCase().includes('float') ? 'number' : 'text'}
                  value={values[column.name] ?? ''}
                  onChange={(event) => update(column.name, event.target.value)}
                />
              )}
            </label>
          ))}
        </div>

        <div className="modalFoot">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button className="primary" onClick={() => onSave(values)}>{mode === 'create' ? 'Create record' : 'Save changes'}</button>
        </div>
      </div>
    </div>
  );
}

function downloadCsv(result) {
  if (!result?.rows?.length) return;
  const lines = [result.columns.join(',')];
  result.rows.forEach((row) => {
    lines.push(result.columns.map((column) => JSON.stringify(row[column] ?? '')).join(','));
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'query-report.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

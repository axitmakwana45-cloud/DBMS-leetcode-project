import React, { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { request } from "./services/api.js";

const difficulties = ["Easy", "Medium", "Hard"];
const difficultyColors = { easy: "#2dd4a4", medium: "#f4b740", hard: "#f27583" };
const navItems = [
  ["Dashboard", "/app/dashboard", "▦"],
  ["Problems", "/app/problems", "⌕"],
  ["Submissions", "/app/submissions", "▤"],
  ["Analytics", "/app/analytics", "◫"],
  ["Contests", "/app/contests", "◷"],
  ["Leaderboard", "/app/leaderboard", "♛"],
  ["Profile", "/app/profile", "◎"],
  ["Settings", "/app/settings", "⚙"],
];
const tooltipStyle = { background: "#111b2d", border: "1px solid #293852", borderRadius: 8, color: "#e8eefb" };
const empty = "No matching records are available in the connected database.";

function routeFromLocation() {
  const path = window.location.pathname;
  const problem = path.match(/^\/app\/problems\/(\d+)$/);
  const submission = path.match(/^\/app\/submissions\/(\d+)$/);
  if (problem) return { page: "problem", id: Number(problem[1]) };
  if (submission) return { page: "submission", id: Number(submission[1]) };
  const route = navItems.find(([, href]) => href === path);
  return { page: route ? route[0].toLowerCase() : "dashboard", id: null };
}

function navigate(path) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function useRemoteData(path, options = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const search = JSON.stringify(options);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const query = new URLSearchParams(options).toString();
    request(query ? `${path}?${query}` : path)
      .then((result) => { if (active) setData(result); })
      .catch((requestError) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, search]);

  return { data, error, loading, setData };
}

export default function DeveloperPlatform({ user, onLogout }) {
  const [route, setRoute] = useState(routeFromLocation);
  const [theme, setTheme] = useState(() => localStorage.getItem("developerTheme") || "dark");

  useEffect(() => {
    if (!window.location.pathname.startsWith("/app/")) navigate("/app/dashboard");
    const handlePopState = () => setRoute(routeFromLocation());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("developerTheme", theme);
  }, [theme]);

  const activeHref = route.page === "problem" ? "/app/problems" : route.page === "submission" ? "/app/submissions" : `/app/${route.page}`;
  const title = route.page === "problem" ? "Problem workspace"
    : route.page === "submission" ? "Submission details"
      : navItems.find(([, href]) => href === activeHref)?.[0] || "Dashboard";

  return (
    <div className="userLayout">
      <aside className="userSidebar">
        <button className="userBrand" onClick={() => navigate("/app/dashboard")}>
          <span className="brandIcon">LC</span>
          <span><b>LeetCode</b><small>Developer Platform</small></span>
        </button>
        <div className="userNavLabel">WORKSPACE</div>
        <nav className="userNav">
          {navItems.map(([label, href, icon]) => (
            <button key={href} className={activeHref === href ? "active" : ""} onClick={() => navigate(href)}>
              <span>{icon}</span>{label}
            </button>
          ))}
        </nav>
        <div className="userSidebarFoot">
          <div className="userAvatar">{(user.username || "D").slice(0, 1).toUpperCase()}</div>
          <div className="userIdentity"><strong>{user.username}</strong><span>Developer</span></div>
          <button className="userIconButton" title="Log out" onClick={onLogout}>↪</button>
        </div>
      </aside>
      <main className="userMain">
        <header className="userTopbar">
          <div><div className="eyebrow">LEETCODE MANAGEMENT STUDIO</div><h1>{title}</h1></div>
          <div className="userTopActions">
            <span className="userRoleBadge">Developer</span>
            <button className="ghost" onClick={onLogout}>Log out</button>
          </div>
        </header>
        {route.page === "dashboard" && <UserDashboard onNavigate={navigate} />}
        {route.page === "problems" && <ProblemsPage onNavigate={navigate} />}
        {route.page === "problem" && <ProblemPage problemId={route.id} onNavigate={navigate} />}
        {route.page === "submissions" && <SubmissionsPage onNavigate={navigate} />}
        {route.page === "submission" && <SubmissionPage submissionId={route.id} onNavigate={navigate} />}
        {route.page === "analytics" && <AnalyticsPage />}
        {route.page === "leaderboard" && <LeaderboardPage />}
        {route.page === "contests" && <ContestsPage />}
        {route.page === "profile" && <ProfilePage />}
        {route.page === "settings" && <SettingsPage theme={theme} onThemeChange={setTheme} />}
      </main>
    </div>
  );
}

function UserDashboard({ onNavigate }) {
  const { data, error, loading } = useRemoteData("/api/user/dashboard");
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  if (!data) return <EmptyState />;

  const stats = [
    ["Problems solved", data.personal.total_solved, "◉"],
    ["Easy solved", data.personal.easy_solved, "E"],
    ["Medium solved", data.personal.medium_solved, "M"],
    ["Hard solved", data.personal.hard_solved, "H"],
    ["Submissions", data.personal.total_submissions, "↗"],
    ["Acceptance rate", data.personal.acceptance_rate == null ? "—" : `${data.personal.acceptance_rate}%`, "✓"],
    ["Current streak", `${data.personal.current_streak} days`, "◷"],
  ];
  const progress = difficulties.map((difficulty) => {
    const key = difficulty.toLowerCase();
    const total = data.difficulty_totals[key] || 0;
    const solved = data.personal[`${key}_solved`] || 0;
    return { difficulty, total, solved, percent: total ? Math.min(100, Math.round(100 * solved / total)) : 0 };
  });

  return (
    <div className="userPageContent">
      <section className="userWelcome">
        <div>
          <div className="eyebrow">YOUR PROGRESS, YOUR PACE</div>
          <h2>Welcome back, {data.developer.full_name || data.developer.username}</h2>
          <p>{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })} · Every problem is progress.</p>
        </div>
        <button className="primary" onClick={() => onNavigate("/app/problems")}>Solve a problem <span>→</span></button>
      </section>

      <SectionTitle title="Personal progress" subtitle="Calculated from your linked solve and submission records" />
      <div className="userStatsGrid">
        {stats.map(([label, value, icon]) => <UserStat key={label} label={label} value={value ?? 0} icon={icon} />)}
      </div>

      <div className="userTwoColumns">
        <section className="userPanel">
          <SectionTitle title="Problem progress" subtitle="Solved vs. available by difficulty" />
          {progress.map((item) => (
            <div className="progressRow" key={item.difficulty}>
              <div><Difficulty value={item.difficulty} /><span>{item.solved} / {item.total}</span></div>
              <div className="progressTrack"><i style={{ width: `${item.percent}%`, background: difficultyColors[item.difficulty.toLowerCase()] }} /></div>
            </div>
          ))}
          <div className="progressFoot">{data.personal.total_solved} solved of {data.personal.total_problems} problems</div>
        </section>
        <section className="userPanel">
          <SectionTitle title="Platform at a glance" subtitle="Aggregated statistics; no individual activity shown" />
          <div className="globalStatsGrid">
            <GlobalStat label="Developers" value={data.global.developers} />
            <GlobalStat label="Problems" value={data.global.problems} />
            <GlobalStat label="Submissions" value={data.global.submissions} />
            <GlobalStat label="Accepted" value={data.global.accepted_submissions} />
            <GlobalStat label="Global acceptance" value={data.global.acceptance_rate == null ? "—" : `${data.global.acceptance_rate}%`} />
            <GlobalStat label="Contests" value={data.global.contests} />
          </div>
        </section>
      </div>

      <div className="userTwoColumns">
        <section className="userPanel">
          <SectionTitle title="Your activity" subtitle="Daily solves and submissions · last 12 months" />
          <ActivityHeatmap days={data.activity} />
          <div className="streakCaption">Current streak: {data.personal.current_streak} days · Longest: {data.personal.longest_streak} days</div>
        </section>
        <section className="userPanel">
          <SectionTitle title="Continue practicing" subtitle="Unsolved problems from the database" />
          {data.recommendations.length ? data.recommendations.map((problem) => (
            <button className="recommendedProblem" key={problem.problem_id} onClick={() => onNavigate(`/app/problems/${problem.problem_id}`)}>
              <span className="recommendedId">#{problem.problem_id}</span><strong>{problem.title}</strong><Difficulty value={problem.difficulty} />
            </button>
          )) : <EmptyState message="There are no unsolved problems to recommend." />}
          <button className="textLink" onClick={() => onNavigate("/app/problems")}>Browse all problems →</button>
        </section>
      </div>

      <div className="userTwoColumns">
        <section className="userPanel">
          <SectionTitle title="Global difficulty mix" subtitle="All registered platform problems" />
          <ChartBox data={data.global_charts.problems_by_difficulty} type="bar" color="#728dff" />
        </section>
        <section className="userPanel">
          <SectionTitle title="Recent submissions" subtitle="Your latest saved code submissions" />
          {data.recent_submissions.length ? data.recent_submissions.map((submission) => (
            <button className="recentSubmission" key={submission.submission_id} onClick={() => onNavigate(`/app/submissions/${submission.submission_id}`)}>
              <span><strong>{submission.problem_title || `Problem #${submission.problem_id ?? "—"}`}</strong><small>{formatDate(submission.submitted_at)}</small></span>
              <StatusBadge status={submission.status} />
            </button>
          )) : <EmptyState message="You have no submissions yet." />}
        </section>
      </div>
      <section className="userPanel">
        <SectionTitle title="Platform submissions" subtitle="Aggregated global activity · last 30 days" />
        <ChartBox data={data.global_charts.daily_submissions} type="line" color="#728dff" />
      </section>
    </div>
  );
}

function ProblemsPage({ onNavigate }) {
  const [search, setSearch] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [topic, setTopic] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("problem_id");
  const [order, setOrder] = useState("asc");
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(20);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => setPage(0), [debouncedSearch, difficulty, topic, status, sort, order, limit]);

  const options = { search: debouncedSearch, difficulty, topic, status, sort, order, skip: page * limit, limit };
  const { data, error, loading } = useRemoteData("/api/problems", options);
  return (
    <div className="userPageContent">
      <SectionTitle title="Problem set" subtitle={`${data?.total ?? "—"} database problems · search, filter and practice`} />
      <div className="problemFilters">
        <input aria-label="Search problems" placeholder="Search title or ID…" value={search} onChange={(event) => setSearch(event.target.value)} />
        <select aria-label="Difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value)}><option value="">All difficulties</option>{difficulties.map((item) => <option key={item}>{item}</option>)}</select>
        <select aria-label="Topic" value={topic} onChange={(event) => setTopic(event.target.value)}><option value="">All topics</option>{(data?.topics || []).map((item) => <option key={item}>{item}</option>)}</select>
        <select aria-label="Solve status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All status</option><option value="solved">Solved</option><option value="unsolved">Unsolved</option></select>
        <select aria-label="Sort by" value={sort} onChange={(event) => setSort(event.target.value)}><option value="problem_id">Problem ID</option><option value="title">Title</option><option value="difficulty">Difficulty</option><option value="acceptance_rate">Acceptance</option></select>
        <button className="ghost" onClick={() => setOrder((value) => value === "asc" ? "desc" : "asc")}>Order: {order === "asc" ? "↑" : "↓"}</button>
      </div>
      {error && <ErrorState message={error} />}
      <div className="userPanel problemTablePanel">
        {loading ? <Loading /> : data?.items?.length ? (
          <div className="userTableScroll">
            <table className="userTable">
              <thead><tr><th>Status</th><th>ID</th><th>Title</th><th>Difficulty</th><th>Acceptance</th><th>Topics</th></tr></thead>
              <tbody>{data.items.map((problem) => (
                <tr key={problem.problem_id} onClick={() => onNavigate(`/app/problems/${problem.problem_id}`)}>
                  <td>{problem.solved ? <span className="solvedMark">✓ Solved</span> : <span className="unsolvedMark">—</span>}</td>
                  <td>{problem.problem_id}</td>
                  <td><button className="problemTitleLink" onClick={(event) => { event.stopPropagation(); onNavigate(`/app/problems/${problem.problem_id}`); }}>{problem.title}</button></td>
                  <td><Difficulty value={problem.difficulty} /></td>
                  <td>{problem.acceptance_rate == null ? "—" : `${problem.acceptance_rate}%`}</td>
                  <td><span className="topicChips">{problem.topics.map((item) => <i key={item}>{item}</i>)}</span></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : !error && <EmptyState message={empty} />}
        <Pagination page={page} limit={limit} total={data?.total || 0} onPage={setPage} onLimit={(value) => { setLimit(value); setPage(0); }} />
      </div>
    </div>
  );
}

function ProblemPage({ problemId, onNavigate }) {
  const { data: problem, error, loading } = useRemoteData(`/api/problems/${problemId}`);
  const { data: languages } = useRemoteData("/api/languages");
  const [code, setCode] = useState("");
  const [languageId, setLanguageId] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: submissions, setData: setSubmissions } = useRemoteData("/api/submissions/me", { problem_id: problemId, limit: 10 });

  useEffect(() => {
    if (languages?.length && !languageId) setLanguageId(String(languages[0].language_id));
  }, [languages, languageId]);

  async function saveSubmission(event) {
    event.preventDefault();
    setSubmitError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await request("/api/submissions", {
        method: "POST",
        body: JSON.stringify({ problem_id: problemId, language_id: Number(languageId), code }),
      });
      setNotice(result.message);
      setSubmissions((previous) => ({
        ...previous,
        items: [{ submission_id: result.submission_id, problem_id: problemId, problem_title: problem.title, language: languages.find((item) => item.language_id === Number(languageId))?.name, status: result.status, submitted_at: new Date().toISOString() }, ...(previous?.items || [])],
        total: (previous?.total || 0) + 1,
      }));
      setCode("");
    } catch (requestError) {
      setSubmitError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  if (!problem) return <EmptyState message="Problem not found." />;

  return (
    <div className="userPageContent">
      <button className="textLink backLink" onClick={() => onNavigate("/app/problems")}>← All problems</button>
      <div className="problemWorkspace">
        <section className="userPanel problemDescription">
          <div className="problemDetailMeta"><span>#{problem.problem_id}</span><Difficulty value={problem.difficulty} />{problem.solved && <span className="solvedMark">✓ Solved</span>}</div>
          <h2>{problem.title}</h2>
          <div className="problemFacts"><span>Acceptance {problem.acceptance_rate ?? "—"}{problem.acceptance_rate != null ? "%" : ""}</span><span>Time limit {problem.time_limit_ms} ms</span><span>Memory {problem.memory_limit_mb} MB</span></div>
          <div className="topicChips">{problem.topics.map((item) => <i key={item}>{item}</i>)}</div>
          <h3>Description</h3><div className="problemStatement">{problem.description || "No description is available."}</div>
          <h3>Examples</h3>
          {problem.examples.length ? problem.examples.map((example) => (
            <div className="exampleBox" key={example.test_case_no}>
              <strong>Example {example.test_case_no}</strong>
              <pre><b>Input</b>{"\n"}{example.input}<br /><b>Output</b>{"\n"}{example.expected_output}</pre>
            </div>
          )) : <EmptyState message="No public example test cases are available." />}
          <div className="problemPager">
            {problem.previous && <button className="ghost" onClick={() => onNavigate(`/app/problems/${problem.previous.problem_id}`)}>← {problem.previous.title}</button>}
            {problem.next && <button className="ghost" onClick={() => onNavigate(`/app/problems/${problem.next.problem_id}`)}>{problem.next.title} →</button>}
          </div>
        </section>
        <section className="userPanel codePanel">
          <div className="codePanelHead"><div><h3>Your solution</h3><p>Saved submissions are private to your account.</p></div>
            <select aria-label="Programming language" value={languageId} onChange={(event) => setLanguageId(event.target.value)}>{(languages || []).map((language) => <option key={language.language_id} value={language.language_id}>{language.name}{language.version ? ` ${language.version}` : ""}</option>)}</select>
          </div>
          <div className="judgeNotice"><strong>Code execution is not configured.</strong> Saving stores your code as Pending; it will not run against test cases or mark the problem solved.</div>
          <form onSubmit={saveSubmission}>
            <textarea className="codeEditor" aria-label="Solution code" spellCheck="false" value={code} onChange={(event) => setCode(event.target.value)} placeholder="// Write or paste a solution. It will be saved, not executed." required />
            {submitError && <ErrorState message={submitError} />}
            {notice && <div className="loginSuccess" role="status">{notice}</div>}
            <button className="primary" disabled={busy || !languageId}>{busy ? "Saving…" : "Save submission (not evaluated)"}</button>
          </form>
        </section>
      </div>
      <section className="userPanel">
        <SectionTitle title="Your submission history for this problem" subtitle="Only your own submissions are shown" />
        <SubmissionTable items={submissions?.items || []} onNavigate={onNavigate} />
      </section>
    </div>
  );
}

function SubmissionsPage({ onNavigate }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [language, setLanguage] = useState("");
  const [page, setPage] = useState(0);
  const { data: languages } = useRemoteData("/api/languages");
  const options = { search, status, language_id: language, skip: page * 20, limit: 20 };
  const { data, error, loading } = useRemoteData("/api/submissions/me", options);
  return (
    <div className="userPageContent">
      <SectionTitle title="Your submissions" subtitle="Private submission records for your developer account" />
      <div className="problemFilters">
        <input aria-label="Search submissions" placeholder="Search problem title…" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} />
        <select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}><option value="">All statuses</option>{["ACCEPTED", "WRONG_ANSWER", "TIME_LIMIT_EXCEEDED", "RUNTIME_ERROR", "COMPILE_ERROR", "PENDING"].map((item) => <option key={item}>{item}</option>)}</select>
        <select aria-label="Filter by language" value={language} onChange={(event) => { setLanguage(event.target.value); setPage(0); }}><option value="">All languages</option>{(languages || []).map((item) => <option key={item.language_id} value={item.language_id}>{item.name}</option>)}</select>
      </div>
      {error && <ErrorState message={error} />}
      <div className="userPanel problemTablePanel">
        {loading ? <Loading /> : <SubmissionTable items={data?.items || []} onNavigate={onNavigate} />}
        <Pagination page={page} limit={20} total={data?.total || 0} onPage={setPage} />
      </div>
    </div>
  );
}

function SubmissionPage({ submissionId, onNavigate }) {
  const { data, error, loading } = useRemoteData(`/api/submissions/${submissionId}`);
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  if (!data) return <EmptyState message="Submission not found." />;
  return (
    <div className="userPageContent">
      <button className="textLink backLink" onClick={() => onNavigate("/app/submissions")}>← Your submissions</button>
      <section className="userPanel">
        <SectionTitle title={`Submission #${data.submission_id}`} subtitle={`${data.problem_title || "Problem"} · ${data.language || "Unknown language"} · ${formatDate(data.submitted_at)}`} />
        <StatusBadge status={data.status} />
        <p className="submissionMetrics">Runtime: {data.runtime_ms == null ? "Not available" : `${data.runtime_ms} ms`} · Memory: {data.memory_kb == null ? "Not available" : `${data.memory_kb} KB`}</p>
        {data.problem_id && <button className="ghost" onClick={() => onNavigate(`/app/problems/${data.problem_id}`)}>Open problem</button>}
        <pre className="savedCode">{data.code}</pre>
        {String(data.status).toUpperCase() === "PENDING" && <p className="judgeNote">This submission is stored but has not been evaluated because no judge service is configured.</p>}
      </section>
    </div>
  );
}

function AnalyticsPage() {
  const [days, setDays] = useState("30");
  const { data, error, loading } = useRemoteData("/api/user/analytics", { days });
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  return (
    <div className="userPageContent">
      <div className="analyticsHeading"><SectionTitle title="Your analytics" subtitle="Insights calculated from your own linked database records" />
        <select aria-label="Activity period" value={days} onChange={(event) => setDays(event.target.value)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="365">Last 12 months</option></select>
      </div>
      <div className="userStatsGrid">
        <UserStat label="Solved" value={data.personal.total_solved} icon="◉" />
        <UserStat label="Accepted" value={data.personal.accepted_submissions} icon="✓" />
        <UserStat label="Rejected / pending" value={Math.max(0, data.personal.total_submissions - data.personal.accepted_submissions)} icon="↗" />
        <UserStat label="Acceptance rate" value={data.personal.acceptance_rate == null ? "—" : `${data.personal.acceptance_rate}%`} icon="%" />
      </div>
      <div className="userTwoColumns">
        <section className="userPanel"><SectionTitle title="Solved by difficulty" /><ChartBox data={data.difficulty} type="bar" color="#728dff" /></section>
        <section className="userPanel"><SectionTitle title="Your submissions over time" /><ChartBox data={data.activity.map((item) => ({ label: item.date.slice(5), value: item.submissions }))} type="line" color="#2dd4a4" /></section>
      </div>
      <section className="userPanel"><SectionTitle title="Solved by topic" subtitle="Counts are based on your recorded solves and problem tags" />
        {data.topics.length ? <div className="userTableScroll"><table className="userTable"><thead><tr><th>Topic</th><th>Problems solved</th></tr></thead><tbody>{data.topics.map((item) => <tr key={item.topic}><td>{item.topic}</td><td>{item.solved}</td></tr>)}</tbody></table></div> : <EmptyState message="No topic-level solve records are available yet." />}
      </section>
      <InsightCards personal={data.personal} difficulty={data.difficulty} />
    </div>
  );
}

function LeaderboardPage() {
  const { data, error, loading } = useRemoteData("/api/leaderboard", { limit: 50 });
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  return (
    <div className="userPageContent">
      <SectionTitle title="Platform leaderboard" subtitle="Ranked by recorded solved problems. No email or private submission data is exposed." />
      <section className="userPanel problemTablePanel">
        {data?.items?.length ? <div className="userTableScroll"><table className="userTable"><thead><tr><th>Rank</th><th>Developer</th><th>Problems solved</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.username}><td>#{item.rank}</td><td>{item.username}</td><td>{item.problems_solved}</td></tr>)}</tbody></table></div> : <EmptyState message="No leaderboard records are available." />}
      </section>
    </div>
  );
}

function ContestsPage() {
  const { data, error, loading, setData } = useRemoteData("/api/contests");
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState("");
  const [requestError, setRequestError] = useState("");
  async function join(contestId) {
    setBusy(contestId);
    setNotice("");
    setRequestError("");
    try {
      await request(`/api/contests/${contestId}/join`, { method: "POST" });
      setData((previous) => ({ ...previous, items: previous.items.map((item) => item.contest_id === contestId ? { ...item, registered: true, participant_count: item.participant_count + 1 } : item) }));
      setNotice("You are registered for the contest.");
    } catch (joinError) {
      setRequestError(joinError.message);
    } finally {
      setBusy(null);
    }
  }
  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  return (
    <div className="userPageContent">
      <SectionTitle title="Contests" subtitle="Scheduled contests and participation from the connected database" />
      {notice && <div className="loginSuccess" role="status">{notice}</div>}
      {requestError && <ErrorState message={requestError} />}
      {data?.items?.length ? <div className="contestGrid">{data.items.map((contest) => (
        <section className="userPanel contestCard" key={contest.contest_id}>
          <div className="contestCardTop"><span className={`contestPhase ${contest.phase}`}>{contest.phase}</span><span>{contest.participant_count} participants</span></div>
          <h3>{contest.title}</h3>
          <p>{contest.description || "No contest description provided."}</p>
          <div className="contestDates"><span>Starts {formatDate(contest.start_time)}</span><span>Ends {formatDate(contest.end_time)}</span><span>{contest.problem_count} problems</span></div>
          {contest.phase === "upcoming" && <button className="primary" disabled={busy === contest.contest_id || contest.registered} onClick={() => join(contest.contest_id)}>{contest.registered ? "Registered" : busy === contest.contest_id ? "Registering…" : "Register"}</button>}
        </section>
      ))}</div> : <EmptyState message="There are no contest records in the database." />}
    </div>
  );
}

function ProfilePage() {
  const { data: profile, error, loading, setData } = useRemoteData("/api/user/profile");
  const [dashboard, setDashboard] = useState(null);
  const [dashboardError, setDashboardError] = useState("");
  const [fullName, setFullName] = useState("");
  const [country, setCountry] = useState("");
  const [notice, setNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (profile) {
      setFullName(profile.full_name || "");
      setCountry(profile.country || "");
    }
  }, [profile]);
  useEffect(() => {
    request("/api/user/dashboard")
      .then(setDashboard)
      .catch((requestError) => setDashboardError(requestError.message));
  }, []);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    setSaveError("");
    try {
      await request("/api/user/profile", { method: "PATCH", body: JSON.stringify({ full_name: fullName, country }) });
      setData((previous) => ({ ...previous, full_name: fullName, country }));
      setNotice("Profile updated.");
    } catch (updateError) {
      setSaveError(updateError.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading />;
  if (error) return <ErrorState message={error} />;
  return (
    <div className="userPageContent">
      <SectionTitle title="Your profile" subtitle="Update the profile fields supported by your account" />
      <div className="userTwoColumns">
        <section className="userPanel profileCard">
          <div className="profileAvatar">{(profile.full_name || profile.username).slice(0, 1).toUpperCase()}</div>
          <h2>{profile.full_name}</h2><p>{profile.username}</p>
          <div className="profileDetails"><span>Email</span><strong>{profile.email || "Not provided"}</strong><span>Country</span><strong>{profile.country || "Not provided"}</strong><span>Joined</span><strong>{formatDate(profile.joined_on)}</strong><span>Rating</span><strong>{profile.rating ?? "—"}</strong></div>
          <form className="profileEditForm" onSubmit={save}>
            <label className="loginField"><span>Display name</span><input required maxLength="100" value={fullName} onChange={(event) => setFullName(event.target.value)} /></label>
            <label className="loginField"><span>Country</span><input required maxLength="60" value={country} onChange={(event) => setCountry(event.target.value)} /></label>
            {saveError && <ErrorState message={saveError} />}{notice && <div className="loginSuccess">{notice}</div>}
            <button className="primary" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
          </form>
        </section>
        {dashboard && <section className="userPanel"><SectionTitle title="Your progress" />
          <div className="profileDetails"><span>Total solved</span><strong>{dashboard.personal.total_solved}</strong><span>Easy / Medium / Hard</span><strong>{dashboard.personal.easy_solved} / {dashboard.personal.medium_solved} / {dashboard.personal.hard_solved}</strong><span>Submissions</span><strong>{dashboard.personal.total_submissions}</strong><span>Acceptance rate</span><strong>{dashboard.personal.acceptance_rate == null ? "—" : `${dashboard.personal.acceptance_rate}%`}</strong><span>Current streak</span><strong>{dashboard.personal.current_streak} days</strong><span>Longest streak</span><strong>{dashboard.personal.longest_streak} days</strong></div>
        </section>}
        {dashboardError && <ErrorState message={dashboardError} />}
      </div>
    </div>
  );
}

function SettingsPage({ theme, onThemeChange }) {
  return (
    <div className="userPageContent">
      <SectionTitle title="Settings" subtitle="Personal display preferences for this browser" />
      <section className="userPanel settingsPanel"><div><h3>Appearance</h3><p>Choose a light or dark color scheme. This preference is saved in this browser.</p></div>
        <div className="themeToggle"><button className={theme === "dark" ? "active" : ""} onClick={() => onThemeChange("dark")}>Dark</button><button className={theme === "light" ? "active" : ""} onClick={() => onThemeChange("light")}>Light</button></div>
      </section>
      <section className="userPanel"><SectionTitle title="Privacy and evaluation" /><p className="settingsNote">Your code submissions are private to your account. This project has no code execution/judge service; submissions are saved as Pending and are not evaluated.</p></section>
    </div>
  );
}

function InsightCards({ personal, difficulty }) {
  const top = [...difficulty].sort((a, b) => b.value - a.value)[0];
  const insights = [];
  if (!personal.total_solved) insights.push("Your solve history is empty; recorded statistics will appear here as you complete problems.");
  else if (top) insights.push(`Your most-solved difficulty is ${top.label}, with ${top.value} recorded solves.`);
  if (personal.total_submissions) insights.push(`Your recorded acceptance rate is ${personal.acceptance_rate}%, based on ${personal.accepted_submissions} accepted submissions.`);
  if (personal.current_streak) insights.push(`Your current solve streak is ${personal.current_streak} day${personal.current_streak === 1 ? "" : "s"}.`);
  return <section className="userPanel"><SectionTitle title="Data-based insights" subtitle="Generated only from recorded account data" />{insights.length ? insights.map((insight) => <p className="insightItem" key={insight}>✦ {insight}</p>) : <EmptyState message="There is not enough activity data to calculate insights." />}</section>;
}

function ActivityHeatmap({ days }) {
  const max = Math.max(1, ...days.map((day) => day.solved + day.submissions));
  return <div className="heatmapWrap"><div className="heatmap">{days.map((day) => {
    const activity = day.solved + day.submissions;
    const level = activity === 0 ? 0 : Math.min(4, Math.ceil(activity * 4 / max));
    return <span key={day.date} className={`heatCell heat${level}`} title={`${day.date}: ${day.solved} solved, ${day.submissions} submissions`} aria-label={`${day.date}: ${day.solved} solved, ${day.submissions} submissions`} />;
  })}</div><div className="heatmapLegend"><span>Less</span>{[0, 1, 2, 3, 4].map((level) => <i key={level} className={`heatCell heat${level}`} />)}<span>More</span></div></div>;
}

function SubmissionTable({ items, onNavigate }) {
  if (!items.length) return <EmptyState message="No submissions are available for this filter." />;
  return <div className="userTableScroll"><table className="userTable"><thead><tr><th>ID</th><th>Problem</th><th>Language</th><th>Status</th><th>Runtime</th><th>Memory</th><th>Submitted</th></tr></thead><tbody>{items.map((item) => (
    <tr key={item.submission_id} onClick={() => onNavigate(`/app/submissions/${item.submission_id}`)}>
      <td>#{item.submission_id}</td><td>{item.problem_title || `Problem #${item.problem_id ?? "—"}`}</td><td>{item.language || "—"}</td><td><StatusBadge status={item.status} /></td><td>{item.runtime_ms == null ? "—" : `${item.runtime_ms} ms`}</td><td>{item.memory_kb == null ? "—" : `${item.memory_kb} KB`}</td><td>{formatDate(item.submitted_at)}</td>
    </tr>
  ))}</tbody></table></div>;
}

function ChartBox({ data, type, color }) {
  if (!data?.length) return <EmptyState message="No data is available for this chart." />;
  return <div className="userChart"><ResponsiveContainer>
    {type === "line" ? <LineChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#29364c" /><XAxis dataKey="label" tick={{ fill: "#91a0b9", fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fill: "#91a0b9", fontSize: 10 }} /><Tooltip contentStyle={tooltipStyle} /><Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={false} /></LineChart>
      : <BarChart data={data}><CartesianGrid strokeDasharray="3 3" stroke="#29364c" /><XAxis dataKey="label" tick={{ fill: "#91a0b9", fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fill: "#91a0b9", fontSize: 10 }} /><Tooltip contentStyle={tooltipStyle} /><Bar dataKey="value" fill={color} radius={[5, 5, 0, 0]}>{data.map((item, index) => <Cell key={`${item.label}-${index}`} fill={difficultyColors[String(item.label).toLowerCase()] || color} />)}</Bar></BarChart>}
  </ResponsiveContainer></div>;
}

function Pagination({ page, limit, total, onPage, onLimit }) {
  const pages = Math.max(1, Math.ceil(total / limit));
  return <div className="userPagination"><span>Page {page + 1} of {pages} · {total} total</span>{onLimit && <select aria-label="Page size" value={limit} onChange={(event) => onLimit(Number(event.target.value))}><option value="10">10 / page</option><option value="20">20 / page</option><option value="50">50 / page</option></select>}<div><button className="ghost" disabled={page === 0} onClick={() => onPage(page - 1)}>Previous</button><button className="ghost" disabled={(page + 1) * limit >= total} onClick={() => onPage(page + 1)}>Next</button></div></div>;
}

function UserStat({ label, value, icon }) {
  return <div className="userStat"><span className="userStatIcon">{icon}</span><div><small>{label}</small><strong>{value ?? "—"}</strong></div></div>;
}
function GlobalStat({ label, value }) { return <div className="globalStat"><small>{label}</small><strong>{value ?? "—"}</strong></div>; }
function Difficulty({ value }) { const key = String(value || "").toLowerCase(); return <span className={`difficultyBadge ${key}`}>{value || "Unknown"}</span>; }
function StatusBadge({ status }) { const value = String(status || "UNKNOWN"); return <span className={`submissionStatus ${value.toLowerCase()}`}>{value === "PENDING" ? "Pending · not evaluated" : value.replaceAll("_", " ")}</span>; }
function SectionTitle({ title, subtitle }) { return <div className="userSectionTitle"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div></div>; }
function Loading() { return <div className="userPanel userLoading" role="status">Loading database records…</div>; }
function EmptyState({ message = empty }) { return <div className="userEmpty">{message}</div>; }
function ErrorState({ message }) { return <div className="userError" role="alert">{message}</div>; }
function formatDate(value) { return value ? new Date(value).toLocaleString() : "—"; }

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function request(path, options = {}, skipAuth = false) {
  const token = skipAuth ? null : sessionStorage.getItem("adminToken");
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401 && token) {
    sessionStorage.removeItem("adminToken");
    window.dispatchEvent(new Event("admin:unauthorized"));
  }
  if (!res.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).filter(Boolean).join("; ")
      : typeof detail === "string" ? detail : `HTTP ${res.status}`;
    throw new Error(message || `HTTP ${res.status}`);
  }
  return body;
}

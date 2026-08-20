const API = (() => {
  const BASE = "";

  function token() {
    return localStorage.getItem("token");
  }

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.dispatchEvent(new Event("auth-changed"));
  }

  async function request(path, { method = "GET", body, formData, auth = true } = {}) {
    const headers = {};
    if (body && !formData) headers["Content-Type"] = "application/json";
    if (auth) {
      const t = token();
      if (t) headers["Authorization"] = `Bearer ${t}`;
    }
    const opts = { method, headers };
    if (formData) opts.body = formData;
    else if (body) opts.body = JSON.stringify(body);

    const res = await fetch(BASE + path, opts);
    if (res.status === 401) {
      logout();
      const err = new Error("Session expired, please sign in again");
      err.status = 401;
      throw err;
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        if (Array.isArray(j.detail)) detail = j.detail.map((d) => d.msg).join(", ");
        else if (j.detail) detail = j.detail;
      } catch (e) {}
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  }

  return {
    token,
    logout,
    get: (p) => request(p),
    post: (p, body) => request(p, { method: "POST", body }),
    put: (p, body) => request(p, { method: "PUT", body }),
    patch: (p, body) => request(p, { method: "PATCH", body }),
    delete: (p) => request(p, { method: "DELETE" }),
    upload: (p, formData) => request(p, { method: "POST", formData, body: null }),
  };
})();

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem("user") || "null");
  } catch (e) {
    return null;
  }
}

function setCurrentUser(user) {
  if (user) localStorage.setItem("user", JSON.stringify(user));
  else localStorage.removeItem("user");
  window.dispatchEvent(new Event("auth-changed"));
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function stars(rating) {
  const r = Math.round(rating || 0);
  return `<span class="stars">${"★".repeat(r)}${"☆".repeat(5 - r)}</span>`;
}

function durationLabel(seconds) {
  if (!seconds) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function timeAgo(iso) {
  const then = new Date(iso);
  const diff = (Date.now() - then.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

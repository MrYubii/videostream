async function loadStats() {
  try {
    const s = await API.get("/api/admin/stats");
    document.getElementById("statCreators").textContent = s.total_creators;
    document.getElementById("statVideos").textContent = s.total_videos;
    document.getElementById("statViews").textContent = s.total_views.toLocaleString();
    document.getElementById("statComments").textContent = s.total_comments;
    document.getElementById("statRatings").textContent = s.total_ratings;
  } catch (e) {}
}

async function loadCreators() {
  const creators = await API.get("/api/admin/creators");
  const body = document.getElementById("creatorsBody");
  if (!creators.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No creators yet.</td></tr>`;
    return;
  }
  body.innerHTML = creators
    .map(
      (c) => `
      <tr>
        <td>${esc(c.username)}</td>
        <td class="muted">${esc(c.email)}</td>
        <td><span class="pill">${esc(c.role)}</span></td>
        <td>${c.is_active ? "active" : "disabled"}</td>
        <td>
          <button class="btn btn-ghost" onclick="toggleCreator(${c.id}, ${!c.is_active})">
            ${c.is_active ? "Disable" : "Enable"}
          </button>
        </td>
      </tr>`
    )
    .join("");
}

async function toggleCreator(id, active) {
  try {
    await API.patch(`/api/admin/creators/${id}`, { is_active: active });
    toast(active ? "Creator enabled" : "Creator disabled");
    loadCreators();
  } catch (err) {
    toast(err.message);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initNav("admin");
  const user = getCurrentUser();
  if (!user) { location.href = "/login.html?next=/admin.html"; return; }
  if (user.role !== "admin") {
    document.body.innerHTML = `<div class="container"><h1>403 — Admin access required</h1></div>`;
    return;
  }

  document.getElementById("creatorForm").onsubmit = async (e) => {
    e.preventDefault();
    document.getElementById("formError").textContent = "";
    const f = e.target;
    try {
      await API.post("/api/admin/creators", {
        username: f.username.value.trim(),
        email: f.email.value.trim(),
        full_name: f.full_name.value.trim(),
        password: f.password.value,
      });
      toast("Creator enrolled");
      f.reset();
      loadCreators();
      loadStats();
    } catch (err) {
      document.getElementById("formError").textContent = err.message;
    }
  };

  try {
    await Promise.all([loadCreators(), loadStats()]);
  } catch (err) {
    if (err.status === 401) location.href = "/login.html?next=/admin.html";
  }
});

let videoId = null;
let currentVideo = null;

function byId(id) {
  return document.getElementById(id);
}

async function loadVideo() {
  const id = new URLSearchParams(location.search).get("id");
  if (!id) {
    const t = byId("title");
    if (t) t.textContent = "Missing video id";
    return;
  }
  videoId = id;

  let v;
  try {
    v = await API.get(`/api/videos/${id}`);
    currentVideo = v;
  } catch (err) {
    const t = byId("title");
    if (t) t.textContent = err.message || "Video not found";
    const m = byId("meta");
    if (m) m.innerHTML = `<a class="btn btn-ghost" href="/">← Back to dashboard</a>`;
    return;
  }

  document.title = `${v.title} — VideoStream`;
  const title = byId("title");
  if (title) title.textContent = v.title;
  const meta = byId("meta");
  if (meta) {
    meta.innerHTML = `
      <span>${esc(v.publisher)} · ${esc(v.producer)} · ${esc(v.genre)}</span>
      <span>Age rating: <b>${esc(v.age_rating)}</b> · ${v.view_count.toLocaleString()} views · ${timeAgo(v.created_at)}</span>`;
  }
  const desc = byId("description");
  if (desc) desc.textContent = v.description || "";

  const statusEl = byId("status");
  if (statusEl) {
    if (v.status === "processing") {
      statusEl.hidden = false;
      statusEl.textContent = "⏳ Still processing… refresh in a moment";
    } else {
      statusEl.hidden = true;
    }
  }
  const player = byId("player");
  if (player && v.status !== "processing" && v.stream_url) {
    player.src = v.stream_url;
  }

  setupActions(v);
  loadRating();
  loadReactions();
  loadComments();
}

function setupActions(v) {
  const user = getCurrentUser();
  const canManage = user && (user.role === "admin" || v.uploader === user.username);
  const editBtn = byId("editBtn");
  const deleteBtn = byId("deleteBtn");
  if (editBtn) editBtn.hidden = !canManage;
  if (deleteBtn) deleteBtn.hidden = !canManage;

  if (canManage && deleteBtn) {
    deleteBtn.onclick = async () => {
      if (!confirm("Delete this video permanently?")) return;
      try {
        await API.delete(`/api/videos/${videoId}`);
        toast("Video deleted");
        location.href = "/";
      } catch (err) {
        toast(err.message);
      }
    };
  }

  const shareBtn = byId("shareBtn");
  if (shareBtn) {
    shareBtn.onclick = () => shareVideo(v.title || "Watch this video");
  }

  if (canManage && editBtn) {
    editBtn.onclick = () => {
      const f = byId("editForm");
      if (!f) return;
      f.title.value = v.title;
      f.publisher.value = v.publisher;
      f.producer.value = v.producer;
      f.genre.value = v.genre;
      f.age_rating.value = v.age_rating;
      f.description.value = v.description || "";
      const errEl = byId("editError");
      if (errEl) errEl.textContent = "";
      const modal = byId("editModal");
      if (modal) modal.showModal();
    };
  }
}

async function loadRating() {
  const user = getCurrentUser();
  const container = byId("stars");
  const info = byId("ratingInfo");
  if (!container || !info) return;

  let res;
  try {
    res = await API.get(`/api/videos/${videoId}/rating`);
  } catch (err) {
    info.textContent = "Rating unavailable";
    return;
  }

  const avg = res.average != null ? Number(res.average) : 0;
  info.textContent =
    `Average ${avg.toFixed(1)} / 5 from ${res.count} rating${res.count === 1 ? "" : "s"}`;

  const mine = res.user_rating || 0;
  container.querySelectorAll("span").forEach((s) => {
    const val = parseInt(s.dataset.v, 10);
    s.classList.toggle("on", val <= mine);
  });

  if (user) {
    container.onmouseover = (e) => {
      const t = e.target.closest("span");
      if (!t) return;
      container.querySelectorAll("span").forEach((s) =>
        s.classList.toggle("hover", parseInt(s.dataset.v, 10) <= parseInt(t.dataset.v, 10))
      );
    };
    container.onmouseleave = () => container.querySelectorAll("span").forEach((s) => s.classList.remove("hover"));
    container.onclick = async (e) => {
      const t = e.target.closest("span");
      if (!t) return;
      try {
        await API.put(`/api/videos/${videoId}/rating`, { value: parseInt(t.dataset.v, 10) });
        toast(`Rated ${t.dataset.v} / 5`);
        loadRating();
      } catch (err) { toast(err.message); }
    };
  } else {
    container.style.cursor = "default";
    container.title = "Sign in to rate";
  }
}

async function loadReactions() {
  const likeBtn = byId("likeBtn");
  const dislikeBtn = byId("dislikeBtn");
  if (!likeBtn || !dislikeBtn) return;

  let res;
  try {
    res = await API.get(`/api/videos/${videoId}/reaction`);
  } catch (err) {
    return;
  }
  likeBtn.classList.toggle("active", res.user_reaction === "like");
  dislikeBtn.classList.toggle("active", res.user_reaction === "dislike");
  byId("likeCount").textContent = res.like_count;
  byId("dislikeCount").textContent = res.dislike_count;

  likeBtn.onclick = () => setReaction(res.user_reaction === "like" ? null : "like");
  dislikeBtn.onclick = () => setReaction(res.user_reaction === "dislike" ? null : "dislike");
}

async function setReaction(reaction) {
  if (!getCurrentUser()) {
    toast("Sign in to react");
    location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
    return;
  }
  try {
    await API.put(`/api/videos/${videoId}/reaction`, { reaction });
    loadReactions();
  } catch (err) {
    toast(err.message);
  }
}

async function shareVideo(title) {
  const url = location.origin + "/video.html?id=" + encodeURIComponent(videoId);
  const shareData = { title: title, text: "Watch this video on VideoStream", url: url };

  if (navigator.share) {
    try {
      await navigator.share(shareData);
      return;
    } catch (err) {
      if (err.name === "AbortError") return;
    }
  }

  try {
    await navigator.clipboard.writeText(url);
    toast("Link copied to clipboard");
  } catch (err) {
    prompt("Copy this link:", url);
  }
}

async function loadComments() {
  const el = byId("comments");
  if (!el) return;
  let comments;
  try {
    comments = await API.get(`/api/videos/${videoId}/comments`);
  } catch (err) {
    el.innerHTML = `<div class="muted" style="padding:8px 0;">Comments unavailable.</div>`;
    return;
  }
  if (!comments.length) {
    el.innerHTML = `<div class="muted" style="padding:8px 0;">No comments yet. Be the first!</div>`;
    return;
  }
  el.innerHTML = comments
    .map(
      (c) => `
      <div class="comment">
        <span class="who">${esc(c.author)}</span><span class="when">${timeAgo(c.created_at)}</span>
        <p>${esc(c.body)}</p>
      </div>`
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", () => {
  initNav("");
  const editForm = byId("editForm");
  if (editForm) {
    editForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        await API.patch(`/api/videos/${videoId}`, {
          title: f.title.value.trim(),
          publisher: f.publisher.value.trim(),
          producer: f.producer.value.trim(),
          genre: f.genre.value.trim(),
          age_rating: f.age_rating.value,
          description: f.description.value.trim(),
        });
        toast("Saved");
        const modal = byId("editModal");
        if (modal) modal.close();
        loadVideo();
      } catch (err) {
        const errEl = byId("editError");
        if (errEl) errEl.textContent = err.message;
      }
    });
  }
  const commentForm = byId("commentForm");
  if (commentForm) {
    commentForm.onsubmit = async (e) => {
      e.preventDefault();
      const input = e.target.querySelector("input");
      if (!input) return;
      try {
        await API.post(`/api/videos/${videoId}/comments`, { body: input.value.trim() });
        input.value = "";
        loadComments();
      } catch (err) {
        toast(err.message);
        if (err.status === 401) location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search);
      }
    };
  }
  loadVideo();
});

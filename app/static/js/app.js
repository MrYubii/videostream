const GENRES = [
  "Music", "Dance", "Comedy", "Sports", "Gaming", "Education",
  "Travel", "Food", "Science", "Film", "News", "Podcast",
];

const state = { search: "", genre: "", age: "", sort: "latest", offset: 0, total: 0 };

function renderCard(v) {
  const rating = v.rating_average ? v.rating_average.toFixed(1) : "—";
  return `
    <div class="card" onclick="location.href='/video.html?id=${v.id}'">
      <div class="thumb">
        ${v.age_rating ? `<span class="badge">${esc(v.age_rating)}</span>` : ""}
        ${v.thumbnail_url ? `<img src="${v.thumbnail_url}" loading="lazy" alt="">` : ""}
        <span class="duration">${durationLabel(v.duration_seconds)}</span>
      </div>
      <div class="card-body">
        <h3>${esc(v.title)}</h3>
        <div class="meta">
          <span>${esc(v.publisher)} · ${esc(v.genre)}</span>
          <span>${stars(v.rating_average)} ${rating} · ${v.rating_count} ratings</span>
          <span>👁 ${v.view_count.toLocaleString()} views · ${timeAgo(v.created_at)}</span>
        </div>
      </div>
    </div>`;
}

async function loadVideos(reset = false) {
  if (reset) state.offset = 0;
  const params = new URLSearchParams();
  if (state.search) params.set("search", state.search);
  if (state.genre) params.set("genre", state.genre);
  if (state.age) params.set("age_rating", state.age);
  if (state.sort && state.sort !== "latest") params.set("sort", state.sort);
  params.set("offset", state.offset);
  params.set("limit", 12);
  const data = await API.get(`/api/videos?${params}`);
  const el = document.getElementById("videos");
  const html = data.items.map(renderCard).join("");
  if (reset) el.innerHTML = html;
  else el.insertAdjacentHTML("beforeend", html);

  state.total = data.total;
  document.getElementById("count").textContent = `${data.total} video${data.total === 1 ? "" : "s"}`;
  document.getElementById("load-more").hidden = state.offset + data.items.length >= data.total;
  if (!data.items.length && reset) {
    el.innerHTML = `<div class="empty">No videos found. Try a different search or filter.</div>`;
  }
  state.offset += data.items.length;
}

function uploadWithProgress(fd, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos");
    const t = API.token();
    if (t) xhr.setRequestHeader("Authorization", `Bearer ${t}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (e) {
          reject(new Error("Invalid server response"));
        }
      } else {
        let detail = xhr.statusText;
        try {
          const j = JSON.parse(xhr.responseText);
          if (j.detail) detail = j.detail;
        } catch (e) {}
        const err = new Error(detail);
        err.status = xhr.status;
        reject(err);
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(fd);
  });
}

async function pollVideo(id) {
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const v = await API.get(`/api/videos/${id}`);
      if (v.status !== "processing") {
        loadVideos(true);
        return;
      }
    } catch (e) {
      return;
    }
  }
}

function setupUpload() {
  const modal = document.getElementById("uploadModal");
  const fileInput = document.getElementById("file");
  const zone = document.getElementById("dropZone");

  window.openUpload = () => {
    const user = getCurrentUser();
    if (!user) { toast("Please sign in first"); location.href = "/login.html"; return; }
    if (user.role !== "creator" && user.role !== "admin") {
      toast("Only creator accounts can upload");
      return;
    }
    modal.showModal();
  };

  zone.onclick = () => fileInput.click();
  fileInput.onchange = () => {
    const f = fileInput.files[0];
    document.getElementById("fileLabel").textContent = f ? `${f.name} (${(f.size / 1e6).toFixed(1)} MB)` : "Choose a file";
  };

  document.getElementById("uploadForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = fileInput.files[0];
    if (!f) { document.getElementById("uploadError").textContent = "Please choose a file"; return; }
    const form = e.target;
    const fd = new FormData();
    fd.append("file", f);
    fd.append("title", form.title.value.trim());
    fd.append("publisher", form.publisher.value.trim());
    fd.append("producer", form.producer.value.trim());
    fd.append("genre", form.genre.value.trim());
    fd.append("age_rating", form.age_rating.value);
    fd.append("description", form.description.value.trim());

    const btn = document.getElementById("uploadBtn");
    const bar = document.getElementById("uploadProgress");
    btn.disabled = true;
    btn.textContent = "Uploading…";
    bar.hidden = false;
    bar.value = 0;
    document.getElementById("uploadError").textContent = "";
    try {
      const v = await uploadWithProgress(fd, (p) => {
        const pct = Math.round(p * 100);
        bar.value = pct;
        btn.textContent = `Uploading… ${pct}%`;
      });
      toast("Uploaded! Processing media…");
      modal.close();
      e.target.reset();
      fileInput.value = "";
      bar.value = 0;
      bar.hidden = true;
      document.getElementById("fileLabel").textContent = "Click to choose an MP4 / WebM file";
      loadVideos(true);
      pollVideo(v.id);
    } catch (err) {
      document.getElementById("uploadError").textContent = err.message;
      bar.hidden = true;
    } finally {
      btn.disabled = false;
      btn.textContent = "Upload";
    }
  };
}

function setupFilters() {
  const genreSel = document.getElementById("genre");
  GENRES.forEach((g) => genreSel.insertAdjacentHTML("beforeend", `<option value="${g}">${g}</option>`));

  document.getElementById("apply").onclick = () => {
    state.search = document.getElementById("search").value.trim();
    state.genre = document.getElementById("genre").value;
    state.age = document.getElementById("age").value;
    state.sort = document.getElementById("sort").value;
    loadVideos(true);
  };
  document.getElementById("search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("apply").click();
  });
  document.getElementById("load-more").onclick = () => loadVideos(false);
}

document.addEventListener("DOMContentLoaded", () => {
  initNav("home");
  setupFilters();
  setupUpload();
  loadVideos(true);
});

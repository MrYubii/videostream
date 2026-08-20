function renderNav(active) {
  const user = getCurrentUser();
  const links = [{ href: "/", label: "Dashboard", id: "home" }];
  if (user && user.role === "admin") {
    links.push({ href: "/admin.html", label: "Admin", id: "admin" });
  }
  const linkHtml = links
    .map(
      (l) =>
        `<a href="${l.href}" class="btn ${l.id === active ? "btn-primary" : "btn-ghost"}">${l.label}</a>`
    )
    .join("");

  let right = "";
  if (user) {
    const canUpload =
      (user.role === "creator" || user.role === "admin") &&
      document.getElementById("uploadModal");
    const upload = canUpload
      ? `<button class="btn btn-primary" onclick="openUpload()">＋ Upload</button>`
      : "";
    right = `${upload}<span class="pill" title="${esc(user.email || user.username)}">${esc(user.username)}</span>
      <button class="btn btn-ghost" onclick="API.logout(); location.reload()">Sign out</button>`;
  } else {
    right = `<a href="/login.html" class="btn btn-ghost">Sign in</a>
      <a href="/signup.html" class="btn btn-primary">Sign up</a>`;
  }

  document.querySelectorAll(".nav-slot").forEach((el) => {
    el.innerHTML = `
      <nav class="nav">
        <a href="/" class="brand">Video<em>Stream</em><span>.</span></a>
        ${linkHtml}
        <div class="nav-spacer"></div>
        ${right}
      </nav>`;
  });
}

function toast(message) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 2600);
}

function initNav(active) {
  renderNav(active);
  window.addEventListener("auth-changed", () => renderNav(active));
}

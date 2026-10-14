// Lapu galvene: kas pieslēdzies, lomai atbilstoša navigācija un izrakstīšanās (N3).
const ROLE_NAMES = { EMPLOYEE: "Darbinieks", MANAGER: "Vadītājs", ADMIN: "Administrators" };

// Pārējie lapu skripti var gaidīt šo solījumu, lai zinātu lietotāju un lomu.
const currentUser = fetch("/auth/me")
  .then((response) => {
    if (response.status === 401) {
      window.location.href = "/login";
      return null;
    }
    return response.ok ? response.json() : null;
  })
  .catch(() => null);

currentUser.then((me) => {
  if (!me) return;
  document.getElementById("who").textContent = `${me.name || me.email} · ${ROLE_NAMES[me.role] || me.role}`;
  const admin = me.role === "ADMIN";
  for (const item of document.querySelectorAll(".admin-only")) item.hidden = !admin;
  for (const item of document.querySelectorAll(".staff-only")) item.hidden = admin;
  for (const link of document.querySelectorAll(".site-header nav a")) {
    if (link.getAttribute("href") === window.location.pathname) link.setAttribute("aria-current", "page");
  }
});

document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/login";
});

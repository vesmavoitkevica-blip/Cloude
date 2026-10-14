// Lietotāju lomu pārvaldība administratoram (N3).
const rows = document.getElementById("rows");
const message = document.getElementById("message");

function show(text, kind) {
  message.textContent = text;
  message.className = kind;
}

function cell(content) {
  const td = document.createElement("td");
  td.append(content || "—");
  return td;
}

function render(users) {
  rows.replaceChildren();
  for (const user of users) {
    const select = document.createElement("select");
    select.id = `role-${user.id}`;
    select.setAttribute("aria-label", `Loma: ${user.email}`);
    for (const [value, label] of Object.entries(ROLE_NAMES)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.append(option);
    }
    select.value = user.role;

    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "Saglabāt";
    save.setAttribute("aria-label", `Saglabāt lomu: ${user.email}`);
    save.addEventListener("click", () => saveRole(user, select));

    const tr = document.createElement("tr");
    tr.append(cell(user.email), cell(user.name), cell(select), cell(save));
    rows.append(tr);
  }
}

async function saveRole(user, select) {
  show("", "");
  let response;
  try {
    response = await fetch(`/users/${user.id}/role`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: select.value }),
    });
  } catch {
    show("Neizdevās sazināties ar serveri.", "fail");
    return;
  }
  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    user.role = data.role;
    show(`Loma saglabāta: ${user.email} – ${ROLE_NAMES[data.role]}.`, "ok");
    return;
  }
  select.value = user.role;
  const code = (data.error || {}).code;
  const texts = {
    LAST_ADMIN: "Vienīgajam administratoram lomu noņemt nevar.",
    FORBIDDEN: "Lomas drīkst mainīt tikai administrators.",
    NOT_FOUND: "Lietotājs vairs nav atrodams.",
  };
  show(texts[code] || "Neizdevās saglabāt lomu.", "fail");
}

async function load() {
  try {
    const response = await fetch("/users");
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      show("Neizdevās ielādēt lietotājus.", "fail");
      return;
    }
    render(await response.json());
  } catch {
    show("Neizdevās sazināties ar serveri.", "fail");
  }
}

load();

// Uzdevumi un atgādinājumi (F5).
const ISSUES = {
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  TOO_LONG: "Teksts ir pārāk garš.",
  AFTER_DUE_DATE: "Atgādinājums nevar būt pēc termiņa.",
  NOT_FOUND: "Saistītais ieraksts nav atrasts.",
  MISMATCH: "Organizācija nesakrīt ar saistīto ierakstu.",
};

const filters = document.getElementById("filters");
const form = document.getElementById("form");
const rows = document.getElementById("rows");
const empty = document.getElementById("empty");
const message = document.getElementById("message");
const formHeading = document.getElementById("form-heading");
const cancel = document.getElementById("cancel");
const linkNote = document.getElementById("link-note");
const fields = {
  id: document.getElementById("task-id"),
  title: document.getElementById("title"),
  dueDate: document.getElementById("dueDate"),
  remindOn: document.getElementById("remindOn"),
  organizationId: document.getElementById("organizationId"),
  requestId: document.getElementById("requestId"),
  interactionId: document.getElementById("interactionId"),
  done: document.getElementById("done"),
};
let me = null;

function show(text, kind) {
  message.textContent = text;
  message.className = kind;
}

async function call(url, options) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  const data = await response.json().catch(() => ({}));
  return { response, data };
}

function formatDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}.`;
}

function cell(content) {
  const td = document.createElement("td");
  td.append(content || "—");
  return td;
}

function statusText(task) {
  if (task.done) return "Izpildīts";
  if (task.overdue) return `Kavēts, ${task.overdueDays} d.`;
  if (task.dueToday) return "Šodien";
  return "Neizpildīts";
}

function linkText(task) {
  return [task.organizationName, task.requestTitle].filter(Boolean).join(" · ");
}

function button(text, label, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = text;
  b.setAttribute("aria-label", label);
  b.addEventListener("click", onClick);
  return b;
}

function render(items) {
  rows.replaceChildren();
  for (const task of items) {
    const tr = document.createElement("tr");
    const status = document.createElement(task.overdue ? "strong" : "span");
    if (task.overdue) status.className = "overdue";
    status.textContent = statusText(task);

    const actions = document.createElement("td");
    // Citu uzdevumus vadītājs tikai skatās (N3).
    if (me && task.ownerId === me.id) {
      if (!task.done) {
        actions.append(button("Atzīmēt kā izpildītu", `Atzīmēt kā izpildītu: ${task.title}`, () => complete(task)));
      }
      actions.append(button("Labot", `Labot: ${task.title}`, () => startEdit(task)));
    } else {
      actions.append("—");
    }
    tr.append(cell(task.title), cell(linkText(task)), cell(formatDate(task.dueDate)), cell(status), actions);
    rows.append(tr);
  }
  empty.hidden = items.length > 0;
}

function renderReminders(items) {
  const list = document.getElementById("reminders");
  list.replaceChildren();
  for (const task of items) {
    const li = document.createElement("li");
    li.textContent = `${task.title} – termiņš ${formatDate(task.dueDate)}${task.overdue ? `, kavēts ${task.overdueDays} d.` : ""}`;
    list.append(li);
  }
  document.getElementById("reminders-section").hidden = items.length === 0;
}

async function load() {
  const params = new URLSearchParams();
  if (!filters.showDone.checked) params.set("done", "false");
  if (filters.team.checked) params.set("team", "true");
  try {
    const [list, reminders] = await Promise.all([
      call(`/tasks?${params}`),
      call("/tasks?remindersDue=true"),
    ]);
    if (list.response.ok) render(list.data);
    else show("Neizdevās ielādēt uzdevumus.", "fail");
    if (reminders.response.ok) renderReminders(reminders.data);
  } catch (err) {
    if (err.message !== "unauthorized") show("Neizdevās sazināties ar serveri.", "fail");
  }
}

async function complete(task) {
  try {
    const { response } = await call(`/tasks/${task.id}/complete`, { method: "POST" });
    if (response.ok) {
      show("Uzdevums atzīmēts kā izpildīts.", "ok");
      load();
    } else {
      show("Neizdevās atzīmēt uzdevumu.", "fail");
    }
  } catch (err) {
    if (err.message !== "unauthorized") show("Neizdevās sazināties ar serveri.", "fail");
  }
}

async function loadOrganizations() {
  const { response, data } = await call("/organizations");
  if (!response.ok) return;
  for (const org of data) {
    const option = document.createElement("option");
    option.value = org.id;
    option.textContent = org.name;
    fields.organizationId.append(option);
  }
}

function clearErrors() {
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
}

function resetForm() {
  form.reset();
  for (const key of ["id", "requestId", "interactionId"]) fields[key].value = "";
  fields.organizationId.disabled = false;
  document.getElementById("done-field").hidden = true;
  linkNote.hidden = true;
  formHeading.textContent = "Jauns uzdevums";
  cancel.hidden = true;
  clearErrors();
}

function startEdit(task) {
  resetForm();
  fields.id.value = task.id;
  fields.title.value = task.title;
  fields.dueDate.value = task.dueDate;
  fields.remindOn.value = task.remindOn || "";
  fields.organizationId.value = task.organizationId || "";
  fields.organizationId.disabled = true; // Saites pēc izveides nemainās.
  fields.done.checked = task.done;
  document.getElementById("done-field").hidden = false;
  formHeading.textContent = `Labot: ${task.title}`;
  cancel.hidden = false;
  fields.title.focus();
}

// Adreses parametri aizpilda formu, piemēram, no mijiedarbības nākamā soļa (F9).
function prefillFromAddress() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("title")) fields.title.value = params.get("title");
  if (params.get("organizationId")) fields.organizationId.value = params.get("organizationId");
  for (const key of ["requestId", "interactionId"]) {
    if (params.get(key)) fields[key].value = params.get(key);
  }
  if (params.get("interactionId") || params.get("requestId")) {
    linkNote.textContent = params.get("interactionId")
      ? "Uzdevums tiks saistīts ar mijiedarbības nākamo soli."
      : "Uzdevums tiks saistīts ar pieprasījumu.";
    linkNote.hidden = false;
    fields.organizationId.disabled = true;
  }
}

function optionalId(field) {
  return field.value ? Number(field.value) : null;
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  load();
});

cancel.addEventListener("click", () => {
  resetForm();
  show("", "");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors();
  show("", "");

  const id = fields.id.value;
  const body = {
    title: fields.title.value,
    dueDate: fields.dueDate.value,
    remindOn: fields.remindOn.value || null,
  };
  if (id) {
    body.done = fields.done.checked;
  } else {
    body.interactionId = optionalId(fields.interactionId);
    body.requestId = optionalId(fields.requestId);
    // Ja saistīts ar pieprasījumu vai mijiedarbību, organizāciju nosaka serveris.
    if (!body.interactionId && !body.requestId) body.organizationId = optionalId(fields.organizationId);
  }

  let result;
  try {
    result = await call(id ? `/tasks/${id}` : "/tasks", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    if (err.message !== "unauthorized") show("Neizdevās sazināties ar serveri.", "fail");
    return;
  }

  const { response, data } = result;
  if (response.ok) {
    show(id ? "Uzdevums saglabāts." : "Uzdevums izveidots.", "ok");
    resetForm();
    history.replaceState(null, "", window.location.pathname);
    load();
    return;
  }

  const err = data.error || {};
  let first = null;
  for (const d of err.details || []) {
    const target = document.getElementById(d.field + "-error");
    if (target) target.textContent = ISSUES[d.issue] || d.issue;
    first = first || fields[d.field];
  }
  if (first && first.type !== "hidden") first.focus();
  const texts = {
    NOT_FOUND: "Uzdevums vairs nav atrodams.",
    FORBIDDEN: "Labot drīkst tikai uzdevuma īpašnieks.",
  };
  show(texts[err.code] || "Lūdzu, izlabojiet kļūdas.", "fail");
});

(async () => {
  me = await currentUser;
  if (me && me.role === "MANAGER") {
    for (const el of document.querySelectorAll(".team-only")) el.hidden = false;
  }
  await loadOrganizations().catch(() => {});
  prefillFromAddress();
  load();
})();

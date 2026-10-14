// Organizācijas kartīte un mijiedarbību žurnāls (F3).
const ISSUES = {
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  IN_FUTURE: "Datums nevar būt nākotnē.",
  TOO_LONG: "Teksts ir pārāk garš.",
};
const TYPES = { CALL: "Zvans", EMAIL: "E-pasts", MEETING: "Sanāksme" };
const STATUSES = { NEW: "Jauns", IN_PROGRESS: "Darbā", ANSWERED: "Atbildēts" };

const orgId = Number(window.location.pathname.split("/").pop());
const form = document.getElementById("form");
const historyList = document.getElementById("history");
const empty = document.getElementById("empty");
const message = document.getElementById("message");
const formHeading = document.getElementById("form-heading");
const cancel = document.getElementById("cancel");
const fields = {
  id: document.getElementById("interaction-id"),
  occurredOn: document.getElementById("occurredOn"),
  type: document.getElementById("type"),
  summary: document.getElementById("summary"),
  nextStep: document.getElementById("nextStep"),
};
let me = null;
let responsibleId = null;

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

function localToday() {
  // Pārlūka datums; serveris to pārbauda vēlreiz pēc Latvijas laika.
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function formatDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}.`;
}

function paragraph(label, text) {
  const p = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = `${label}: `;
  p.append(strong, text);
  return p;
}

function renderHistory(items) {
  historyList.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    const heading = document.createElement("h3");
    heading.textContent = `${formatDate(item.occurredOn)} · ${TYPES[item.type] || item.type}`;
    li.append(heading, paragraph("Kopsavilkums", item.summary));
    if (item.nextStep) li.append(paragraph("Nākamais solis", item.nextStep));
    if (me && item.authorId === me.id) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Labot";
      edit.setAttribute("aria-label", `Labot ierakstu ${formatDate(item.occurredOn)}`);
      edit.addEventListener("click", () => startEdit(item));
      li.append(edit);
    }
    historyList.append(li);
  }
  empty.hidden = items.length > 0;
}

async function loadHistory() {
  const { response, data } = await call(`/organizations/${orgId}/interactions`);
  if (response.ok) renderHistory(data);
  else show("Neizdevās ielādēt mijiedarbības.", "fail");
}

async function loadRequests() {
  const { response, data } = await call(`/requests?organizationId=${orgId}`);
  if (!response.ok) return;
  const list = document.getElementById("requests");
  list.replaceChildren();
  for (const item of data) {
    const li = document.createElement("li");
    let text = `${item.title} — ${STATUSES[item.status] || item.status}, termiņš ${formatDate(item.dueDate)}`;
    if (item.overdue) text += ` (Kavēts, ${item.overdueDays} d.)`;
    li.textContent = text;
    list.append(li);
  }
  document.getElementById("requests-empty").hidden = data.length > 0;
}

async function load() {
  try {
    const org = await call(`/organizations/${orgId}`);
    if (org.response.status === 404 || org.response.status === 400) {
      document.getElementById("not-found").hidden = false;
      return;
    }
    if (!org.response.ok) {
      show("Neizdevās ielādēt organizāciju.", "fail");
      return;
    }
    responsibleId = org.data.responsibleUserId;
    document.getElementById("org-name").textContent = org.data.name;
    document.title = `${org.data.name} – Organizācija`;
    document.getElementById("org-reg").textContent = org.data.regNumber || "—";
    document.getElementById("org-address").textContent = org.data.address || "—";
    document.getElementById("new-request").href = `/pieprasijumi?organizationId=${orgId}`;
    document.getElementById("card").hidden = false;

    me = await currentUser;
    // Reģistrē tikai organizācijas atbildīgais (N3); labot savus ierakstus var arī pēc tam.
    if (!me || org.data.responsibleUserId !== me.id) {
      form.hidden = true;
      document.getElementById("not-responsible").hidden = false;
    }
    await Promise.all([loadHistory(), loadRequests()]);
  } catch (err) {
    if (err.message !== "unauthorized") show("Neizdevās sazināties ar serveri.", "fail");
  }
}

function clearErrors() {
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
}

function resetForm() {
  if (me && me.id !== responsibleId) form.hidden = true;
  form.reset();
  fields.id.value = "";
  fields.occurredOn.value = localToday();
  formHeading.textContent = "Jauna mijiedarbība";
  cancel.hidden = true;
  clearErrors();
}

function startEdit(item) {
  clearErrors();
  form.hidden = false;
  fields.id.value = item.id;
  fields.occurredOn.value = item.occurredOn;
  fields.type.value = item.type;
  fields.summary.value = item.summary;
  fields.nextStep.value = item.nextStep || "";
  formHeading.textContent = `Labot ierakstu ${formatDate(item.occurredOn)}`;
  cancel.hidden = false;
  fields.occurredOn.focus();
}

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
    occurredOn: fields.occurredOn.value,
    type: fields.type.value,
    summary: fields.summary.value,
    nextStep: fields.nextStep.value,
  };

  let result;
  try {
    result = await call(id ? `/interactions/${id}` : `/organizations/${orgId}/interactions`, {
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
    show(id ? "Mijiedarbība labota." : "Mijiedarbība pievienota.", "ok");
    resetForm();
    loadHistory();
    return;
  }

  const err = data.error || {};
  let first = null;
  for (const d of err.details || []) {
    const target = document.getElementById(d.field + "-error");
    if (target) target.textContent = ISSUES[d.issue] || d.issue;
    first = first || fields[d.field];
  }
  if (first) first.focus();
  const texts = {
    FORBIDDEN: "Labot drīkst tikai ieraksta autors.",
    NOT_FOUND: "Ieraksts vairs nav atrodams.",
  };
  show(texts[err.code] || "Lūdzu, izlabojiet kļūdas.", "fail");
});

fields.occurredOn.max = localToday();
resetForm();
load();

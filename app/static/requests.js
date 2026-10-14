// Pieprasījumu saraksts ar filtriem, reģistrēšana un labošana (F4).
const ISSUES = {
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  TOO_LONG: "Teksts ir pārāk garš.",
  NOT_FOUND: "Šāda organizācija nav atrasta.",
};
const STATUSES = { NEW: "Jauns", IN_PROGRESS: "Darbā", ANSWERED: "Atbildēts" };

const filters = document.getElementById("filters");
const form = document.getElementById("form");
const rows = document.getElementById("rows");
const empty = document.getElementById("empty");
const message = document.getElementById("message");
const formHeading = document.getElementById("form-heading");
const cancel = document.getElementById("cancel");
const orgFilter = document.getElementById("org-filter");
const fields = {
  id: document.getElementById("request-id"),
  organizationId: document.getElementById("organizationId"),
  title: document.getElementById("title"),
  description: document.getElementById("description"),
  dueDate: document.getElementById("dueDate"),
  status: document.getElementById("status"),
};

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

// Filtri adresē, lai uz filtrētu sarakstu var dot saiti (F9 kartītes).
function filtersToParams() {
  const params = new URLSearchParams();
  for (const box of filters.querySelectorAll("input[type=checkbox]:checked")) {
    params.append(box.name, box.value);
  }
  if (filters.organizationId.value) params.set("organizationId", filters.organizationId.value);
  return params;
}

function paramsToFilters(params) {
  for (const box of filters.querySelectorAll("input[type=checkbox]")) {
    box.checked = params.getAll(box.name).includes(box.value);
  }
  filters.organizationId.value = params.get("organizationId") || "";
}

function render(items) {
  rows.replaceChildren();
  for (const item of items) {
    const tr = document.createElement("tr");
    const org = document.createElement("a");
    org.href = `/organizacijas/${item.organizationId}`;
    org.textContent = item.organizationName;

    const status = document.createElement("span");
    status.textContent = STATUSES[item.status] || item.status;
    const statusCell = cell(status);
    if (item.overdue) {
      const late = document.createElement("strong");
      late.className = "overdue";
      late.textContent = `Kavēts, ${item.overdueDays} d.`;
      statusCell.append(document.createElement("br"), late);
    }

    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Labot";
    edit.setAttribute("aria-label", `Labot: ${item.title}`);
    edit.addEventListener("click", () => startEdit(item));

    tr.append(cell(org), cell(item.title), statusCell, cell(formatDate(item.dueDate)), cell(edit));
    rows.append(tr);
  }
  empty.hidden = items.length > 0;
}

async function load() {
  const params = filtersToParams();
  try {
    const { response, data } = await call(`/requests?${params}`);
    if (response.ok) render(data);
    else show("Neizdevās ielādēt pieprasījumus.", "fail");
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
  const preselected = filters.organizationId.value;
  if (preselected) {
    fields.organizationId.value = preselected;
    const org = data.find((o) => String(o.id) === preselected);
    if (org) {
      const all = document.createElement("a");
      all.href = "/pieprasijumi";
      all.textContent = "Rādīt visu organizāciju pieprasījumus";
      orgFilter.append(`Rādīti tikai organizācijas „${org.name}” pieprasījumi. `, all);
      orgFilter.hidden = false;
    }
  }
}

function clearErrors() {
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
}

function resetForm() {
  const keepOrg = fields.organizationId.value;
  form.reset();
  fields.id.value = "";
  fields.organizationId.value = filters.organizationId.value || keepOrg;
  fields.organizationId.disabled = false;
  formHeading.textContent = "Reģistrēt pieprasījumu";
  cancel.hidden = true;
  clearErrors();
}

function startEdit(item) {
  clearErrors();
  fields.id.value = item.id;
  fields.organizationId.value = item.organizationId;
  fields.organizationId.disabled = true; // Organizācija pēc reģistrēšanas nemainās.
  fields.title.value = item.title;
  fields.description.value = item.description || "";
  fields.dueDate.value = item.dueDate;
  fields.status.value = item.status;
  formHeading.textContent = `Labot: ${item.title}`;
  cancel.hidden = false;
  fields.title.focus();
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  history.replaceState(null, "", `?${filtersToParams()}`);
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
    description: fields.description.value,
    dueDate: fields.dueDate.value,
    status: fields.status.value,
  };
  if (!id) body.organizationId = fields.organizationId.value ? Number(fields.organizationId.value) : null;

  let result;
  try {
    result = await call(id ? `/requests/${id}` : "/requests", {
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
    show(id ? "Pieprasījums saglabāts." : "Pieprasījums reģistrēts.", "ok");
    resetForm();
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
  if (first) first.focus();
  show(err.code === "NOT_FOUND" ? "Pieprasījums vairs nav atrodams." : "Lūdzu, izlabojiet kļūdas.", "fail");
});

paramsToFilters(new URLSearchParams(window.location.search));
loadOrganizations().catch(() => {});
load();

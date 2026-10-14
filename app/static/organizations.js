// Organizāciju meklēšana, izveide un rediģēšana (F1).
const ISSUES = {
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  TOO_LONG: "Teksts ir pārāk garš.",
  NOT_FOUND: "Šāds lietotājs nav atrasts.",
  ALREADY_EXISTS: "Organizācija ar šo reģistrācijas numuru jau ir.",
};

const search = document.getElementById("search");
const form = document.getElementById("form");
const rows = document.getElementById("rows");
const empty = document.getElementById("empty");
const message = document.getElementById("message");
const formHeading = document.getElementById("form-heading");
const cancel = document.getElementById("cancel");
// Lauki pēc ID, jo form.id un form.name ir pašas formas īpašības.
const fields = {
  id: document.getElementById("org-id"),
  name: document.getElementById("name"),
  regNumber: document.getElementById("regNumber"),
  address: document.getElementById("address"),
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

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text || "—";
  return td;
}

function render(items) {
  rows.replaceChildren();
  for (const org of items) {
    const tr = document.createElement("tr");
    const nameCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = `/organizacijas/${org.id}`;
    link.textContent = org.name;
    nameCell.append(link);
    tr.append(nameCell, cell(org.regNumber), cell(org.address));
    const action = document.createElement("td");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Rediģēt";
    edit.setAttribute("aria-label", `Rediģēt: ${org.name}`);
    edit.addEventListener("click", () => startEdit(org));
    action.append(edit);
    tr.append(action);
    rows.append(tr);
  }
  empty.hidden = items.length > 0;
}

async function load() {
  const params = new URLSearchParams();
  if (search.q.value.trim()) params.set("q", search.q.value.trim());
  if (search.mine.checked) params.set("mine", "true");
  try {
    const { response, data } = await call(`/organizations?${params}`);
    if (response.ok) render(data);
    else show("Neizdevās ielādēt organizācijas.", "fail");
  } catch (err) {
    if (err.message !== "unauthorized") show("Neizdevās sazināties ar serveri.", "fail");
  }
}

function clearErrors() {
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
}

function startEdit(org) {
  clearErrors();
  fields.id.value = org.id;
  fields.name.value = org.name;
  fields.regNumber.value = org.regNumber || "";
  fields.address.value = org.address || "";
  formHeading.textContent = `Rediģēt: ${org.name}`;
  cancel.hidden = false;
  fields.name.focus();
}

function resetForm() {
  form.reset();
  fields.id.value = "";
  formHeading.textContent = "Jauna organizācija";
  cancel.hidden = true;
  clearErrors();
}

search.addEventListener("submit", (event) => {
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
    name: fields.name.value,
    regNumber: fields.regNumber.value,
    address: fields.address.value,
  };

  let result;
  try {
    result = await call(id ? `/organizations/${id}` : "/organizations", {
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
    show(id ? "Organizācija saglabāta." : "Organizācija izveidota.", "ok");
    resetForm();
    load();
    return;
  }

  const err = data.error || {};
  let first = null;
  for (const d of err.details || []) {
    const target = document.getElementById(d.field + "-error");
    if (target) target.textContent = ISSUES[d.issue] || d.issue;
    first = first || document.getElementById(d.field);
  }
  if (first) first.focus();
  show(err.code === "NOT_FOUND" ? "Organizācija vairs nav atrodama." : "Lūdzu, izlabojiet kļūdas.", "fail");
});

load();

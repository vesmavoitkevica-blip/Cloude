// Kopīgā loģika reģistrācijas un pieteikšanās formām (CR-4, N3).
// Galapunktu un veiksmes paziņojumu nosaka formas data-endpoint un data-success.
// Ar data-redirect pēc pieteikšanās lietotājs nonāk savas lomas sākumlapā.
const ISSUES = {
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  TOO_SHORT: "Parolei jābūt vismaz 8 rakstzīmēm.",
  TOO_LONG: "Teksts ir pārāk garš.",
  ALREADY_EXISTS: "Šis e-pasts jau ir reģistrēts.",
};

const form = document.getElementById("form");
const message = document.getElementById("message");
// form.name ir formas atribūts, tāpēc vārda lauku meklē pēc ID.
const nameField = document.getElementById("name");

function body() {
  const data = { email: form.email.value, password: form.password.value };
  if (nameField) data.name = nameField.value;
  return data;
}

function show(text, kind) {
  message.textContent = text;
  message.className = kind;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
  show("", "");

  let response;
  try {
    response = await fetch(form.dataset.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body()),
    });
  } catch {
    show("Neizdevās sazināties ar serveri.", "fail");
    return;
  }

  const data = await response.json().catch(() => ({}));
  if (response.ok) {
    if (form.dataset.redirect) {
      window.location.href = data.role === "ADMIN" ? "/admin" : "/organizacijas";
      return;
    }
    show(form.dataset.success, "ok");
    form.reset();
    return;
  }

  const err = data.error || {};
  for (const d of err.details || []) {
    const target = document.getElementById(d.field + "-error");
    if (target) target.textContent = ISSUES[d.issue] || d.issue;
  }
  show(
    err.code === "INVALID_CREDENTIALS" ? "Nepareizs e-pasts vai parole." : "Lūdzu, izlabojiet kļūdas.",
    "fail",
  );
});

"""Reģistrācijas un pieteikšanās HTML formas (CR-4)."""

from __future__ import annotations

ISSUE_MESSAGES = """{
  REQUIRED: "Lauks ir obligāts.",
  INVALID_FORMAT: "Nederīgs formāts.",
  TOO_SHORT: "Parolei jābūt vismaz 8 rakstzīmēm.",
  ALREADY_EXISTS: "Šis e-pasts jau ir reģistrēts.",
}"""


def _page(title: str, endpoint: str, button: str, success: str, link: str) -> str:
    return f"""<!doctype html>
<html lang="lv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f4f5f7; margin: 0; }}
  main {{ max-width: 360px; margin: 10vh auto; padding: 24px; background: #fff;
         border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  label {{ display: block; margin-top: 12px; font-weight: 600; }}
  input {{ width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; }}
  button {{ margin-top: 20px; width: 100%; padding: 10px; cursor: pointer; }}
  .field-error {{ color: #b00020; font-size: .9em; min-height: 1.2em; }}
  #message {{ margin-top: 16px; }}
  #message.ok {{ color: #1b5e20; }}
  #message.fail {{ color: #b00020; }}
</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <form id="form" novalidate>
    <label for="email">E-pasts</label>
    <input id="email" name="email" type="email" autocomplete="email" required>
    <div class="field-error" id="email-error"></div>
    <label for="password">Parole</label>
    <input id="password" name="password" type="password" required
           autocomplete="{'new-password' if endpoint.endswith('register') else 'current-password'}">
    <div class="field-error" id="password-error"></div>
    <button type="submit">{button}</button>
  </form>
  <p id="message" role="status"></p>
  <p>{link}</p>
</main>
<script>
const ISSUES = {ISSUE_MESSAGES};
const form = document.getElementById("form");
const message = document.getElementById("message");

form.addEventListener("submit", async (event) => {{
  event.preventDefault();
  for (const el of document.querySelectorAll(".field-error")) el.textContent = "";
  message.textContent = "";
  message.className = "";

  let response;
  try {{
    response = await fetch("{endpoint}", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ email: form.email.value, password: form.password.value }}),
    }});
  }} catch {{
    message.textContent = "Neizdevās sazināties ar serveri.";
    message.className = "fail";
    return;
  }}

  const data = await response.json().catch(() => ({{}}));
  if (response.ok) {{
    message.textContent = "{success}";
    message.className = "ok";
    form.reset();
    return;
  }}
  const err = data.error || {{}};
  for (const d of err.details || []) {{
    const target = document.getElementById(d.field + "-error");
    if (target) target.textContent = ISSUES[d.issue] || d.issue;
  }}
  message.textContent = err.code === "INVALID_CREDENTIALS"
    ? "Nepareizs e-pasts vai parole."
    : "Lūdzu, izlabojiet kļūdas.";
  message.className = "fail";
}});
</script>
</body>
</html>
"""


REGISTER_PAGE = _page(
    "Reģistrācija",
    "/auth/register",
    "Reģistrēties",
    "Konts izveidots. Tagad varat pieteikties.",
    '<a href="/login">Jau ir konts? Pieteikties</a>',
)

LOGIN_PAGE = _page(
    "Pieteikšanās",
    "/auth/login",
    "Pieteikties",
    "Jūs esat pieteicies.",
    '<a href="/register">Nav konta? Reģistrēties</a>',
)

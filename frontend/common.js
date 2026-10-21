const api = async (path, body, method = "POST") => {
  const token = localStorage.getItem("token");
  const r = await fetch("/api/" + path, {
    method: body || method !== "GET" ? "POST" : "GET",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
};

function renderNav() {
  const user = localStorage.getItem("username");
  const nav = document.getElementById("nav");
  nav.innerHTML = '<a class="brand" href="/">♞ Chess Mates</a><a href="/rules.html">Rules</a>' +
    (user
      ? `<a href="/play.html">Play</a><span>${user.replace(/[<>&"]/g, "")}</span><a href="#" id="logout">Log out</a>`
      : '<a href="/login.html">Log in</a><a href="/login.html#signup">Sign up</a>');
  const lo = document.getElementById("logout");
  if (lo) lo.onclick = async (e) => {
    e.preventDefault();
    await api("logout").catch(() => {});
    localStorage.clear();
    location.href = "/";
  };
}

function authForm() {
  let kind = location.hash === "#signup" ? "signup" : "login";
  const apply = () => {
    const signup = kind === "signup";
    const t = signup ? "Sign up" : "Log in";
    document.title = t + " - Chess Mates";
    document.getElementById("title").textContent = t;
    document.getElementById("submit").textContent = t;
    document.getElementById("password").autocomplete = signup ? "new-password" : "current-password";
    document.getElementById("toggle").innerHTML = signup
      ? 'Already have an account? <a href="#login">Log in</a>'
      : 'New here? <a href="#signup">Create an account</a>';
    document.getElementById("error").textContent = "";
  };
  window.addEventListener("hashchange", () => { kind = location.hash === "#signup" ? "signup" : "login"; apply(); });
  apply();
  document.getElementById("form").onsubmit = async (e) => {
    e.preventDefault();
    const err = document.getElementById("error");
    err.textContent = "";
    try {
      const d = await api(kind, {
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      });
      localStorage.setItem("token", d.token);
      localStorage.setItem("username", d.username);
      location.href = "/play.html";
    } catch (ex) { err.textContent = ex.message; }
  };
}
document.addEventListener("DOMContentLoaded", renderNav);

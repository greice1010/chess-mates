const token = localStorage.getItem("token");
if (!token) location.href = "/login.html";
const me = localStorage.getItem("username");
const GLYPH = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙", k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const PIECE_NAME = { K: "white king", Q: "white queen", R: "white rook", B: "white bishop", N: "white knight", P: "white pawn", k: "black king", q: "black queen", r: "black rook", b: "black bishop", n: "black knight", p: "black pawn" };
const $ = (id) => document.getElementById(id);
let ws, state = null, selected = null;

function setSocketEnabled(enabled) {
  for (const id of ["find", "cancel", "resign", "newgame"]) $(id).disabled = !enabled;
  for (const square of $("board").children) square.disabled = !enabled;
}

function send(msg) {
  if (ws?.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(msg));
  return true;
}

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => setSocketEnabled(true);
  ws.onclose = (e) => {
    setSocketEnabled(false);
    if (e.code === 4401) { localStorage.clear(); location.href = "/login.html"; }
    else setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "waiting") { $("lobby").hidden = false; $("gameview").hidden = true; $("status").textContent = "Waiting for an opponent…"; $("find").hidden = true; $("cancel").hidden = false; }
    else if (m.type === "idle") { state = null; $("lobby").hidden = false; $("gameview").hidden = true; $("status").textContent = "Find an opponent to start a game."; $("find").hidden = false; $("cancel").hidden = true; }
    else if (m.type === "presence") { $("offline").hidden = m.online; }
    else if (m.type === "error") { $("err").textContent = m.message; }
    else if (m.type === "state") { state = m; selected = null; $("err").textContent = ""; render(); }
  };
}

function parseFen(fen) {
  const rows = fen.split(" ")[0].split("/"), out = [];
  for (const r of rows) for (const ch of r) {
    if (/\d/.test(ch)) for (let i = 0; i < +ch; i++) out.push(null); else out.push(ch);
  }
  return out; // index 0 = a8
}
const sqName = (i) => "abcdefgh"[i % 8] + (8 - Math.floor(i / 8));


function render() {
  $("lobby").hidden = true; $("gameview").hidden = false;
  const board = $("board");
  const focusedIndex = board.contains(document.activeElement) ? Number(document.activeElement.dataset.index) : null;
  const myColor = state.white === me ? "white" : "black";
  const pieces = parseFen(state.fen);
  const order = [...Array(64).keys()];
  if (myColor === "black") order.reverse();
  board.innerHTML = "";
  for (const i of order) {
    const d = document.createElement("button");
    d.type = "button";
    d.disabled = ws?.readyState !== WebSocket.OPEN;
    d.dataset.index = i;
    const light = (Math.floor(i / 8) + (i % 8)) % 2 === 0;
    d.className = "sq " + (light ? "l" : "d") + (selected === i ? " sel" : "");
    const p = pieces[i];
    d.setAttribute("aria-label", `${sqName(i)}, ${p ? PIECE_NAME[p] : "empty"}`);
    d.setAttribute("aria-pressed", selected === i);
    d.textContent = p ? GLYPH[p] : "";
    d.onclick = () => click(i, pieces, myColor);
    board.appendChild(d);
  }
  if (focusedIndex !== null) board.querySelector(`[data-index="${focusedIndex}"]`)?.focus({ preventScroll: true });
  $("opp").textContent = (myColor === "white" ? state.black : state.white) + (state.turn !== myColor && !state.result ? " ●" : "");
  $("me").textContent = me + " (" + myColor + ")" + (state.turn === myColor && !state.result ? " ●" : "");
  let info = state.result ? `Game over: ${state.result} by ${state.reason}` : (state.turn === myColor ? "Your move" : "Opponent's move");
  if (state.check && !state.result) info += " — check!";
  $("info").textContent = info;
  $("resign").hidden = !!state.result; $("newgame").hidden = !state.result;
  const rows = [];
  for (let n = 0; n < state.moves.length; n += 2)
    rows.push(`<tr><td class="n">${n / 2 + 1}.</td><td>${state.moves[n]}</td><td>${state.moves[n + 1] || ""}</td></tr>`);
  $("moves").innerHTML = "<table>" + rows.join("") + "</table>";
}

function click(i, pieces, myColor) {
  if (state.result || state.turn !== myColor) return;
  const mine = (p) => p && (myColor === "white" ? p === p.toUpperCase() : p === p.toLowerCase());
  if (selected === null) {
    if (mine(pieces[i])) { selected = i; render(); }
    return;
  }
  if (i === selected || mine(pieces[i])) { selected = mine(pieces[i]) && i !== selected ? i : null; render(); return; }
  let uci = sqName(selected) + sqName(i);
  const p = pieces[selected];
  if ((p === "P" && i < 8) || (p === "p" && i >= 56)) uci += "q";
  if (!send({ type: "move", uci })) return;
  selected = null; render();
}

$("find").onclick = () => send({ type: "find" });
$("cancel").onclick = () => send({ type: "cancel" });
$("resign").onclick = () => confirm("Resign this game?") && send({ type: "resign" });
$("newgame").onclick = () => { $("gameview").hidden = true; $("lobby").hidden = false; send({ type: "find" }); };
connect();

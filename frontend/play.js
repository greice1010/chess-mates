const token = localStorage.getItem("token");
if (!token) location.href = "/login.html";
const me = localStorage.getItem("username");
const GLYPH = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙", k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const $ = (id) => document.getElementById(id);
let ws, state = null, selected = null;

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws?token=${encodeURIComponent(token)}`);
  ws.onclose = (e) => {
    if (e.code === 4401) { localStorage.clear(); location.href = "/login.html"; }
    else setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "waiting") { $("status").textContent = "Waiting for an opponent…"; $("find").hidden = true; $("cancel").hidden = false; }
    else if (m.type === "idle") { $("status").textContent = "Find an opponent to start a game."; $("find").hidden = false; $("cancel").hidden = true; }
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
  const myColor = state.white === me ? "white" : "black";
  const pieces = parseFen(state.fen);
  const order = [...Array(64).keys()];
  if (myColor === "black") order.reverse();
  const board = $("board"); board.innerHTML = "";
  for (const i of order) {
    const d = document.createElement("div");
    const light = (Math.floor(i / 8) + (i % 8)) % 2 === 0;
    d.className = "sq " + (light ? "l" : "d") + (selected === i ? " sel" : "");
    const p = pieces[i];
    d.textContent = p ? GLYPH[p] : "";
    d.onclick = () => click(i, pieces, myColor);
    board.appendChild(d);
  }
  $("opp").textContent = (myColor === "white" ? state.black : state.white) + (state.turn !== myColor && !state.result ? " ●" : "");
  $("me").textContent = me + " (" + myColor + ")" + (state.turn === myColor && !state.result ? " ●" : "");
  let info = state.result ? `Game over: ${state.result} by ${state.reason}` : (state.turn === myColor ? "Your move" : "Opponent's move");
  if (state.check && !state.result) info += " — check!";
  $("info").textContent = info;
  $("resign").hidden = !!state.result; $("newgame").hidden = !state.result;
  $("moves").textContent = state.moves.map((m, n) => (n % 2 ? "" : (n / 2 + 1) + ". ") + m).join(" ");
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
  ws.send(JSON.stringify({ type: "move", uci }));
  selected = null; render();
}

$("find").onclick = () => ws.send(JSON.stringify({ type: "find" }));
$("cancel").onclick = () => ws.send(JSON.stringify({ type: "cancel" }));
$("resign").onclick = () => confirm("Resign this game?") && ws.send(JSON.stringify({ type: "resign" }));
$("newgame").onclick = () => { $("gameview").hidden = true; $("lobby").hidden = false; ws.send(JSON.stringify({ type: "find" })); };
connect();

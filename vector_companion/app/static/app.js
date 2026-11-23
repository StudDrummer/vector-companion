"use strict";
/* ---------------- icons (inline SVG, 24x24 stroke) ---------------- */
const P = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
  joy: '<circle cx="12" cy="8" r="3"/><path d="M12 11v5"/><rect x="5" y="16" width="14" height="5" rx="2"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>',
  wave: '<path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2"/>',
  eye: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 8"/>',
  brain: '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a2 2 0 0 0-3-1z"/><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1"/>',
  bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  arrowdown: '<path d="M12 4v16M5 13l7 7 7-7"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  up: '<path d="M6 15l6-6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
  speaker: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/>',
  speakeroff: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/>',
  cube: '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
  roll: '<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1"/><circle cx="15" cy="15" r="1"/><circle cx="15" cy="9" r="1"/><circle cx="9" cy="15" r="1"/>',
  wheel: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/><path d="M12 4v5.5M12 14.5V20M4 12h5.5M14.5 12H20"/>',
  cards: '<rect x="3" y="6" width="11" height="15" rx="2"/><path d="M8 3h11a2 2 0 0 1 2 2v13"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  pencil: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  doc: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
  heart: '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
};
const svg = n => `<svg viewBox="0 0 24 24">${P[n] || ""}</svg>`;
document.body.innerHTML = document.body.innerHTML.replace(/%(\w+)%/g, (m, n) => P[n] ? svg(n) : m);

/* ---------------- helpers ---------------- */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
async function api(path, body, raw) {
  const opt = body === undefined ? {} : raw ? { method: "POST", body, headers: raw }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok || (j && j.ok === false)) throw new Error((j && j.error) || r.statusText);
  return j;
}
let toastT;
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast on" + (err ? " err" : "");
  clearTimeout(toastT); toastT = setTimeout(() => t.className = "toast", 2200);
}
const tryApi = async (path, body, okMsg) => {
  try { const r = await api(path, body); if (okMsg) toast(okMsg); return r; }
  catch (e) { toast(friendly(e.message), true); }
};
const friendly = m => /no robot|unreach|refused|timed out|URLError/i.test(m) ? "Can't reach Vector. Is WirePod running?" : m;
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const wp = (action, params, msg) => tryApi("/api/wp/" + action, params || {}, msg);
const intent = (name, label) => tryApi("/api/do", { action: name }, label || "Sent to Vector");
const say = text => text.trim() && tryApi("/api/say", { text }, "Speaking");

/* ---------------- navigation ---------------- */
const hooks = { overview: [loadToday], drive: [enterDrive, leaveDrive], scan: [startScan, stopScanCam], personality: [loadPersonality], people: [loadFaces], photos: [loadPhotos], brain: [loadBrain],
  notify: [loadNotify], about: [loadAbout], jarvis: [loadJarvis], guard: [loadGuard], actions: [loadStudy], eyes: [loadRobotSettings], general: [loadRobotSettings], voice: [loadRobotSettings] };
let current = null;
function go(id) {
  if (current === id) return;
  if (current && hooks[current] && hooks[current][1]) hooks[current][1]();
  if (current === "drive") stopCam();
  current = id;
  $$(".page").forEach(p => p.classList.toggle("on", p.id === id));
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.go === id));
  if (hooks[id] && hooks[id][0]) hooks[id][0]();
  if (id === "general") { loadSafety(); loadK("#general"); }
  $("#main").scrollTop = 0;
}
$$("[data-go]").forEach(a => a.addEventListener("click", () => go(a.dataset.go)));

/* ---------------- status ---------------- */
const EYES = { teal: "#2fd6c9", orange: "#ff9f0a", yellow: "#ffd60a", lime: "#b4e33d", blue: "#2f7cff", purple: "#bf5af2", green: "#30d158" };
const EYE_NAMES = Object.keys(EYES);
let ST = {}, RS = {};
function battInfo(b) {
  if (!b || b.battery_level === undefined) return null;
  const lvl = b.battery_level, words = ["Very low", "Low", "Good", "Full"];
  // a worn-out battery reads "full" on the charger but sits around 3.5 V; say what's really going on
  const worn = b.battery_volts && b.battery_volts < 3.65 && b.is_on_charger_platform;
  return { pct: worn ? 0.08 : ([0.12, 0.33, 0.66, 1][lvl] ?? 0.5), word: worn ? "Replace" : (words[lvl] ?? "--"),
    charging: !worn && b.is_charging, onCharger: b.is_on_charger_platform, worn };
}
async function refreshStatus() {
  try { ST = await api("/api/status"); } catch { ST = {}; }
  const bot = ST.robot, b = battInfo(ST.battery), online = bot && b;
  $("#sb-dot").className = "dot " + (online ? "ok" : ST.wirepod ? "warn" : "bad");
  $("#sb-status").textContent = online ? (b.onCharger ? "On charger" : "Connected") : ST.wirepod ? "Robot offline" : "WirePod not running";
  $("#hero-sub").textContent = online ? `Serial ${bot.esn}` : ST.wirepod ? "Vector isn't answering. Is he awake and on Wi-Fi?" : "Open the WirePod app to connect.";
  $("#pill-batt").textContent = b ? b.word : "--";
  $("#pill-power").textContent = b ? (b.charging ? "Charging" : b.onCharger ? "On charger" : "On battery") : "--";
  $("#pill-ip").textContent = bot ? bot.ip_address : "--";
  $("#cam-batt").textContent = b ? `BATTERY ${b.word.toUpperCase()}${b.charging ? " +" : ""}` : "";
  const ring = $("#ring-fg");
  ring.style.strokeDashoffset = 326.7 * (1 - (b ? b.pct : 0));
  ring.style.stroke = b && b.pct <= 0.33 ? "var(--red)" : "var(--green)";
  $(".ring-face").classList.toggle("sleepy", !online);
  const mark = (ok, yes, no) => `<span class="${ok ? "ok" : "bad"}">${ok ? yes : no}</span>`;
  $("#svc-wp").innerHTML = mark(ST.wirepod, "Running", "Not running");
  $("#svc-brain").innerHTML = mark(ST.brain, "Running", "Not running");
  $("#svc-ollama").innerHTML = mark(ST.ollama, "Running", "Not running");
  const c = ST.companion;
  $("#svc-comp").innerHTML = !c ? mark(false, "", "Not running") : c.connected ? mark(true, "Connected", "") : `<span class="bad">Can't reach Vector</span>`;
}

/* ---------------- robot settings (eyes, volume, general) ---------------- */
function setEyeCss(color) { document.documentElement.style.setProperty("--eye", color); }
function eyeCssFromSettings() {
  const c = RS.custom_eye_color;
  if (c && c.enabled) return `hsl(${Math.round((c.hue || 0) * 360)} ${Math.round((c.saturation ?? 1) * 100)}% 55%)`;
  return EYES[EYE_NAMES[RS.eye_color ?? 0]] || EYES.teal;
}
async function loadRobotSettings() {
  try { RS = await api("/api/robot_settings"); } catch { return; }
  setEyeCss(eyeCssFromSettings());
  $("#volume").value = RS.master_volume ?? 3;
  $$(".sw-item").forEach(el => el.classList.toggle("on", +el.dataset.i === (RS.eye_color ?? 0) && !(RS.custom_eye_color || {}).enabled));
  const c = RS.custom_eye_color || {};
  $("#custom-on").checked = !!c.enabled;
  $("#hue").value = c.hue ?? 0.5; $("#sat").value = c.saturation ?? 1;
  segSet("#wake", String(RS.button_wakeword ?? 0));
  segSet("#temp", RS.temp_is_fahrenheit === false ? "c" : "f");
  segSet("#clock", RS.clock_24_hour ? "24" : "12");
  if (document.activeElement !== $("#location")) $("#location").value = RS.default_location || "";
  if (RS.time_zone) $("#tz").value = RS.time_zone;
  if (RS.locale) $("#locale").value = RS.locale;
}
function segSet(sel, v) { $$(sel + " button").forEach(b => b.classList.toggle("on", b.dataset.v === v)); }
function segBind(sel, fn) {
  $$(sel + " button").forEach(b => b.addEventListener("click", () => { segSet(sel, b.dataset.v); fn(b.dataset.v); }));
}

// eyes
$("#swatches").innerHTML = EYE_NAMES.map((n, i) =>
  `<div class="sw-item" data-i="${i}"><i style="--c:${EYES[n]}"></i>${n[0].toUpperCase() + n.slice(1)}</div>`).join("");
$$(".sw-item").forEach(el => el.addEventListener("click", async () => {
  $$(".sw-item").forEach(x => x.classList.toggle("on", x === el));
  $("#custom-on").checked = false;
  setEyeCss(EYES[EYE_NAMES[+el.dataset.i]]);
  await wp("eye_color", { color: +el.dataset.i });
}));
const sendCustom = debounce(() => wp("custom_eye_color", { hue: $("#hue").value, sat: $("#sat").value }), 250);
function customPreview() { setEyeCss(`hsl(${Math.round($("#hue").value * 360)} ${Math.round($("#sat").value * 100)}% 55%)`); }
["#hue", "#sat"].forEach(s => $(s).addEventListener("input", () => {
  $("#custom-on").checked = true; $$(".sw-item").forEach(x => x.classList.remove("on")); customPreview(); sendCustom();
}));
$("#custom-on").addEventListener("change", e => {
  if (e.target.checked) { customPreview(); sendCustom(); }
  else { const i = RS.eye_color ?? 0; setEyeCss(EYES[EYE_NAMES[i]]); $$(".sw-item")[i].classList.add("on"); wp("eye_color", { color: i }); }
});

// voice
$("#volume").addEventListener("change", e => wp("volume", { volume: e.target.value }, "Volume set"));
$("#vo-say-btn").addEventListener("click", () => say($("#vo-say").value));
$("#vo-say").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); say(e.target.value); } });
$("#vo-listen").addEventListener("click", () => go("jarvis"));
const CHIPS = ["Hello!", "Good morning.", "Time to study.", "Great job!", "I'll be right back.", "Who's there?", "Beep boop."];
$("#chips").innerHTML = CHIPS.map(c => `<button class="chip">${esc(c)}</button>`).join("");
$$(".chip").forEach(c => c.addEventListener("click", () => say(c.textContent)));
const drop = $("#drop");
async function sendSound(file) {
  if (!file) return;
  toast("Converting " + file.name + "...");
  try { await api("/api/sound", await file.arrayBuffer(), { "X-Filename": file.name, "Content-Type": "application/octet-stream" }); toast("Playing on Vector"); }
  catch (e) { toast(friendly(e.message), true); }
}
$("#sound").addEventListener("change", e => sendSound(e.target.files[0]));
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => sendSound(e.dataTransfer.files[0]));

// general
segBind("#wake", v => wp(v === "1" ? "button_alexa" : "button_hey_vector", {}, "Saved"));
segBind("#temp", v => wp(v === "c" ? "temp_c" : "temp_f", {}, "Saved"));
segBind("#clock", v => wp(v === "24" ? "time_format_24" : "time_format_12", {}, "Saved"));
$("#location").addEventListener("change", e => wp("location", { location: e.target.value }, "Location saved"));
try { $("#tz").innerHTML = Intl.supportedValuesOf("timeZone").map(z => `<option>${z}</option>`).join(""); } catch { }
$("#tz").value = Intl.DateTimeFormat().resolvedOptions().timeZone;
$("#tz").addEventListener("change", e => wp("timezone", { timezone: e.target.value }, "Time zone saved"));
$("#locale").addEventListener("change", e => wp("locale", { locale: e.target.value }, "Language saved"));

/* ---------------- actions ---------------- */
const TILES = [
  ["blackjack", "Blackjack", "cards", "#5e5ce6"], ["fist_bump", "Fist bump", "bolt", "#ff9f0a"],
  ["trick", "Do a trick", "spark", "#ff375f"], ["love", "I love you", "heart", "#ff2d55"],
  ["praise", "Good robot", "spark", "#30d158"], ["take_photo", "Take photo", "camera", "#8e8e93"],
  ["time", "What time is it", "info", "#64d2ff"], ["hello", "Say hi", "person", "#0a84ff"],
  ["sleep", "Sleep", "moon", "#5e5ce6"], ["go_to_charger", "Go home", "bolt", "#30d158"],
  ["dance", "Dance", "music", "#ff375f", 1], ["explore", "Explore", "compass", "#30d158", 1],
  ["come_here", "Come here", "arrowdown", "#0a84ff", 1], ["fetch_cube", "Fetch cube", "cube", "#ff9f0a", 1],
  ["roll_cube", "Roll cube", "roll", "#ffd60a", 1], ["pop_a_wheelie", "Wheelie", "wheel", "#bf5af2", 1],
];
$("#tiles").innerHTML = TILES.map(([k, l, i, c, drives]) =>
  `<button class="tile${drives ? " drives" : ""}" data-a="${k}"><span class="ti" style="--c:${c}">${svg(i)}</span><b>${l}</b>${drives ? `<small class="lockn">${svg("lock")} needs dock lock off</small>` : ""}</button>`).join("");
$$(".tile").forEach(t => t.addEventListener("click", async () => {
  t.classList.add("busy"); setTimeout(() => t.classList.remove("busy"), 1600);
  await intent(t.dataset.a, t.querySelector("b").textContent);
  if (t.dataset.a === "blackjack") { $("#bj").classList.add("on"); setTimeout(syncLive, 600); }
  else setTimeout(syncLive, 400);
}));
$("#quiz-go").addEventListener("click", () => tryApi("/api/quiz", { topic: $("#quiz-topic").value.trim() || "my mistakes" }, "Making your quiz..."));
$("#study-go").addEventListener("click", async () => { await tryApi("/api/companion/focus", { minutes: 25, goal: $("#study-goal").value.trim() }, "Study session started"); syncLive(); });
async function loadStudy() { try { const s = await api("/api/study"); $("#study-today").textContent = s.today ? `${s.today} min` : "Nothing yet"; } catch { } }
$("#bj-hit").addEventListener("click", async () => { await intent("bj_hit", "Hit"); syncLive(); });
$("#bj-stand").addEventListener("click", async () => { await intent("bj_stand", "Stand"); syncLive(); });
$$("[data-intent]").forEach(b => b.addEventListener("click", () => intent(b.dataset.intent, b.textContent.trim())));
$("#qa-listen").addEventListener("click", () => go("jarvis"));
$("#qa-study").addEventListener("click", () => tryApi("/api/companion/focus", { minutes: 25 }, "25 minute study session started"));
$("#qa-quiz").addEventListener("click", () => { go("actions"); setTimeout(() => $("#quiz-topic").focus(), 200); });
$("#qa-status").addEventListener("click", () => intent("status", "Status report"));
async function loadToday() {
  let t = {}; try { t = await api("/api/today"); } catch { return; }
  $("#t-weather").textContent = t.weather ? t.weather.now : "--";
  $("#t-weather2").textContent = t.weather ? t.weather.range : "";
  $("#t-study").textContent = t.study ? `${t.study} min` : "0 min";
  $("#t-focus").textContent = t.focus ? `Timer: ${Math.ceil(t.focus.left_s / 60)} min left` : (t.study ? "Nice work" : "Not started yet");
  $("#t-todo").textContent = String(t.todo.length);
  $("#t-todo2").textContent = t.todo[0] ? t.todo[0] : "List is clear";
  $("#t-next").textContent = t.next[0] ? t.next[0].split(":")[0] : "Nothing";
  $("#t-next2").textContent = t.next[0] ? (t.next[0].split(":").slice(1).join(":").trim() || "") : "No reminders soon";
}
$("#ov-say").addEventListener("keydown", e => { if (e.key === "Enter") { say(e.target.value); e.target.value = ""; } });
$("#dr-say").addEventListener("keydown", e => { if (e.key === "Enter") { say(e.target.value); e.target.value = ""; } });

/* ---------------- drive & camera ---------------- */
let camOn = false;
async function startCam() {
  const img = $("#cam"), msg = $("#cam-msg");
  msg.style.display = "flex"; msg.textContent = "Connecting to camera...";
  try {
    const { url } = await api("/api/camera_url");
    camOn = true;
    img.onload = () => { msg.style.display = "none"; };
    img.onerror = () => { if (camOn) msg.textContent = "Camera unavailable. Is Vector awake?"; };
    img.src = url + "&t=" + Date.now();
  } catch (e) { msg.textContent = friendly(e.message); }
}
function stopCam() { camOn = false; $("#cam").removeAttribute("src"); }
let speedK = 0.75;
segBind("#speed", v => speedK = +v);
const MAXW = 220;
const drive = { x: 0, y: 0, active: false, keys: new Set(), head: 0, lift: 0 };
function wheels() {
  const fwd = -drive.y, turn = drive.x * 0.65;
  const clamp = v => Math.max(-1, Math.min(1, v));
  return { lw: Math.round(clamp(fwd + turn) * MAXW * speedK), rw: Math.round(clamp(fwd - turn) * MAXW * speedK) };
}
let lastSent = "";
setInterval(() => {
  if (current !== "drive") return;
  const moving = drive.active || drive.keys.size || drive.head || drive.lift;
  if (!moving) return;
  const body = { ...wheels(), head: drive.head, lift: drive.lift };
  lastSent = JSON.stringify(body);
  api("/api/move", body).catch(e => toast(friendly(e.message), true));
}, 140);
function halt(body) { api("/api/move", body).catch(() => { }); }
function stopDrive() { drive.x = drive.y = drive.head = drive.lift = 0; drive.active = false; drive.keys.clear(); api("/api/stop", {}).catch(() => { }); setKnob(0, 0); }

// joystick
const joy = $("#joy"), knob = $("#knob");
function setKnob(x, y) { knob.style.transform = `translate(${x * 38}px, ${y * 38}px)`; }
function joyPos(e) {
  const r = joy.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  let x = (e.clientX - cx) / (r.width / 2 - 14), y = (e.clientY - cy) / (r.height / 2 - 14);
  const m = Math.hypot(x, y); if (m > 1) { x /= m; y /= m; }
  const dz = v => Math.abs(v) < 0.12 ? 0 : v;
  drive.x = dz(x); drive.y = dz(y); setKnob(x, y);
}
joy.addEventListener("pointerdown", e => { joy.setPointerCapture(e.pointerId); drive.active = true; joy.classList.add("active"); joyPos(e); });
joy.addEventListener("pointermove", e => { if (drive.active) joyPos(e); });
const joyEnd = () => { if (!drive.active) return; drive.active = false; drive.x = drive.y = 0; joy.classList.remove("active"); setKnob(0, 0); halt({ lw: 0, rw: 0 }); };
joy.addEventListener("pointerup", joyEnd); joy.addEventListener("pointercancel", joyEnd);

// head / lift: precise angle & height through the companion (Python SDK)
const sendHead = debounce(v => tryApi("/api/companion/head", { deg: +v }), 120);
const sendLift = debounce(v => tryApi("/api/companion/lift", { height: v / 100 }), 120);
function setHead(v) { v = Math.max(-22, Math.min(45, +v)); $("#head").value = v; $("#head-v").innerHTML = v + "&deg;"; sendHead(v); }
function setLift(v) { v = Math.max(0, Math.min(100, +v)); $("#lift").value = v; $("#lift-v").textContent = v + "%"; sendLift(v); }
$("#head").addEventListener("input", e => setHead(e.target.value));
$("#lift").addEventListener("input", e => setLift(e.target.value));
$("#stop-all").addEventListener("click", () => { stopDrive(); toast("Stopped"); });
$("#mirror").addEventListener("change", e => wp("mirror_mode", { enable: e.target.checked ? "true" : "false" }, e.target.checked ? "Camera on his face" : "Face back to normal"));

// keyboard
const KEYMAP = { w: [0, -1], arrowup: [0, -1], s: [0, 1], arrowdown: [0, 1], a: [-1, 0], arrowleft: [-1, 0], d: [1, 0], arrowright: [1, 0] };
function keysToDrive() {
  if (drive.active) return;
  let x = 0, y = 0;
  drive.keys.forEach(k => { x += KEYMAP[k][0]; y += KEYMAP[k][1]; });
  drive.x = Math.max(-1, Math.min(1, x)); drive.y = Math.max(-1, Math.min(1, y)); setKnob(drive.x * 0.8, drive.y * 0.8);
}
const typing = () => { const a = document.activeElement; return /TEXTAREA|SELECT/.test(a.tagName) || (a.tagName === "INPUT" && !["range", "checkbox"].includes(a.type)); };
document.addEventListener("keydown", e => {
  if (current !== "drive" || typing() || e.metaKey) return;
  const k = e.key.toLowerCase();
  if (KEYMAP[k] && DOCK) { e.preventDefault(); if (!e.repeat) toast("Driving is locked while he charges (Safety > Dock lock)", true); return; }
  if (KEYMAP[k]) { e.preventDefault(); drive.keys.add(k); keysToDrive(); }
  else if (k === "r" || k === "f") setHead(+$("#head").value + (k === "r" ? 5 : -5));
  else if (k === "t" || k === "g") setLift(+$("#lift").value + (k === "t" ? 10 : -10));
  else if (k === " ") { e.preventDefault(); stopDrive(); }
});
document.addEventListener("keyup", e => {
  const k = e.key.toLowerCase();
  if (KEYMAP[k]) { drive.keys.delete(k); keysToDrive(); if (!drive.keys.size && !drive.active) halt({ lw: 0, rw: 0 }); }
});
window.addEventListener("blur", () => { if (current === "drive") stopDrive(); });

/* ---------------- safety, sensors, map ---------------- */
let DOCK = true, sensorT = null, mapT = null;
async function loadSafety() {
  try { const s = await api("/api/settings"); DOCK = s.app.safety ? s.app.safety.dock_lock : true; } catch { }
  $("#dock-lock").checked = $("#dock-lock2").checked = DOCK;
  document.querySelector(".joy-wrap").classList.toggle("locked", DOCK);
}
async function setDock(on) {
  if (!on && !confirm("Turn off the dock lock? With his current battery he'll shut down as soon as he leaves the charger.")) { loadSafety(); return; }
  await tryApi("/api/settings", { app: { safety: { dock_lock: on } } }, on ? "Dock lock on" : "Dock lock off: driving enabled");
  loadSafety();
}
["#dock-lock", "#dock-lock2"].forEach(sel => $(sel).addEventListener("change", e => setDock(e.target.checked)));
async function pollSensors() {
  try {
    const s = await api("/api/sensors");
    $("#sn-charger").innerHTML = s.on_charger ? '<span class="ok">Yes</span>' : '<span class="warn">No</span>';
    $("#sn-cliff").innerHTML = s.cliff ? '<span class="bad">Edge detected</span>' : '<span class="ok">Clear</span>';
    $("#sn-dist").textContent = s.distance_mm == null ? "Nothing close" : (s.distance_mm / 10).toFixed(1) + " cm";
    if (s.safety_event && Date.now() / 1000 - s.safety_event.at < 3) toast("Stopped: " + s.safety_event.why, true);
  } catch { $("#sn-charger").textContent = $("#sn-cliff").textContent = $("#sn-dist").textContent = "offline"; }
}
function refreshMap() {
  const img = $("#desk-map"); const n = new Image();
  n.onload = () => { img.src = n.src; $("#map-msg").style.display = "none"; };
  n.onerror = () => { $("#map-msg").style.display = "flex"; $("#map-msg").textContent = "Map unavailable while Vector is offline."; };
  n.src = "/api/map.png?t=" + Date.now();
}
function enterDrive() { startCam(); loadSafety(); pollSensors(); refreshMap(); sensorT = setInterval(pollSensors, 1000); mapT = setInterval(refreshMap, 3000); }
function leaveDrive() { stopDrive(); clearInterval(sensorT); clearInterval(mapT); }

/* ---------------- people ---------------- */
async function loadFaces() {
  const box = $("#faces");
  let list;
  try { list = await api("/api/faces"); } catch (e) { box.innerHTML = `<div class="empty">${esc(friendly(e.message))}</div>`; return; }
  if (!Array.isArray(list)) list = (list && list.faces) || [];
  if (!list.length) { box.innerHTML = `<div class="empty">No faces yet. Teach him one below.</div>`; return; }
  box.innerHTML = list.map(f => {
    const id = f.face_id ?? f.faceId ?? f.id, name = f.name || "Unknown";
    return `<div class="row" data-id="${id}" data-name="${esc(name)}"><div class="face-av">${esc(name[0] || "?").toUpperCase()}</div>
      <div class="li-text">${esc(name)}</div>
      <button class="icon-btn ren" title="Rename">${svg("pencil")}</button><button class="icon-btn del" title="Forget">${svg("trash")}</button></div>`;
  }).join("");
  $$("#faces .ren").forEach(b => b.addEventListener("click", () => {
    const row = b.closest(".row"), t = row.querySelector(".li-text");
    t.innerHTML = `<input class="field" style="text-align:left" value="${row.dataset.name}">`;
    const inp = t.querySelector("input"); inp.focus(); inp.select();
    inp.addEventListener("keydown", async e => {
      if (e.key === "Enter" && inp.value.trim()) { await wp("rename_face", { id: row.dataset.id, oldname: row.dataset.name, newname: inp.value.trim() }, "Renamed"); loadFaces(); }
      if (e.key === "Escape") loadFaces();
    });
  }));
  confirmBtns("#faces .del", async row => { await wp("delete_face", { id: row.dataset.id }, "Forgotten"); loadFaces(); });
}
function confirmBtns(sel, fn) {
  $$(sel).forEach(b => b.addEventListener("click", () => {
    if (!b.dataset.armed) { b.dataset.armed = 1; b.style.color = "var(--red)"; b.title = "Click again to confirm"; setTimeout(() => { delete b.dataset.armed; b.style.color = ""; }, 2500); return; }
    fn(b.closest(".row"));
  }));
}
$("#face-add").addEventListener("click", async () => {
  const n = $("#face-name").value.trim(); if (!n) return toast("Type a name first", true);
  await wp("add_face", { name: n }, `Learning ${n}... look at Vector`); $("#face-name").value = ""; setTimeout(loadFaces, 8000);
});

/* ---------------- photos ---------------- */
let lbId = null;
async function loadPhotos() {
  const g = $("#photo-grid");
  let d;
  try { d = await api("/api/photos"); } catch (e) { g.innerHTML = `<div class="empty">${esc(friendly(e.message))}</div>`; return; }
  const mac = (d && d.mac) || [], robot = (d && d.robot) || [];
  if (!mac.length && !robot.length) { g.innerHTML = `<div class="empty">No photos yet. Say "Hey Jarvis, take a photo".</div>`; return; }
  g.innerHTML = mac.map(p => `<figure class="ph" data-mac="${esc(p.name)}"><img src="/api/mac_photo/${encodeURIComponent(p.name)}" loading="lazy" alt="">` +
      `<figcaption>${p.kind === "guard" ? "Desk guard · " : ""}${new Date(p.at * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</figcaption></figure>`).join("") +
    robot.slice().reverse().map(id => `<figure class="ph" data-id="${id}"><img src="/api/photo?thumb=1&id=${id}" loading="lazy" alt=""><figcaption>On Vector</figcaption></figure>`).join("");
  $$("#photo-grid .ph").forEach(f => f.addEventListener("click", () => {
    lbId = f.dataset.id || null; lbMac = f.dataset.mac || null;
    $("#lb-img").src = lbMac ? "/api/mac_photo/" + encodeURIComponent(lbMac) : "/api/photo?id=" + lbId;
    $("#lightbox").classList.add("on");
  }));
}
let lbMac = null;
$("#ph-refresh").addEventListener("click", loadPhotos);
$("#lb-close").addEventListener("click", () => $("#lightbox").classList.remove("on"));
$("#lightbox").addEventListener("click", e => { if (e.target.id === "lightbox") $("#lightbox").classList.remove("on"); });
$("#lb-del").addEventListener("click", async e => {
  const b = e.currentTarget;
  if (!b.dataset.armed) { b.dataset.armed = 1; b.textContent = "Delete forever?"; setTimeout(() => { delete b.dataset.armed; b.textContent = "Delete"; }, 2500); return; }
  if (lbMac) await tryApi("/api/mac_photo_delete", { name: lbMac }, "Deleted");
  else await wp("delete_image", { id: lbId }, "Deleted");
  $("#lightbox").classList.remove("on"); loadPhotos();
});

/* ---------------- brain & memory ---------------- */
let SET = null;
const KEY_HELP = { anthropic: ["Anthropic API key", "console.anthropic.com"], chatgpt: ["OpenAI API key", "platform.openai.com"],
  gemini: ["Gemini API key", "aistudio.google.com (free tier available)"] };
async function loadBrain() {
  try { SET = await api("/api/settings"); } catch { return; }
  const br = SET.brain;
  segSet("#provider", br.provider); await providerUI(br.model);
  segSet("#style", (SET.app.persona || {}).style || "vector"); styleHelp();
  $("#owner").value = br.owner; $("#projects").checked = !!br.projects_dir;
  if (document.activeElement !== $("#about-me")) $("#about-me").value = br.about_me || "";
  loadMemory();
}
async function providerUI(current) {
  const p = $("#provider .on")?.dataset.v || "ollama";
  $("#row-key").style.display = p === "ollama" ? "none" : "";
  if (KEY_HELP[p]) {
    $("#key-label").firstChild.textContent = KEY_HELP[p][0];
    $("#key-help").textContent = "From " + KEY_HELP[p][1];
    const hint = SET?.brain.keys[p];
    $("#api-key").value = ""; $("#api-key").placeholder = hint ? `Saved (${hint})` : "Paste key";
  }
  let models = [];
  try { models = await api("/api/models?provider=" + p); } catch { }
  if (!models.length) models = p === "ollama" ? ["gemma3:4b"] : p === "chatgpt" ? ["gpt-5.5"] : p === "gemini" ? ["(save your key to load models)"] : [];
  $("#model").innerHTML = models.map(m => `<option>${esc(m)}</option>`).join("");
  if (current && models.includes(current)) $("#model").value = current;
}
segBind("#provider", () => providerUI());
const STYLE_HELP = { vector: "Playful little robot", jarvis: "Calm, witty and quick. Calls you sir and suggests next steps." };
function styleHelp() { $("#style-help").textContent = STYLE_HELP[$("#style .on")?.dataset.v || "vector"]; }
segBind("#style", async v => { styleHelp(); await tryApi("/api/settings", { app: { persona: { style: v } } }, v === "vector" ? "Back to classic Vector" : v.toUpperCase() + " mode on"); });
$("#brain-save").addEventListener("click", async () => {
  const provider = $("#provider .on")?.dataset.v || "ollama";
  const key = $("#api-key").value.trim();
  if (provider !== "ollama" && !key && !SET?.brain.keys[provider]) return toast("Paste your API key first", true);
  const body = { brain: { provider, owner: $("#owner").value, projects_dir: $("#projects").checked ? "~/GitHub" : "",
    about_me: $("#about-me").value, keys: key ? { [provider]: key } : {} } };
  // first save stores the key so the model list can load; then save the chosen model
  let r = await tryApi("/api/settings", body);
  if (!r) return;
  SET.brain = r.brain; await providerUI();
  const model = $("#model").value;
  if (model && !model.startsWith("(")) r = await tryApi("/api/settings", { brain: { provider, model } }, "Brain restarted");
  if (r) { $("#api-key").value = ""; $("#brain-saved").textContent = "Saved"; setTimeout(() => $("#brain-saved").textContent = "", 2500); loadBrain(); }
});
let MEM = { memory: [], todo: [] };
async function loadMemory() {
  try { MEM = await api("/api/memory"); } catch { return; }
  $("#mem").innerHTML = MEM.memory.length ? MEM.memory.map((m, i) =>
    `<div class="row" data-i="${i}"><div class="li-text">${esc(m.text)}<small>${esc((m.at || "").replace("T", " "))}</small></div><button class="icon-btn del">${svg("trash")}</button></div>`).join("")
    : `<div class="empty">Nothing yet.</div>`;
  $("#todo").innerHTML = MEM.todo.length ? MEM.todo.map((t, i) =>
    `<div class="row" data-i="${i}"><label class="check"><input type="checkbox" class="done"><span></span></label><div class="li-text">${esc(t)}</div><button class="icon-btn del">${svg("trash")}</button></div>`).join("")
    : `<div class="empty">Your list is empty.</div>`;
  $$("#mem .del").forEach(b => b.addEventListener("click", () => { MEM.memory.splice(+b.closest(".row").dataset.i, 1); saveMem(); }));
  $$("#todo .del, #todo .done").forEach(b => b.addEventListener(b.classList.contains("done") ? "change" : "click", () => {
    setTimeout(() => { MEM.todo.splice(+b.closest(".row").dataset.i, 1); saveMem(); }, b.classList.contains("done") ? 350 : 0);
  }));
}
async function saveMem() { await tryApi("/api/memory", { memory: MEM.memory, todo: MEM.todo }); loadMemory(); }
$("#todo-new").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.value.trim()) { MEM.todo.push(e.target.value.trim()); e.target.value = ""; saveMem(); } });

/* ---------------- notifications ---------------- */
async function loadNotify() {
  try { SET = await api("/api/settings"); } catch { return; }
  const n = SET.app.notify, q = SET.app.quiet_hours;
  $$("[data-n]").forEach(el => {
    if (el.type === "checkbox") el.checked = !!n[el.dataset.n];
    else renderStepper(el, n[el.dataset.n]);
  });
  $("#qh-on").checked = q.enabled; $("#qh-start").value = q.start; $("#qh-end").value = q.end;
  loadHookLog();
}
function renderStepper(el, v) {
  el.dataset.v = v;
  el.innerHTML = `<button>-</button><span>${v}${el.dataset.unit}</span><button>+</button>`;
  const [minus, plus] = el.querySelectorAll("button");
  const set = d => { const nv = Math.max(+el.dataset.min, +el.dataset.v + d); renderStepper(el, nv); saveNotify(); };
  minus.onclick = () => set(-el.dataset.step); plus.onclick = () => set(+el.dataset.step);
}
const saveNotify = debounce(async () => {
  const notify = {};
  $$("[data-n]").forEach(el => notify[el.dataset.n] = el.type === "checkbox" ? el.checked : +el.dataset.v);
  const r = await tryApi("/api/settings", { app: { notify, quiet_hours: { enabled: $("#qh-on").checked, start: $("#qh-start").value, end: $("#qh-end").value } } });
  if (r) { $("#notify-saved").textContent = "Saved"; setTimeout(() => $("#notify-saved").textContent = "", 1500); }
}, 300);
$$("#notify input").forEach(i => i.addEventListener("change", saveNotify));
$("#test-notify").addEventListener("click", async () => { await tryApi("/api/test_notify", {}, "Vector should speak in a moment"); setTimeout(loadHookLog, 6000); });
async function loadHookLog() {
  try { const l = await api("/api/logs"); $("#hooklog").textContent = l.hook.filter(x => /^\d{4}-\d\d-\d\d /.test(x)).reverse().join("\n") || "No announcements yet."; } catch { }
}

/* ---------------- diagnostics ---------------- */
async function loadAbout() {
  await refreshStatus();
  const bot = ST.robot || {}, b = ST.battery || {};
  let br = {}; try { br = (await api("/api/settings")).brain; } catch { }
  const rows = [["Serial number", bot.esn || "--"], ["IP address", bot.ip_address || "--"],
    ["Battery voltage", b.battery_volts ? b.battery_volts.toFixed(2) + " V" : "--"],
    ["Brain", br.backend ? (br.backend === "anthropic" ? "Claude" : "Local model") + (br.model ? " (" + br.model + ")" : "") : "--"],
    ["wire-pod", ST.wirepod ? "Running on this Mac" : "Not running"]];
  $("#about-rows").innerHTML = rows.map(([k, v]) => `<div class="row"><div class="rl">${k}</div><div class="rr">${esc(v)}</div></div>`).join("");
  try {
    let s = await api("/api/stats"); if (s.raw) s = JSON.parse(s.raw);
    const flat = {}; (function f(o, p) { for (const [k, v] of Object.entries(o || {})) typeof v === "object" ? f(v, p + k + ".") : flat[p + k] = v; })(s, "");
    const LABELS = { "Alive.seconds": "Time awake (lifetime)", "BStat.ReactedToTriggerWord": 'Times he answered "Hey Vector"',
      "Pet.ms": "Time petted", "Stim.CumlPosDelta": "Happiness points", "BStat.PetMinutes": "Minutes petted" };
    for (const k of Object.keys(flat)) if (!(k in LABELS)) delete flat[k];  // hide raw internal counters
    const nice = k => LABELS[k] || k.replace(/^(Alive|BStat|Stim|FeatureType|Feature)\./, "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[._]/g, " ").replace(/^\w/, c => c.toUpperCase());
    const fmt = (k, v) => /seconds?$|Sec$/i.test(k) ? (v / 3600).toFixed(1) + " hours" : /\.ms$/.test(k) ? (v / 60000).toFixed(1) + " minutes" : Number(v).toLocaleString();
    const items = Object.entries(flat).filter(([, v]) => typeof v === "number" && v > 0).slice(0, 12);
    $("#stats").innerHTML = items.length ? items.map(([k, v]) => `<div class="row"><div class="rl">${esc(nice(k))}</div><div class="rr">${esc(fmt(k, v))}</div></div>`).join("") : `<div class="empty">No stats available.</div>`;
  } catch { $("#stats").innerHTML = `<div class="empty">No stats available.</div>`; }
  try {
    const n = await api("/api/companion/stats");
    const rows = [["Wi-Fi", n.verdict], ["Wi-Fi drops", `${n.drops_1h} in the last hour, ${n.drops_24h} today` + (n.last_drops.length ? ` (last: ${n.last_drops.slice(-3).join(", ")})` : "")],
      ['"Hey Vector" heard', `${n.wake_words_24h} time${n.wake_words_24h === 1 ? "" : "s"}` + (n.last_wake ? `, last at ${n.last_wake}` : "") + ". If he doesn't light up when you say it, his microphones didn't catch it."],
      ["Voice", n.voice === "mac" ? "JARVIS voice (Mac)" : "His own voice"], ["Cube", n.cube ? "Connected" : "Not connected"]];
    $("#net-rows").innerHTML = rows.map(([k, v]) => `<div class="row"><div class="rl">${k}</div><div class="rr wrap-text">${esc(v)}</div></div>`).join("");
  } catch { $("#net-rows").innerHTML = `<div class="empty">The companion isn't running.</div>`; }
  try { const l = await api("/api/logs"); $("#brainlog").textContent = l.brain.filter(x => !/GET \/health/.test(x) && x.trim() !== "[brain]").slice(-30).join("\n") || "Nothing yet."; } catch { }
}
$("#brain-restart").addEventListener("click", () => tryApi("/api/brain/restart", {}, "Brain restarted"));
$("#release").addEventListener("click", () => tryApi("/api/release", {}, "Vector is free"));

/* ---------------- scan & ask ---------------- */
async function startScan() {
  const img = $("#scam"), msg = $("#scam-msg");
  msg.style.display = "flex"; msg.textContent = "Connecting to camera...";
  try {
    const { url } = await api("/api/camera_url");
    img.onload = () => { msg.style.display = "none"; };
    img.onerror = () => { msg.textContent = "Camera unavailable"; };
    img.src = url + "&t=" + Date.now();
  } catch (e) { msg.textContent = friendly(e.message); }
  loadScans();
}
function stopScanCam() { $("#scam").removeAttribute("src"); }
segBind("#scan-mode", () => { });
function md(t) {  // small, safe Markdown renderer
  const lines = esc(t || "").split("\n"); let out = "", list = null, code = false;
  const inline = x => x.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|\W)\*([^*]+)\*(?=\W|$)/g, "$1<i>$2</i>");
  const close = () => { if (list) { out += `</${list}>`; list = null; } };
  for (const l of lines) {
    if (l.startsWith("```")) { close(); out += code ? "</pre>" : "<pre>"; code = !code; continue; }
    if (code) { out += l + "\n"; continue; }
    let m;
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) { close(); out += `<h3>${inline(m[2])}</h3>`; }
    else if ((m = l.match(/^\s*[-*]\s+(.*)/))) { if (list !== "ul") { close(); out += "<ul>"; list = "ul"; } out += `<li>${inline(m[1])}</li>`; }
    else if ((m = l.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); out += "<ol>"; list = "ol"; } out += `<li>${inline(m[1])}</li>`; }
    else if (!l.trim()) { close(); }
    else { close(); out += `<p>${inline(l)}</p>`; }
  }
  close(); return out;
}
let lastScan = null;
function showScan(r) {
  lastScan = r; $("#scan-result").hidden = false;
  $("#res-img").src = "/api/scan_image/" + r.id;
  $("#res-title").textContent = r.title || "Scan";
  $("#res-meta").textContent = `${(r.at || "").replace("T", " ")} · ${r.model} · ${r.seconds}s`;
  $("#res-say").textContent = r.say || "";
  $("#res-body").innerHTML = md(r.text);
}
$("#res-copy").addEventListener("click", async () => { if (!lastScan) return; await navigator.clipboard.writeText(lastScan.text); toast("Copied"); });
$("#scan-go").addEventListener("click", async () => {
  const b = $("#scan-go"); if (b.disabled) return;
  b.disabled = true; b.classList.add("scan-busy"); const label = b.innerHTML; b.textContent = "Hold it steady... Vector is reading";
  try {
    const r = await api("/api/companion/scan", { mode: $("#scan-mode .on")?.dataset.v || "explain", question: $("#scan-q").value, countdown: true });
    showScan(r.result); loadScans(); $("#scan-q").value = "";
  } catch (e) { toast(e.message.length < 140 ? e.message : "Scan failed. Is the companion running?", true); }
  finally { b.disabled = false; b.classList.remove("scan-busy"); b.innerHTML = label; }
});
async function loadScans() {
  let h = []; try { h = await api("/api/scans"); } catch { }
  $("#scan-hist").innerHTML = h.length ? h.map((r, i) => `<div class="row" data-i="${i}"><img class="hist-img" src="/api/scan_image/${r.id}" alt=""><div class="li-text">${esc(r.say || r.title)}<small>${esc(r.title)} · ${esc((r.at || "").replace("T", " "))}</small></div></div>`).join("")
    : `<div class="empty">No scans yet.</div>`;
  $$("#scan-hist .row").forEach(row => row.addEventListener("click", () => { showScan(h[+row.dataset.i]); $("#main").scrollTop = 0; }));
}

/* ---------------- personality ---------------- */
let ANIMS = [];
async function loadPersonality() {
  let h = {}; try { h = await api("/api/companion/health"); } catch { }
  $("#comp-state").innerHTML = h.connected ? '<span class="ok">Connected</span>' : h.running === false ? '<span class="bad">Not running</span>' : '<span class="bad">Can\'t reach Vector</span>';
  $("#comp-err").textContent = h.connected ? "" : (h.error || "");
  let st = {}; try { st = (await api("/api/settings")).app.companion; } catch { }
  $$("[data-c]").forEach(el => { if (el.type === "checkbox") el.checked = !!st[el.dataset.c]; else renderStepperC(el, st[el.dataset.c] ?? 25); });
  $("#focus-state").textContent = h.focus ? `${Math.ceil(h.focus.left_s / 60)} of ${h.focus.total} min left` : "No timer running";
  if (!ANIMS.length && h.connected) { try { ANIMS = await api("/api/companion_anims"); } catch { } }
  renderAnims();
}
function renderStepperC(el, v) {
  el.dataset.v = v;
  el.innerHTML = `<button>-</button><span>${v}${el.dataset.unit}</span><button>+</button>`;
  const [minus, plus] = el.querySelectorAll("button");
  const set = d => { renderStepperC(el, Math.max(+el.dataset.min, +el.dataset.v + d)); saveComp(); };
  minus.onclick = () => set(-el.dataset.step); plus.onclick = () => set(+el.dataset.step);
}
const saveComp = debounce(() => {
  const companion = {};
  $$("[data-c]").forEach(el => companion[el.dataset.c] = el.type === "checkbox" ? el.checked : +el.dataset.v);
  tryApi("/api/settings", { app: { companion } }, "Saved");
}, 300);
$$("#personality input[type=checkbox]").forEach(i => i.addEventListener("change", saveComp));
$("#focus-go").addEventListener("click", async () => { await tryApi("/api/companion/focus", { minutes: +$('[data-c="focus_minutes"]').dataset.v }, "Focus timer started"); loadPersonality(); syncLive(); });
$("#focus-stop").addEventListener("click", async () => { await tryApi("/api/companion/focus", { stop: true }, "Timer stopped"); loadPersonality(); syncLive(); });
$$("[data-face]").forEach(b => b.addEventListener("click", () => tryApi("/api/companion/face", { icon: b.dataset.face, seconds: 3 })));
$("#face-text").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.value.trim()) { tryApi("/api/companion/face", { text: e.target.value.trim(), seconds: 5 }); e.target.value = ""; } });
$("#brief-test").addEventListener("click", async () => {
  const r = await tryApi("/api/companion/greet_test", {}); if (r) { toast("Briefing: " + r.text.slice(0, 80) + "..."); tryApi("/api/companion/say", { text: r.text }); }
});
const pretty = t => t.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/\bRtp\b/g, "").replace(/\s+/g, " ").trim();
function renderAnims() {
  const q = $("#anim-q").value.toLowerCase().replace(/\s+/g, "");
  const list = ANIMS.filter(a => !/^Invalid|^Already|Test|Debug|^Dev/.test(a) && a.toLowerCase().replace(/_/g, "").includes(q)).slice(0, 300);
  $("#anim-count").textContent = ANIMS.length ? `${ANIMS.length} built in` : "(connect Vector to load)";
  $("#anim-list").innerHTML = list.map(a => `<button data-a="${esc(a)}" title="${esc(a)}">${esc(pretty(a))}</button>`).join("");
  $$("#anim-list button").forEach(b => b.addEventListener("click", () => tryApi("/api/companion/anim", { name: b.dataset.a }, "Playing")));
}
$("#anim-q").addEventListener("input", renderAnims);

/* ---------------- generic settings binder: data-k="section.key" ---------------- */
let APP = {};
const kget = k => k.split(".").reduce((o, p) => (o || {})[p], APP);
function fillK(root) {
  $$(root + " [data-k]").forEach(el => {
    const v = kget(el.dataset.k);
    if (el.classList.contains("seg")) el.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === String(v)));
    else if (el.type === "checkbox") el.checked = !!v;
    else if (v !== undefined && document.activeElement !== el) el.value = v;
  });
}
function saveK(el, value) {
  const [sec, key] = el.dataset.k.split(".");
  const num = el.type === "range" || typeof (APP[sec] || {})[key] === "number";
  const val = num ? +value : value;
  (APP[sec] = APP[sec] || {})[key] = val;
  tryApi("/api/settings", { app: { [sec]: { [key]: val } } }, "Saved");
}
$$("[data-k]").forEach(el => {
  if (el.classList.contains("seg")) el.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    el.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); saveK(el, b.dataset.v); }));
  else if (el.type === "checkbox") el.addEventListener("change", () => saveK(el, el.checked));
  else el.addEventListener("change", () => saveK(el, el.value));
});
async function loadK(root) { try { APP = (await api("/api/settings")).app; } catch { } fillK(root); }

/* ---------------- hey jarvis ---------------- */
let earsT = null;
async function loadJarvis() {
  await loadK("#jarvis");
  if (!$("#voices").options.length) {
    let v = []; try { v = await api("/api/voices"); } catch { }
    const NOVELTY = /^(Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Good News|Jester|Junior|Organ|Ralph|Superstar|Trinoids|Whisper|Wobble|Zarvox|Fred|Kathy|Grandma|Grandpa|Rocko)\b/;
    v = v.filter(n => !NOVELTY.test(n));
    const cur = kget("voice.mac_voice") || "Daniel";
    if (!v.includes(cur)) v.unshift(cur);
    $("#voices").innerHTML = v.map(n => `<option${n === cur ? " selected" : ""}>${esc(n)}</option>`).join("");
  }
  loadTts();
  refreshEars(); clearInterval(earsT); earsT = setInterval(() => current === "jarvis" ? refreshEars() : clearInterval(earsT), 1500);
}
async function refreshEars() {
  let e = {}; try { e = await api("/api/ears"); } catch { }
  const age = e.at ? (Date.now() / 1000 - e.at) : 1e9;
  const running = e.running;
  const st = !running ? '<span class="bad">Not running</span>' : e.state === "error" ? `<span class="bad">Microphone problem</span>`
    : /listening for '/.test(e.state || "") ? `<span class="ok">${esc(e.state.replace("listening for", "Listening for"))}</span>` : e.state === "mic off" ? '<span class="mute">Mic off</span>'  : esc(e.state || "--");
  $("#ears-state").innerHTML = st;
  const meter = e.peak !== undefined ? ` · mic ${e.mic_silent ? "SILENT" : Math.round(e.peak)} · best match ${Math.round((e.best_score || 0) * 100)}%` : "";
  $("#ears-sub").textContent = e.error ? e.error : running ? `Heard his name ${e.heard || 0} time${e.heard === 1 ? "" : "s"}${meter}` : "Click Restart Ears, then allow the microphone";
  if (e.mic_silent && running) $("#ears-state").innerHTML = '<span class="bad">Microphone blocked</span>';
  $("#ears-text").textContent = e.last_text ? `"${e.last_text}"` : "--";
  $("#ears-reply").textContent = e.last_reply ? "Reply: " + e.last_reply.slice(0, 140) : "";
}
$("#ears-restart").addEventListener("click", async () => { await tryApi("/api/ears/restart", {}, "Restarting Ears"); setTimeout(refreshEars, 2500); });
let ttsT;
async function loadTts() {
  let t = {}; try { t = await api("/api/tts"); } catch { return; }
  const sel = $("#piper-voices");
  sel.innerHTML = Object.entries(t.voices || {}).map(([k, v]) => `<option value="${k}"${k === t.chosen ? " selected" : ""}>${esc(v.label)}${v.installed ? "" : " (download)"}</option>`).join("");
  const cur = (t.voices || {})[sel.value] || {};
  const busy = t.state && /installing|downloading/.test(t.state) && Date.now() / 1000 - (t.at || 0) < 900;
  $("#tts-get").hidden = !!cur.installed || busy;
  $("#tts-sub").textContent = busy ? t.state + "..." : t.state === "error" ? "Download failed: " + (t.error || "") : !t.piper ? "Not installed yet" : cur.installed ? "Ready" : "Not downloaded";
  clearTimeout(ttsT); if (busy && current === "jarvis") ttsT = setTimeout(loadTts, 2000);
}
$("#piper-voices").addEventListener("change", async e => {
  await tryApi("/api/settings", { app: { voice: { piper_voice: e.target.value } } }, "Voice chosen");
  loadTts();
});
$("#tts-get").addEventListener("click", async () => { await tryApi("/api/tts/install", { voice: $("#piper-voices").value }, "Downloading voice"); setTimeout(loadTts, 800); });
$("#voice-try-btn").addEventListener("click", () => tryApi("/api/companion/say", { text: $("#voice-try").value }, "Speaking"));

/* ---------------- desk guard + cube ---------------- */
async function loadGuard() {
  await loadK("#guard");
  let g = {}, h = {}; try { g = await api("/api/companion/guard"); } catch { }
  try { h = await api("/api/companion/health"); } catch { }
  $("#guard-on").checked = !!g.on;
  $("#guard-state").textContent = g.on ? `Watching since ${new Date(g.since * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · ${g.events.length} event${g.events.length === 1 ? "" : "s"}` : "Off";
  const ev = (g.events || []).filter(e => e.photo).slice(-12).reverse();
  $("#guard-events").innerHTML = ev.length ? ev.map(e => `<img src="/api/guard_photo/${encodeURIComponent(e.photo)}" title="${new Date(e.at * 1000).toLocaleTimeString()}">`).join("")
    : `<div class="empty">${g.on ? "Nothing yet. All quiet." : "Turn on desk guard or say \"Hey Jarvis, guard my desk\"."}</div>`;
  $("#cube-state").innerHTML = h.cube ? '<span class="ok">Connected</span>' : '<span class="mute">Not connected</span>';
  $("#cube-sub").textContent = h.cube ? "Tap it to try" : "Put it near him and press Connect. Needs an N battery (E90 / LR1).";
}
$("#guard-on").addEventListener("change", async e => {
  await tryApi("/api/companion/guard", { on: e.target.checked, report: false }, e.target.checked ? "Desk guard on" : "Desk guard off"); loadGuard();
});
$("#cube-connect").addEventListener("click", async () => { await tryApi("/api/companion/cube", { connect: true }, "Looking for the cube..."); setTimeout(loadGuard, 12000); });
$("#cube-light").addEventListener("click", () => tryApi("/api/companion/cube", { color: "blue", seconds: 3 }));
setInterval(() => { if (current === "guard") loadGuard(); }, 8000);

/* ---------------- live state: keep the app matched to what he's doing ----------------
   Games, timers and modes can start from the app, by voice or from the cube, so read them from him every few seconds. */
let LIVE = {};
async function syncLive() {
  let h; try { h = await api("/api/companion/health"); } catch { return; }
  if (!h) return;
  LIVE = h;
  const mm = s => `${Math.floor(s / 60)}:${String(Math.max(0, s % 60)).padStart(2, "0")}`;
  // sidebar chip
  const parts = [];
  if (h.focus) {
    const done = 1 - h.focus.left_s / (h.focus.total * 60);
    parts.push(`<b>Studying</b> <span class="sub">${mm(h.focus.left_s)} left${h.focus.goal ? " · " + esc(h.focus.goal) : ""}</span><div class="bar"><i style="width:${Math.round(Math.min(1, Math.max(0, done)) * 100)}%"></i></div>`);
  }
  if (h.game && h.game.active) parts.push(`<b>Blackjack</b> <span class="sub">you have ${h.game.you_total}</span>`);
  if (h.quiz_state) parts.push(`<b>Quiz</b> <span class="sub">question ${h.quiz_state.q} of ${h.quiz_state.of} · ${h.quiz_state.score} right</span>`);
  if (h.mirror) parts.push(`<b>Camera on his face</b>`);
  if (h.guard) parts.push(`<b>Guarding your desk</b>`);
  if (h.speaking && !parts.length) parts.push(`<span class="sub">Speaking...</span>`);
  const now = $("#sb-now");
  now.hidden = !parts.length || !h.connected;
  now.innerHTML = parts.join("<br>");
  // blackjack panel
  const g = h.game, bj = $("#bj");
  bj.classList.toggle("on", !!g);
  if (g) {
    $("#bj-title").textContent = g.active ? "Blackjack" : `Blackjack: ${g.result}`;
    $("#bj-hand").innerHTML = `You: <b>${g.you.map(esc).join(", ")}</b> (${g.you_total}) · Vector: <b>${g.me.map(esc).join(", ")}</b>${g.me_total != null ? ` (${g.me_total})` : ", one card hidden"}`;
  }
  $("#bj-hit").disabled = $("#bj-stand").disabled = !(g && g.active);
  // focus line on the Personality page
  const fs = $("#focus-state");
  if (fs) fs.textContent = h.focus ? `${Math.ceil(h.focus.left_s / 60)} of ${h.focus.total} min left${h.focus.goal ? " · " + h.focus.goal : ""}` : "No timer running";
  const mirror = $('[data-wp="mirror_mode"], #mirror');
  if (mirror && mirror.type === "checkbox") mirror.checked = !!h.mirror;
  const gOn = $("#guard-on");
  if (gOn && document.activeElement !== gOn) gOn.checked = !!h.guard;
}
setInterval(syncLive, 2500);
syncLive();

/* ---------------- boot ---------------- */
go("overview");
refreshStatus(); loadRobotSettings();
setInterval(refreshStatus, 6000);
setInterval(() => { if (current === "notify") loadHookLog(); }, 5000);
setInterval(() => { if (current === "overview") loadToday(); }, 30000);

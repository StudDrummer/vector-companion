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
  if (!r.ok || j.ok === false) throw new Error(j.error || r.statusText);
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
const intent = (name, label) => wp("cloud_intent", { intent: name }, label || "Sent to Vector");
const say = text => text.trim() && tryApi("/api/say", { text }, "Speaking");

/* ---------------- navigation ---------------- */
const hooks = { drive: [enterDrive, leaveDrive], scan: [startScan, stopScanCam], personality: [loadPersonality], people: [loadFaces], photos: [loadPhotos], brain: [loadBrain],
  notify: [loadNotify], about: [loadAbout], eyes: [loadRobotSettings], general: [loadRobotSettings], voice: [loadRobotSettings] };
let current = null;
function go(id) {
  if (current === id) return;
  if (current && hooks[current] && hooks[current][1]) hooks[current][1]();
  if (current === "drive") stopCam();
  current = id;
  $$(".page").forEach(p => p.classList.toggle("on", p.id === id));
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.go === id));
  if (hooks[id] && hooks[id][0]) hooks[id][0]();
  if (id === "general") loadSafety();
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
  return { pct: [0.12, 0.33, 0.66, 1][lvl] ?? 0.5, word: words[lvl] ?? "--", charging: b.is_charging,
    onCharger: b.is_on_charger_platform };
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
$("#vo-listen").addEventListener("click", () => wp("trigger_wake_word", {}, "Vector is listening"));
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
  ["dance", "Dance", "music", "#ff375f"], ["explore", "Explore", "compass", "#30d158"],
  ["come_here", "Come here", "arrowdown", "#0a84ff"], ["look_at_me", "Look at me", "eye", "#64d2ff"],
  ["fetch_cube", "Fetch cube", "cube", "#ff9f0a"], ["roll_cube", "Roll cube", "roll", "#ffd60a"],
  ["pop_a_wheelie", "Wheelie", "wheel", "#bf5af2"], ["blackjack", "Blackjack", "cards", "#5e5ce6"],
  ["take_photo", "Take photo", "camera", "#8e8e93"], ["go_to_charger", "Go home", "bolt", "#30d158"],
  ["sleep", "Sleep", "moon", "#5e5ce6"], ["_listen", "Listen", "mic", "#ff453a"],
];
$("#tiles").innerHTML = TILES.map(([k, l, i, c]) =>
  `<button class="tile" data-a="${k}"><span class="ti" style="--c:${c}">${svg(i)}</span><b>${l}</b></button>`).join("");
$$(".tile").forEach(t => t.addEventListener("click", async () => {
  t.classList.add("busy"); setTimeout(() => t.classList.remove("busy"), 1600);
  if (t.dataset.a === "_listen") wp("trigger_wake_word", {}, "Vector is listening");
  else intent(t.dataset.a, t.querySelector("b").textContent);
}));
$$("[data-intent]").forEach(b => b.addEventListener("click", () => intent(b.dataset.intent, b.textContent.trim())));
$("#qa-listen").addEventListener("click", () => wp("trigger_wake_word", {}, "Vector is listening"));
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
  if (!Array.isArray(list)) list = list.faces || [];
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
  let ids;
  try { ids = await api("/api/photos"); } catch (e) { g.innerHTML = `<div class="empty">${esc(friendly(e.message))}</div>`; return; }
  if (!Array.isArray(ids) || !ids.length) { g.innerHTML = `<div class="empty">No photos yet.</div>`; return; }
  g.innerHTML = ids.slice().reverse().map(id => `<img data-id="${id}" src="/api/photo?thumb=1&id=${id}" loading="lazy" alt="">`).join("");
  $$("#photo-grid img").forEach(i => i.addEventListener("click", () => {
    lbId = i.dataset.id; $("#lb-img").src = "/api/photo?id=" + lbId; $("#lightbox").classList.add("on");
  }));
}
$("#ph-refresh").addEventListener("click", loadPhotos);
$("#lb-close").addEventListener("click", () => $("#lightbox").classList.remove("on"));
$("#lightbox").addEventListener("click", e => { if (e.target.id === "lightbox") $("#lightbox").classList.remove("on"); });
$("#lb-del").addEventListener("click", async e => {
  const b = e.currentTarget;
  if (!b.dataset.armed) { b.dataset.armed = 1; b.textContent = "Delete forever?"; setTimeout(() => { delete b.dataset.armed; b.textContent = "Delete"; }, 2500); return; }
  await wp("delete_image", { id: lbId }, "Deleted"); $("#lightbox").classList.remove("on"); loadPhotos();
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
  if (!models.length) models = p === "ollama" ? ["llama3.2:3b"] : p === "chatgpt" ? ["gpt-5.5"] : p === "gemini" ? ["(save your key to load models)"] : [];
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
  try { const l = await api("/api/logs"); $("#hooklog").textContent = l.hook.slice().reverse().join("\n") || "No announcements yet."; } catch { }
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
    const LABELS = { "Alive.seconds": "Time alive", "Alive.distance_cm": "Distance driven", "BStat.PetMinutes": "Minutes petted",
      "Stim.CumlPosDelta": "Happy moments", "Alive.num_wake_word": "Times called" };
    const nice = k => LABELS[k] || k.replace(/^(Alive|BStat|Stim|FeatureType|Feature)\./, "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[._]/g, " ").replace(/^\w/, c => c.toUpperCase());
    const fmt = (k, v) => /seconds?$|Sec$/i.test(k) ? (v / 3600).toFixed(1) + " h" : /cm$/i.test(k) ? (v / 100).toFixed(1) + " m" : String(v);
    const items = Object.entries(flat).filter(([, v]) => typeof v === "number" && v > 0).slice(0, 12);
    $("#stats").innerHTML = items.length ? items.map(([k, v]) => `<div class="row"><div class="rl">${esc(nice(k))}</div><div class="rr">${esc(fmt(k, v))}</div></div>`).join("") : `<div class="empty">No stats available.</div>`;
  } catch { $("#stats").innerHTML = `<div class="empty">No stats available.</div>`; }
  try { const l = await api("/api/logs"); $("#brainlog").textContent = l.brain.slice(-30).join("\n") || "Empty."; } catch { }
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
$("#focus-go").addEventListener("click", async () => { await tryApi("/api/companion/focus", { minutes: +$('[data-c="focus_minutes"]').dataset.v }, "Focus timer started"); loadPersonality(); });
$("#focus-stop").addEventListener("click", async () => { await tryApi("/api/companion/focus", { stop: true }, "Timer stopped"); loadPersonality(); });
$$("[data-face]").forEach(b => b.addEventListener("click", () => tryApi("/api/companion/face", { icon: b.dataset.face, seconds: 3 })));
$("#face-text").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.value.trim()) { tryApi("/api/companion/face", { text: e.target.value.trim(), seconds: 5 }); e.target.value = ""; } });
$("#brief-test").addEventListener("click", async () => {
  const r = await tryApi("/api/companion/greet_test", {}); if (r) { toast("Briefing: " + r.text.slice(0, 80) + "..."); tryApi("/api/companion/say", { text: r.text }); }
});
const pretty = t => t.replace(/([a-z])([A-Z])/g, "$1 $2");
function renderAnims() {
  const q = $("#anim-q").value.toLowerCase().replace(/\s+/g, "");
  const list = ANIMS.filter(a => a.toLowerCase().includes(q)).slice(0, 300);
  $("#anim-count").textContent = ANIMS.length ? `${ANIMS.length} built in` : "(connect Vector to load)";
  $("#anim-list").innerHTML = list.map(a => `<button data-a="${esc(a)}" title="${esc(a)}">${esc(pretty(a))}</button>`).join("");
  $$("#anim-list button").forEach(b => b.addEventListener("click", () => tryApi("/api/companion/anim", { name: b.dataset.a }, "Playing")));
}
$("#anim-q").addEventListener("input", renderAnims);

/* ---------------- boot ---------------- */
go("overview");
refreshStatus(); loadRobotSettings();
setInterval(refreshStatus, 6000);
setInterval(() => { if (current === "notify") loadHookLog(); }, 5000);

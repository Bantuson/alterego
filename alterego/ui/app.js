/* The studio frontend.
 *
 * The constellation is not decoration: it renders the user's real
 * 478 scanned landmarks, and the knob morphs use the SAME control-
 * point rules as alterego/disguise.py (ported below). Points glow
 * green exactly where — and exactly as much as — the disguise will
 * move real pixels. Truthful previews (PRODUCT.md, principle 4).
 */
import * as THREE from "/three.module.min.js";

/* ---------- the warp math, ported from disguise.py ---------- */

const POINT = {
  chin: 152, jaw_left: 397, jaw_right: 172,
  cheek_left: 454, cheek_right: 234,
  nose_tip: 4, nose_bridge: 6, nostril_left: 327, nostril_right: 98,
  eye_outer_left: 263, eye_inner_left: 362,
  eye_outer_right: 33, eye_inner_right: 133,
  mouth_left: 291, mouth_right: 61, lip_top: 13, lip_bottom: 14,
  brow_left: 334, brow_right: 105,
};

const KNOBS = [
  "jaw_width", "chin_length", "eye_spacing", "nose_length",
  "nose_width", "mouth_width", "lip_fullness", "brow_height",
];

/* Mirror of control_shifts(): same landmarks, same axes, same
 * magic numbers. If disguise.py changes, change this too. */
function controlShifts(pts, knobs) {
  const p = {};
  for (const [name, i] of Object.entries(POINT)) p[name] = pts[i];
  const faceWidth = Math.hypot(
    p.cheek_left[0] - p.cheek_right[0], p.cheek_left[1] - p.cheek_right[1]);
  const centerX = (p.cheek_left[0] + p.cheek_right[0]) / 2;
  const out = (pt) => (pt[0] > centerX ? 1 : -1);
  const moves = [];

  const jaw = knobs.jaw_width * 0.04 * faceWidth;
  for (const n of ["jaw_left", "jaw_right"]) moves.push([p[n], jaw * out(p[n]), 0]);
  for (const n of ["cheek_left", "cheek_right"]) moves.push([p[n], jaw * 0.5 * out(p[n]), 0]);
  moves.push([p.chin, 0, knobs.chin_length * 0.05 * faceWidth]);
  const eye = knobs.eye_spacing * 0.02 * faceWidth;
  for (const n of ["eye_outer_left", "eye_inner_left", "eye_outer_right", "eye_inner_right"])
    moves.push([p[n], eye * out(p[n]), 0]);
  moves.push([p.nose_tip, 0, knobs.nose_length * 0.04 * faceWidth]);
  const noseW = knobs.nose_width * 0.03 * faceWidth;
  for (const n of ["nostril_left", "nostril_right"]) moves.push([p[n], noseW * out(p[n]), 0]);
  const mouth = knobs.mouth_width * 0.03 * faceWidth;
  for (const n of ["mouth_left", "mouth_right"]) moves.push([p[n], mouth * out(p[n]), 0]);
  const lip = knobs.lip_fullness * 0.015 * faceWidth;
  moves.push([p.lip_top, 0, -lip]);
  moves.push([p.lip_bottom, 0, lip]);
  const brow = knobs.brow_height * 0.025 * faceWidth;
  moves.push([p.brow_left, 0, -brow]);
  moves.push([p.brow_right, 0, -brow]);
  return { moves, sigma: faceWidth * 0.18 };
}

/* Gaussian splat, per landmark (the pointwise displacement_field). */
function displaceAll(pts, knobs) {
  const { moves, sigma } = controlShifts(pts, knobs);
  const twoSigmaSq = 2 * sigma * sigma;
  return pts.map(([x, y, z]) => {
    let dx = 0, dy = 0, wsum = 0;
    for (const [[cx, cy], mx, my] of moves) {
      const w = Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / twoSigmaSq);
      dx += w * mx; dy += w * my; wsum += w;
    }
    const norm = Math.max(wsum, 1);
    return [x + dx / norm, y + dy / norm, z];
  });
}

/* ---------- three.js scene ---------- */

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const canvas = document.getElementById("stage");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
camera.position.z = 4.6;
const group = new THREE.Group();
scene.add(group);

const N = 478;
const positions = new Float32Array(N * 3);
const colors = new Float32Array(N * 3);
const velocities = new Float32Array(N * 3);
const targets = new Float32Array(N * 3);

/* Round glowing sprite so points render as orbs, not squares. */
function dotTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d").createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.4, "rgba(255,255,255,0.5)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  const ctx = c.getContext("2d");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
const points = new THREE.Points(geometry, new THREE.PointsMaterial({
  size: 0.045, map: dotTexture(), vertexColors: true, transparent: true,
  depthWrite: false, blending: THREE.AdditiveBlending,
}));
group.add(points);

let lines = null; // built after a scan (kNN over the real landmarks)

const BASE = new THREE.Color(0.36, 0.42, 0.62);   // resting ink-blue
const HOT = new THREE.Color(0.22, 0.9, 0.03);     // accent: warped points

/* Pre-scan idle: an anonymous, breathing shell of points. */
let scanned = null;   // raw scan (pixel space) once available
let normalized = null; // scan mapped into scene space
for (let i = 0; i < N; i++) {
  const phi = Math.acos(1 - 2 * (i + 0.5) / N);
  const theta = Math.PI * (1 + Math.sqrt(5)) * i;
  const r = 1.15;
  targets[i * 3] = r * Math.sin(phi) * Math.cos(theta);
  targets[i * 3 + 1] = r * Math.cos(phi) * 0.72;
  targets[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta) * 0.5;
  positions[i * 3] = (Math.random() - 0.5) * 8;
  positions[i * 3 + 1] = (Math.random() - 0.5) * 8;
  positions[i * 3 + 2] = (Math.random() - 0.5) * 8;
  BASE.toArray(colors, i * 3);
}

function normalizeScan(pts) {
  /* Pixel space -> scene space: center, scale by face height, flip Y
   * (screens grow downward, scenes grow upward). */
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(...ys) - Math.min(...ys);
  const s = 2.3 / span;
  return pts.map(([x, y, z]) => [(x - cx) * s, -(y - cy) * s, -z * s * 0.9]);
}

function setTargetsFromScan(knobs) {
  const displaced = displaceAll(scanned, knobs);
  normalized = normalizeScan(displaced);
  const rest = normalizeScan(scanned);
  for (let i = 0; i < N; i++) {
    targets[i * 3] = normalized[i][0];
    targets[i * 3 + 1] = normalized[i][1];
    targets[i * 3 + 2] = normalized[i][2];
    /* Color = truthful change map: how far this landmark moves. */
    const d = Math.hypot(
      normalized[i][0] - rest[i][0], normalized[i][1] - rest[i][1]);
    const heat = Math.min(d * 22, 1);
    const c = BASE.clone().lerp(HOT, heat);
    c.toArray(colors, i * 3);
  }
  geometry.attributes.color.needsUpdate = true;
}

function buildLines() {
  /* Faint web between each landmark and its 3 nearest neighbours —
   * turns a dust cloud into a readable face. Computed once. */
  const idx = [];
  for (let i = 0; i < N; i++) {
    const dists = [];
    for (let j = 0; j < N; j++) {
      if (i === j) continue;
      const dx = normalized[i][0] - normalized[j][0];
      const dy = normalized[i][1] - normalized[j][1];
      const dz = normalized[i][2] - normalized[j][2];
      dists.push([dx * dx + dy * dy + dz * dz, j]);
    }
    dists.sort((a, b) => a[0] - b[0]);
    for (let k = 0; k < 3; k++) idx.push(i, dists[k][1]);
  }
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute("position", geometry.attributes.position);
  lineGeo.setIndex(idx);
  lines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({
    color: 0x2b3a63, transparent: true, opacity: 0.28,
    depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  group.add(lines);
}

/* Spring integration: stiffness/damping per threejs-animation skill. */
const STIFF = 60, DAMP = 12;
const clock = new THREE.Clock();
let mouseX = 0, mouseY = 0;
addEventListener("pointermove", (e) => {
  mouseX = (e.clientX / innerWidth - 0.5) * 2;
  mouseY = (e.clientY / innerHeight - 0.5) * 2;
});

function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
}
addEventListener("resize", resize);
resize();

function animate() {
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.getElapsedTime();
  for (let i = 0; i < N * 3; i++) {
    if (reduceMotion) { positions[i] = targets[i]; continue; }
    const force = -STIFF * (positions[i] - targets[i]) - DAMP * velocities[i];
    velocities[i] += force * dt;
    positions[i] += velocities[i] * dt;
  }
  /* Ambient breath: the mirror is alive, faintly. */
  if (!reduceMotion) {
    group.rotation.y = Math.sin(t * 0.12) * 0.16 + mouseX * 0.14;
    group.rotation.x = mouseY * 0.08;
    points.material.size = 0.045 + Math.sin(t * 0.8) * 0.004;
  }
  geometry.attributes.position.needsUpdate = true;
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();

/* ---------- UI state & API ---------- */

const $ = (s) => document.querySelector(s);
const consoleEl = $("#console");
const pinned = [];
const rolling = [];

function log(text, cls = "") {
  (cls === "warn" || cls === "err" ? pinned : rolling).push({ text, cls });
  while (pinned.length > 5) pinned.shift();
  while (rolling.length > 9) rolling.shift();
  consoleEl.innerHTML = [...pinned, ...rolling]
    .map(l => `<div class="${l.cls}">${l.text.replace(/</g, "&lt;")}</div>`).join("");
}

const knobState = Object.fromEntries(KNOBS.map(k => [k, 0]));

function refreshConstellation() {
  if (scanned) setTargetsFromScan(knobState);
}

/* Faders */
const fadersEl = $("#faders");
for (const knob of KNOBS) {
  const row = document.createElement("div");
  row.className = "fader";
  row.innerHTML = `
    <label for="k-${knob}">${knob.replace("_", " ")}</label>
    <input type="range" id="k-${knob}" min="-1" max="1" step="0.01" value="0">
    <output id="o-${knob}">+0.00</output>`;
  fadersEl.appendChild(row);
  const input = row.querySelector("input");
  const out = row.querySelector("output");
  input.addEventListener("input", () => {
    knobState[knob] = parseFloat(input.value);
    const v = knobState[knob];
    out.textContent = (v >= 0 ? "+" : "") + v.toFixed(2);
    out.classList.toggle("hot", Math.abs(v) > 0.005);
    refreshConstellation();
  });
}

function setKnobs(values) {
  for (const knob of KNOBS) {
    knobState[knob] = values[knob] ?? 0;
    const input = $(`#k-${knob}`), out = $(`#o-${knob}`);
    input.value = knobState[knob];
    out.textContent = (knobState[knob] >= 0 ? "+" : "") + knobState[knob].toFixed(2);
    out.classList.toggle("hot", Math.abs(knobState[knob]) > 0.005);
  }
  refreshConstellation();
}

/* Panels: one open at a time; identity opens its two rails together. */
const panels = { identity: ["#panel-identity", "#panel-personas"],
                 studio: ["#panel-studio"], live: ["#panel-live"] };
let open = null;
function show(name) {
  open = open === name ? null : name;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("open"));
  document.querySelectorAll("nav button").forEach(b =>
    b.classList.toggle("on", b.dataset.panel === open));
  if (open) for (const sel of panels[open]) $(sel).classList.add("open");
}
document.querySelectorAll("nav button").forEach(b =>
  b.addEventListener("click", () => show(b.dataset.panel)));
addEventListener("keydown", (e) => { if (e.key === "Escape") show(open); });

/* Identities */
async function loadIdentities() {
  const list = await (await fetch("/api/identities")).json();
  const chips = $("#chips");
  chips.innerHTML = "";
  for (const it of list) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = it.name ?? "· main identity";
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach(c => c.classList.remove("on"));
      chip.classList.add("on");
      $("#persona-name").value = it.name ?? "";
      setKnobs(it.knobs);
      log(`loaded ${it.name ?? "main identity"}`);
    });
    chips.appendChild(chip);
  }
  if (!list.length) chips.innerHTML =
    `<p style="font-family:var(--mono);font-size:.72rem;color:var(--muted)">
     none yet — shape the knobs and save</p>`;
}

$("#btn-zero").addEventListener("click", () => setKnobs({}));
$("#btn-save").addEventListener("click", async () => {
  const name = $("#persona-name").value.trim() || null;
  const res = await (await fetch("/api/identities", {
    method: "POST", body: JSON.stringify({ name, knobs: knobState }),
  })).json();
  if (res.error) return log(res.error, "err");
  log(`saved -> ${res.saved}`, "ok");
  loadIdentities();
});

/* Scan */
async function scan(fromCache) {
  if (fromCache) {
    const cached = await (await fetch("/api/scan/cached")).json();
    if (!cached.points) return false;
    scanned = cached.points;
  } else {
    log("scanning — look at the camera, neutral face…");
    const res = await (await fetch("/api/scan", { method: "POST" })).json();
    if (res.error) { log(res.error, "err"); return false; }
    scanned = res.points;
  }
  $("#hint").classList.add("gone");
  setTargetsFromScan(knobState);
  if (!lines) buildLines();
  if (!fromCache) log("scan complete — the mirror is yours", "ok");
  return true;
}
$("#btn-scan").addEventListener("click", () => scan(false));

/* Studio jobs */
async function loadFiles() {
  const files = await (await fetch("/api/files")).json();
  $("#studio-video").innerHTML =
    files.map(f => `<option>${f}</option>`).join("") ||
    "<option value=''>— no recordings found —</option>";
}
const flags = {};
document.querySelectorAll("#studio-toggles button").forEach(b =>
  b.addEventListener("click", () => {
    flags[b.dataset.flag] = !flags[b.dataset.flag];
    b.classList.toggle("on", flags[b.dataset.flag]);
  }));

async function runJob(payload) {
  const res = await (await fetch("/api/jobs", {
    method: "POST", body: JSON.stringify(payload),
  })).json();
  if (res.error) return log(res.error, "err");
  const events = new EventSource(`/api/jobs/${res.id}/events`);
  events.onmessage = (e) => {
    const line = JSON.parse(e.data);
    const cls = line.includes("⚠") || line.includes("?") && line.includes("REAL")
      ? "warn" : line.startsWith("✓") ? "ok" : line.startsWith("✗") ? "err" : "";
    log(line, cls);
  };
  events.addEventListener("end", () => events.close());
}

$("#btn-ship").addEventListener("click", () => runJob({
  verb: "ship", video: $("#studio-video").value,
  identity: $("#studio-identities").value.split(",")[0].trim() || null,
  image: $("#studio-image").value.trim() || null, ...flags,
}));
$("#btn-disguise").addEventListener("click", () => runJob({
  verb: "disguise", video: $("#studio-video").value,
  identities: $("#studio-identities").value.split(",").map(s => s.trim()).filter(Boolean),
}));

/* Live */
async function liveStatus() {
  const s = await (await fetch("/api/live/status")).json();
  $("#btn-cut").disabled = !s.running;
}
async function startLive(virtual) {
  const res = await (await fetch("/api/live/start", {
    method: "POST",
    body: JSON.stringify({
      identity: $("#live-identity").value.trim() || null,
      image: $("#live-image").value.trim() || null, virtual,
    }),
  })).json();
  if (res.error) return log(res.error, "err");
  log(virtual ? "on air — virtual camera live" : "rehearsal window open", "ok");
  liveStatus();
}
$("#btn-rehearse").addEventListener("click", () => startLive(false));
$("#btn-air").addEventListener("click", () => startLive(true));
$("#btn-cut").addEventListener("click", async () => {
  await fetch("/api/live/stop", { method: "POST" });
  log("feed cut", "warn");
  liveStatus();
});

/* Boot. `?demo` = screenshot mode: springs land instantly and the
 * identity panel opens — used for docs and headless visual checks. */
(async () => {
  await Promise.all([loadIdentities(), loadFiles(), liveStatus()]);
  const hadCache = await scan(true);
  if (hadCache) $("#hint").classList.add("gone");
  if (location.search.includes("demo")) {
    show("identity");
    setKnobs({ jaw_width: 0.8, eye_spacing: -0.6, lip_fullness: 0.5 });
    for (let i = 0; i < N * 3; i++) { positions[i] = targets[i]; velocities[i] = 0; }
  }
})();

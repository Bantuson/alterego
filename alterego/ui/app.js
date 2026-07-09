/* The studio frontend: a precision instrument, not a particle demo.
 *
 * Rendering doctrine (DESIGN.md): the scanned 478 landmarks are drawn
 * with MediaPipe's REAL face-mesh topology (topology.js) — faint
 * tesselation wire + bright feature contours — over a measurement
 * room (graticule + reticle). The knob morphs use the SAME control-
 * point rules as alterego/disguise.py, ported below; points and wire
 * glow green exactly where — and as much as — the disguise will move
 * real pixels. Truthful previews, always.
 */
import * as THREE from "/three.module.min.js";
import { TESSELATION, CONTOURS } from "/topology.js";
import { CANONICAL } from "/canonical.js";

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
  return { moves, sigma: faceWidth * 0.18, faceWidth };
}

/* Gaussian splat, per landmark (the pointwise displacement_field). */
function displaceAll(pts, knobs) {
  const { moves, sigma } = controlShifts(pts, knobs);
  const twoSigmaSq = 2 * sigma * sigma;
  let maxShift = 0;
  const out = pts.map(([x, y, z]) => {
    let dx = 0, dy = 0, wsum = 0;
    for (const [[cx, cy], mx, my] of moves) {
      const w = Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / twoSigmaSq);
      dx += w * mx; dy += w * my; wsum += w;
    }
    const norm = Math.max(wsum, 1);
    maxShift = Math.max(maxShift, Math.hypot(dx / norm, dy / norm));
    return [x + dx / norm, y + dy / norm, z];
  });
  return { out, maxShift };
}

/* ---------- three.js: the room ---------- */

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const canvas = document.getElementById("stage");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(new THREE.Color("#070a15"), 4.2, 9.5);
const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 60);
camera.position.z = 5.0;

const room = new THREE.Group();   // graticule + reticle: moves less (parallax depth)
const face = new THREE.Group();   // the specimen
scene.add(room, face);

/* Graticule: a fine dot-grid wall far behind the specimen. */
function graticule() {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = "rgba(160,175,215,0.55)";
  for (let x = 16; x < 512; x += 32)
    for (let y = 16; y < 512; y += 32) g.fillRect(x, y, 1.4, 1.4);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(7, 4.5);
  const wall = new THREE.Mesh(
    new THREE.PlaneGeometry(30, 18),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.16, fog: false })
  );
  wall.position.z = -4.5;
  return wall;
}
room.add(graticule());

/* Reticle: measurement rings + tick marks around the specimen. */
function reticle() {
  const group = new THREE.Group();
  const mat = (opacity) => new THREE.LineBasicMaterial({
    color: 0x3d4a75, transparent: true, opacity, fog: false });
  for (const [radius, opacity] of [[1.55, 0.55], [1.9, 0.3]]) {
    const pts = [];
    for (let i = 0; i <= 128; i++) {
      const a = (i / 128) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0));
    }
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat(opacity)));
  }
  const ticks = [];
  for (let i = 0; i < 72; i++) {
    const a = (i / 72) * Math.PI * 2;
    const r1 = 1.9, r2 = i % 6 === 0 ? 2.02 : 1.96;
    ticks.push(new THREE.Vector3(Math.cos(a) * r1, Math.sin(a) * r1, 0),
               new THREE.Vector3(Math.cos(a) * r2, Math.sin(a) * r2, 0));
  }
  group.add(new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(ticks), mat(0.45)));
  group.position.z = -0.6;
  return group;
}
const ret = reticle();
room.add(ret);

/* ---------- the specimen: real topology, two-layer glow ---------- */

const N = 478;
const positions = new Float32Array(N * 3);
const colors = new Float32Array(N * 3);
const velocities = new Float32Array(N * 3);
const targets = new Float32Array(N * 3);

function dotTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.35, "rgba(255,255,255,0.55)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
const sprite = dotTexture();

/* Layer 1: crisp cores. Layer 2: wide soft halos = cheap bloom. */
const cores = new THREE.Points(geometry, new THREE.PointsMaterial({
  size: 0.030, map: sprite, vertexColors: true, transparent: true,
  opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending,
}));
const halos = new THREE.Points(geometry, new THREE.PointsMaterial({
  size: 0.13, map: sprite, vertexColors: true, transparent: true,
  opacity: 0.16, depthWrite: false, blending: THREE.AdditiveBlending,
}));
face.add(halos, cores);

/* The wire that makes it a FACE: faint tesselation, bright contours. */
const tessGeo = new THREE.BufferGeometry();
tessGeo.setAttribute("position", geometry.attributes.position);
tessGeo.setIndex(new THREE.BufferAttribute(TESSELATION, 1));
face.add(new THREE.LineSegments(tessGeo, new THREE.LineBasicMaterial({
  color: 0x46557f, transparent: true, opacity: 0.14,
  depthWrite: false, blending: THREE.AdditiveBlending,
})));

const contourGeo = new THREE.BufferGeometry();
contourGeo.setAttribute("position", geometry.attributes.position);
contourGeo.setAttribute("color", geometry.attributes.color);
contourGeo.setIndex(new THREE.BufferAttribute(CONTOURS, 1));
face.add(new THREE.LineSegments(contourGeo, new THREE.LineBasicMaterial({
  vertexColors: true, transparent: true, opacity: 0.85,
  depthWrite: false, blending: THREE.AdditiveBlending,
})));

const BASE = new THREE.Color(0.52, 0.60, 0.86);
const HOT = new THREE.Color(0.25, 0.95, 0.06);

/* Before any real scan the specimen is MediaPipe's CANONICAL face —
 * the neutral reference head, honestly labeled as such. Scanning
 * replaces it with you. Either way the knobs morph what you see. */
let scanned = null;
const specimen = () => scanned ?? CANONICAL;
for (let i = 0; i < N; i++) {
  positions[i * 3] = (Math.random() - 0.5) * 10;
  positions[i * 3 + 1] = (Math.random() - 0.5) * 10;
  positions[i * 3 + 2] = (Math.random() - 0.5) * 6;
  BASE.toArray(colors, i * 3);
}

function normalizeScan(pts) {
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(...ys) - Math.min(...ys);
  const s = 2.5 / span;
  return pts.map(([x, y, z]) => [(x - cx) * s, -(y - cy) * s, -z * s]);
}

let maxShiftPx = 0;
function setTargetsFromScan(knobs) {
  const source = specimen();
  const { out: displaced, maxShift } = displaceAll(source, knobs);
  maxShiftPx = maxShift;
  const shaped = normalizeScan(displaced);
  const rest = normalizeScan(source);
  for (let i = 0; i < N; i++) {
    targets[i * 3] = shaped[i][0];
    targets[i * 3 + 1] = shaped[i][1];
    targets[i * 3 + 2] = shaped[i][2];
    /* Truthful change map: green in proportion to real movement. */
    const d = Math.hypot(shaped[i][0] - rest[i][0], shaped[i][1] - rest[i][1]);
    BASE.clone().lerp(HOT, Math.min(d * 22, 1)).toArray(colors, i * 3);
  }
  geometry.attributes.color.needsUpdate = true;
  updateReadouts();
}

/* ---------- animation ---------- */

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
  geometry.attributes.position.needsUpdate = true;
  if (!reduceMotion) {
    face.rotation.y = Math.sin(t * 0.1) * 0.22 + mouseX * 0.16;
    face.rotation.x = mouseY * 0.09;
    room.rotation.y = mouseX * 0.03;   // parallax: the room barely moves
    room.rotation.x = mouseY * 0.015;
    ret.rotation.z = t * 0.02;         // the instrument is running
  }
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

function updateReadouts() {
  $("#ro-signal").textContent = scanned ? "LIVE SCAN" : "CANONICAL";
  $("#ro-signal").classList.toggle("on", !!scanned);
  $("#ro-shift").textContent = `${maxShiftPx.toFixed(1)}px`;
}

function refreshConstellation() {
  setTargetsFromScan(knobState);
}

/* The mixing desk: custom bipolar faders (keyboard + pointer). */
const fadersEl = $("#faders");
const faderEls = {};
for (const knob of KNOBS) {
  const row = document.createElement("div");
  row.className = "knob";
  row.innerHTML = `
    <div class="knob-top">
      <span class="knob-label">${knob.replace("_", " ")}</span>
      <span class="knob-value">+0.00</span>
    </div>
    <div class="meter" role="slider" tabindex="0" aria-label="${knob.replace("_", " ")}"
         aria-valuemin="-1" aria-valuemax="1" aria-valuenow="0">
      <div class="meter-fill"></div><div class="meter-notch"></div><div class="meter-thumb"></div>
    </div>`;
  fadersEl.appendChild(row);
  const meter = row.querySelector(".meter");
  const fill = row.querySelector(".meter-fill");
  const thumb = row.querySelector(".meter-thumb");
  const value = row.querySelector(".knob-value");
  faderEls[knob] = { meter, fill, thumb, value };

  const render = () => {
    const v = knobState[knob];
    value.textContent = (v >= 0 ? "+" : "") + v.toFixed(2);
    value.classList.toggle("hot", Math.abs(v) > 0.005);
    meter.setAttribute("aria-valuenow", v.toFixed(2));
    const pct = (v + 1) / 2 * 100;
    thumb.style.left = `${pct}%`;
    /* Bipolar fill: grows from the center notch toward the thumb. */
    fill.style.left = `${Math.min(50, pct)}%`;
    fill.style.width = `${Math.abs(pct - 50)}%`;
    fill.classList.toggle("hot", Math.abs(v) > 0.005);
  };
  const set = (v) => {
    knobState[knob] = Math.max(-1, Math.min(1, v));
    render();
    refreshConstellation();
  };
  const fromPointer = (e) => {
    const rect = meter.getBoundingClientRect();
    set(((e.clientX - rect.left) / rect.width) * 2 - 1);
  };
  meter.addEventListener("pointerdown", (e) => {
    meter.setPointerCapture(e.pointerId);
    fromPointer(e);
  });
  meter.addEventListener("pointermove", (e) => {
    if (e.buttons) fromPointer(e);
  });
  meter.addEventListener("dblclick", () => set(0));
  meter.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") set(knobState[knob] + 0.05);
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") set(knobState[knob] - 0.05);
    if (e.key === "0") set(0);
  });
  row._render = render;
}

function setKnobs(values) {
  for (const knob of KNOBS) {
    knobState[knob] = values[knob] ?? 0;
  }
  document.querySelectorAll(".knob").forEach(r => r._render());
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
  $("#ro-personas").textContent = String(list.length);
  const chips = $("#chips");
  chips.innerHTML = "";
  for (const it of list) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = it.name ?? "main identity";
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
    `<p class="empty">none yet — shape the knobs and save</p>`;
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
    const cls = line.includes("REAL") ? "warn"
      : line.startsWith("✓") ? "ok" : line.startsWith("✗") ? "err" : "";
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
  const haveScan = await scan(true);
  if (!haveScan) setTargetsFromScan(knobState); // the canonical specimen
  updateReadouts();
  if (location.search.includes("demo")) {
    show("identity");
    setKnobs({ jaw_width: 0.8, eye_spacing: -0.6, lip_fullness: 0.5 });
    for (let i = 0; i < N * 3; i++) { positions[i] = targets[i]; velocities[i] = 0; }
  }
})();

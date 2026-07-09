/* The studio frontend: one journey — set up an identity, work takes
 * through the pipeline, go live locked. The MESH view is the scanned
 * landmark specimen; the MIRROR view is the real camera with the real
 * disguise (MJPEG from the same fail-closed pipeline that feeds the
 * virtual camera). Both obey the same knob math as disguise.py.
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

/* Mirror of control_shifts(): same landmarks, same axes, same magic
 * numbers. If disguise.py changes, change this too. */
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

const room = new THREE.Group();   // graticule wall: parallax backdrop
const face = new THREE.Group();   // the specimen
scene.add(room, face);

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

/* Reticle: rings + ticks, scene-level so it tracks the specimen
 * exactly (a parallax parent would drift it off-center). */
function reticle() {
  const group = new THREE.Group();
  const mat = (opacity) => new THREE.LineBasicMaterial({
    color: 0x3d4a75, transparent: true, opacity, fog: false });
  for (const [radius, opacity] of [[1.15, 0.55], [1.32, 0.3]]) {
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
    const r1 = 1.32, r2 = i % 6 === 0 ? 1.40 : 1.36;
    ticks.push(new THREE.Vector3(Math.cos(a) * r1, Math.sin(a) * r1, 0),
               new THREE.Vector3(Math.cos(a) * r2, Math.sin(a) * r2, 0));
  }
  group.add(new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(ticks), mat(0.45)));
  group.position.z = -0.6;
  return group;
}
const ret = reticle();
scene.add(ret);

/* ---------- the specimen ---------- */

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

const cores = new THREE.Points(geometry, new THREE.PointsMaterial({
  size: 0.030, map: sprite, vertexColors: true, transparent: true,
  opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending,
}));
const halos = new THREE.Points(geometry, new THREE.PointsMaterial({
  size: 0.13, map: sprite, vertexColors: true, transparent: true,
  opacity: 0.16, depthWrite: false, blending: THREE.AdditiveBlending,
}));
face.add(halos, cores);

/* The wire fades in only once the points have settled — mid-flight
 * dots with lines attached read as chaos, not assembly. */
const tessMat = new THREE.LineBasicMaterial({
  color: 0x46557f, transparent: true, opacity: 0,
  depthWrite: false, blending: THREE.AdditiveBlending,
});
const contourMat = new THREE.LineBasicMaterial({
  vertexColors: true, transparent: true, opacity: 0,
  depthWrite: false, blending: THREE.AdditiveBlending,
});
const WIRE_OPACITY = { tess: 0.14, contour: 0.85 };

const tessGeo = new THREE.BufferGeometry();
tessGeo.setAttribute("position", geometry.attributes.position);
tessGeo.setIndex(new THREE.BufferAttribute(TESSELATION, 1));
face.add(new THREE.LineSegments(tessGeo, tessMat));

const contourGeo = new THREE.BufferGeometry();
contourGeo.setAttribute("position", geometry.attributes.position);
contourGeo.setAttribute("color", geometry.attributes.color);
contourGeo.setIndex(new THREE.BufferAttribute(CONTOURS, 1));
face.add(new THREE.LineSegments(contourGeo, contourMat));

const BASE = new THREE.Color(0.52, 0.60, 0.86);
const HOT = new THREE.Color(0.25, 0.95, 0.06);

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
  const s = 2.0 / span; // face height 2.0 units: inside the 1.15 ring
  return pts.map(([x, y, z]) => [(x - cx) * s, -(y - cy) * s, -z * s]);
}

let maxShiftPx = 0;
let targetsReady = false;
function setTargetsFromScan(knobs) {
  targetsReady = true;
  const source = specimen();
  const { out: displaced, maxShift } = displaceAll(source, knobs);
  maxShiftPx = maxShift;
  const shaped = normalizeScan(displaced);
  const rest = normalizeScan(source);
  for (let i = 0; i < N; i++) {
    targets[i * 3] = shaped[i][0];
    targets[i * 3 + 1] = shaped[i][1];
    targets[i * 3 + 2] = shaped[i][2];
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
let faceOffsetTarget = 0;
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
  if (targetsReady) {
    for (let i = 0; i < N * 3; i++) {
      if (reduceMotion) { positions[i] = targets[i]; continue; }
      const force = -STIFF * (positions[i] - targets[i]) - DAMP * velocities[i];
      velocities[i] += force * dt;
      positions[i] += velocities[i] * dt;
    }
    geometry.attributes.position.needsUpdate = true;
  }
  /* Wire opacity follows convergence: sample how far points sit from
   * their targets; the mesh materializes as the face assembles. */
  let drift = 0;
  for (let i = 0; i < 30; i++) {
    const j = i * 16 * 3;
    drift += Math.abs(positions[j] - targets[j]);
  }
  const settled = reduceMotion ? 1 : Math.max(0, 1 - drift / 3);
  tessMat.opacity += (WIRE_OPACITY.tess * settled - tessMat.opacity) * 0.08;
  contourMat.opacity += (WIRE_OPACITY.contour * settled - contourMat.opacity) * 0.08;

  const glide = reduceMotion ? 1 : Math.min(dt * 6, 1);
  face.position.x += (faceOffsetTarget - face.position.x) * glide;
  ret.position.x = face.position.x;
  if (!reduceMotion) {
    face.rotation.y = Math.sin(t * 0.1) * 0.22 + mouseX * 0.16;
    face.rotation.x = mouseY * 0.09;
    room.rotation.y = mouseX * 0.03;
    room.rotation.x = mouseY * 0.015;
    ret.rotation.z = t * 0.02;
  }
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();

/* ---------- shared UI state ---------- */

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
let personas = [];

function updateReadouts() {
  const onair = document.body.dataset.onair === "on";
  const signal = $("#ro-signal");
  signal.textContent = onair ? "ON AIR" : scanned ? "LIVE SCAN" : "CANONICAL";
  signal.className = onair ? "air" : scanned ? "on" : "";
  $("#ro-shift").textContent = `${maxShiftPx.toFixed(1)}px`;
  $("#ro-personas").textContent = String(personas.length);
}

/* ---------- the mirror (MJPEG preview) ---------- */

const mirror = $("#mirror");
let mirrorOn = false;
let knobPushTimer = null;

function startMirror(identity, image) {
  // Screenshot/demo mode never touches the real camera.
  if (new URLSearchParams(location.search).get("demo") !== null) return;
  const params = new URLSearchParams();
  if (identity) params.set("identity", identity);
  if (image) params.set("image", image);
  params.set("t", Date.now()); // never let the browser cache a stream
  mirror.src = `/api/preview/stream?${params}`;
  document.body.dataset.mirror = "on";
  mirrorOn = true;
  pushKnobs(); // the desk state applies immediately
}

async function stopMirror() {
  if (!mirrorOn) return;
  mirrorOn = false;
  mirror.src = "";
  delete document.body.dataset.mirror;
  await fetch("/api/preview/stop", { method: "POST" }).catch(() => {});
}

function pushKnobs() {
  if (!mirrorOn) return;
  clearTimeout(knobPushTimer);
  knobPushTimer = setTimeout(() => {
    fetch("/api/preview/knobs", {
      method: "POST", body: JSON.stringify({ knobs: knobState }),
    }).catch(() => {});
  }, 120);
}

$("#seg-mesh").addEventListener("click", () => {
  $("#seg-mesh").classList.add("on");
  $("#seg-mirror").classList.remove("on");
  stopMirror();
});
$("#seg-mirror").addEventListener("click", () => {
  $("#seg-mirror").classList.add("on");
  $("#seg-mesh").classList.remove("on");
  startMirror($("#persona-name").value.trim() || null, null);
  log("mirror on — this is the pipeline's real output");
});

/* ---------- the mixing desk ---------- */

const fadersEl = $("#faders");
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

  const render = () => {
    const v = knobState[knob];
    value.textContent = (v >= 0 ? "+" : "") + v.toFixed(2);
    value.classList.toggle("hot", Math.abs(v) > 0.005);
    meter.setAttribute("aria-valuenow", v.toFixed(2));
    const pct = (v + 1) / 2 * 100;
    thumb.style.left = `${pct}%`;
    fill.style.left = `${Math.min(50, pct)}%`;
    fill.style.width = `${Math.abs(pct - 50)}%`;
    fill.classList.toggle("hot", Math.abs(v) > 0.005);
  };
  const set = (v) => {
    knobState[knob] = Math.max(-1, Math.min(1, v));
    render();
    setTargetsFromScan(knobState);
    pushKnobs();
    setupProgress(2);
  };
  const fromPointer = (e) => {
    const rect = meter.getBoundingClientRect();
    set(((e.clientX - rect.left) / rect.width) * 2 - 1);
  };
  meter.addEventListener("pointerdown", (e) => { meter.setPointerCapture(e.pointerId); fromPointer(e); });
  meter.addEventListener("pointermove", (e) => { if (e.buttons) fromPointer(e); });
  meter.addEventListener("dblclick", () => set(0));
  meter.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") set(knobState[knob] + 0.05);
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") set(knobState[knob] - 0.05);
    if (e.key === "0") set(0);
  });
  row._render = render;
}

function setKnobs(values) {
  for (const knob of KNOBS) knobState[knob] = values[knob] ?? 0;
  document.querySelectorAll(".knob").forEach(r => r._render());
  setTargetsFromScan(knobState);
  pushKnobs();
}

/* ---------- panels & modes ---------- */

let open = null;
function show(name) {
  open = open === name ? null : name;
  document.querySelectorAll(".panel").forEach(p =>
    p.classList.toggle("open", p.id === `panel-${open}`));
  document.querySelectorAll("nav button").forEach(b =>
    b.classList.toggle("on", b.dataset.panel === open));
  document.body.classList.toggle("panel-open", !!open);
  faceOffsetTarget = open ? -0.65 : 0;
  if (open === "live") {
    // Live IS the mirror: preview starts the moment you arrive.
    startMirror($("#live-identity").value.trim() || null,
                $("#live-image").value.trim() || null);
  } else if (open !== "identity" || !$("#seg-mirror").classList.contains("on")) {
    stopMirror();
  }
}
document.querySelectorAll("nav button").forEach(b =>
  b.addEventListener("click", () => show(b.dataset.panel)));
addEventListener("keydown", (e) => { if (e.key === "Escape" && open) show(open); });

/* ---------- setup (first run) ---------- */

let setupStage = 0; // 0 inactive · 1 scan · 2 shape · 3 save
function setupProgress(stage) {
  if (!setupStage || stage < setupStage) return;
  setupStage = stage;
  for (const n of [1, 2, 3]) {
    const el = $(`#setup-${n}`);
    el.classList.toggle("now", n === stage);
    el.classList.toggle("done", n < stage);
  }
}
function enterSetup() {
  document.body.dataset.setup = "on";
  setupStage = 1;
  setupProgress(1);
  show("identity");
  log("welcome — save your first identity to unlock the studio");
}
function completeSetup() {
  if (!setupStage) return;
  setupStage = 0;
  delete document.body.dataset.setup;
  log("studio unlocked — STUDIO processes takes, LIVE goes on air", "ok");
}

/* ---------- identities ---------- */

async function loadIdentities() {
  personas = await (await fetch("/api/identities")).json();
  const chips = $("#chips");
  chips.innerHTML = "";
  for (const it of personas) {
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
  if (!personas.length) chips.innerHTML = `<p class="empty">no personas yet</p>`;
  updateReadouts();
}

$("#btn-zero").addEventListener("click", () => setKnobs({}));
$("#btn-save").addEventListener("click", async () => {
  const name = $("#persona-name").value.trim() || null;
  const res = await (await fetch("/api/identities", {
    method: "POST", body: JSON.stringify({ name, knobs: knobState }),
  })).json();
  if (res.error) return log(res.error, "err");
  log(`saved -> ${res.saved}`, "ok");
  await loadIdentities();
  completeSetup();
});

async function scan(fromCache) {
  if (fromCache) {
    const cached = await (await fetch("/api/scan/cached")).json();
    if (!cached.points) return false;
    scanned = cached.points;
  } else {
    await stopMirror(); // the scan needs the camera
    log("scanning — look at the camera, neutral face…");
    const res = await (await fetch("/api/scan", { method: "POST" })).json();
    if (res.error) { log(res.error, "err"); return false; }
    scanned = res.points;
    setupProgress(2);
  }
  $("#hint").classList.add("gone");
  setTargetsFromScan(knobState);
  if (!fromCache) log("scan complete — the mirror is yours", "ok");
  return true;
}
$("#btn-scan").addEventListener("click", () => scan(false));

/* Save-as field reaching step 3 */
$("#persona-name").addEventListener("input", () => setupProgress(3));

/* ---------- studio workbench ---------- */

const STAGES = [
  { key: "disguise", flag: null },
  { key: "background", flag: "no_background" },
  { key: "enhance", flag: null },
  { key: "cut", flag: "no_fillers" },   // toggling cut here = skip fillers
  { key: "voice", flag: "no_voice" },
];
const stageState = Object.fromEntries(STAGES.map(s => [s.key, true]));
let selectedFile = null;

const pipeEl = $("#pipe");
STAGES.forEach((stage, i) => {
  if (i) {
    const arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = "→";
    pipeEl.appendChild(arrow);
  }
  const b = document.createElement("button");
  b.className = "stage";
  b.textContent = stage.key;
  b.dataset.stage = stage.key;
  b.addEventListener("click", () => {
    if (!stage.flag && stage.key !== "cut") return; // disguise/enhance always run in ship
    stageState[stage.key] = !stageState[stage.key];
    b.classList.toggle("off", !stageState[stage.key]);
  });
  pipeEl.appendChild(b);
});

async function loadFiles() {
  const files = await (await fetch("/api/files")).json();
  const list = $("#file-list");
  list.innerHTML = "";
  for (const f of files) {
    const b = document.createElement("button");
    b.className = "file";
    const age = Math.max(0, (Date.now() / 1000 - f.mtime) / 3600);
    const when = age < 1 ? "just now" : age < 24 ? `${age.toFixed(0)}h ago`
      : `${(age / 24).toFixed(0)}d ago`;
    b.innerHTML = `<span class="name">${f.path}</span>
                   <span class="meta">${f.mb} MB · ${when}</span>`;
    b.addEventListener("click", () => {
      document.querySelectorAll(".file").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      selectedFile = f.path;
    });
    list.appendChild(b);
  }
  if (!files.length) list.innerHTML =
    `<p class="empty">no footage found — record with the CLI or drop
     files into recordings/</p>`;
}

function markStages(line) {
  /* The pipeline prints "[2/5] background" — light the chips up. */
  const match = line.match(/^\[(\d+)\/\d+\] (\w+)/);
  if (match) {
    document.querySelectorAll(".stage").forEach(el => {
      if (el.dataset.stage === match[2]) el.classList.add("running");
      else if (el.classList.contains("running")) {
        el.classList.remove("running");
        el.classList.add("done");
      }
    });
  }
  if (line.includes("shipped:")) {
    document.querySelectorAll(".stage.running").forEach(el => {
      el.classList.remove("running");
      el.classList.add("done");
    });
  }
}

async function runJob(payload) {
  const res = await (await fetch("/api/jobs", {
    method: "POST", body: JSON.stringify(payload),
  })).json();
  if (res.error) return log(res.error, "err");
  document.querySelectorAll(".stage").forEach(el =>
    el.classList.remove("running", "done"));
  const events = new EventSource(`/api/jobs/${res.id}/events`);
  events.onmessage = (e) => {
    const line = JSON.parse(e.data);
    markStages(line);
    const cls = line.includes("REAL") ? "warn"
      : line.startsWith("✓") ? "ok" : line.startsWith("✗") ? "err" : "";
    log(line, cls);
    if (line.startsWith("✓")) loadFiles(); // new output appears in the list
  };
  events.addEventListener("end", () => events.close());
}

$("#btn-ship").addEventListener("click", () => {
  if (!selectedFile) return log("pick footage first", "warn");
  runJob({
    verb: "ship", video: selectedFile,
    identity: $("#studio-identities").value.split(",")[0].trim() || null,
    image: $("#studio-image").value.trim() || null,
    no_background: !stageState.background,
    no_fillers: !stageState.cut,
    no_voice: !stageState.voice,
  });
});

/* ---------- live: preview → lock → connect ---------- */

async function liveStatus() {
  const s = await (await fetch("/api/live/status")).json();
  document.body.dataset.onair = s.running ? "on" : "off";
  if (!s.running) delete document.body.dataset.onair;
  $("#btn-cut").disabled = !s.running;
  $("#btn-air").disabled = s.running;
  updateReadouts();
}

async function startLive(virtual) {
  await stopMirror(); // hand the camera to the live process
  const res = await (await fetch("/api/live/start", {
    method: "POST",
    body: JSON.stringify({
      identity: $("#live-identity").value.trim() || null,
      image: $("#live-image").value.trim() || null, virtual,
    }),
  })).json();
  if (res.error) return log(res.error, "err");
  log(virtual ? "identity locked — on air" : "rehearsal window open", "ok");
  liveStatus();
}
$("#btn-rehearse").addEventListener("click", () => startLive(false));
$("#btn-air").addEventListener("click", () => startLive(true));
$("#btn-cut").addEventListener("click", async () => {
  await fetch("/api/live/stop", { method: "POST" });
  log("feed cut", "warn");
  await liveStatus();
  if (open === "live") startMirror($("#live-identity").value.trim() || null,
                                   $("#live-image").value.trim() || null);
});

/* ---------- boot ---------- */

setTargetsFromScan(knobState); // canonical specimen exists at frame one
const demoMode = new URLSearchParams(location.search).get("demo");
if (demoMode !== null || location.search.includes("hold")) {
  const hold = new Image();
  // hold mode waits longer: it also covers the server's first-import lag
  hold.src = demoMode !== null ? "/slow" : "/slow?ms=7000";
}
if (demoMode !== null) {
  show(["studio", "live"].includes(demoMode) ? demoMode : "identity");
  setKnobs({ jaw_width: 0.8, eye_spacing: -0.6, lip_fullness: 0.5 });
  for (let i = 0; i < N * 3; i++) { positions[i] = targets[i]; velocities[i] = 0; }
}

(async () => {
  await Promise.all([loadIdentities(), loadFiles(), liveStatus()]);
  await scan(true);
  updateReadouts();
  if (!personas.length && !location.search.includes("demo")) enterSetup();
})();

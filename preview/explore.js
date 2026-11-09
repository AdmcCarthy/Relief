// Zoomable region viewer: picks a tile-pyramid level from the zoom, fetches only the tiles in view, stitches them
// into one 16-bit elevation texture and draws it with the same Detuned style as the gallery (stepped relief by
// climate zone, linear bathymetry, no contours, no illumination).
import { createRenderer } from "./relief.js";
import { detunedStyle, regionBars } from "./palette.js";
import { equalEarthRing, ringPath } from "./geo.js";

const ORDER = ["north_sea", "norwegian_sea", "barents_sea", "ne_europe", "atlantic", "world", "vestland"];
const getJSON = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dpr = Math.min(2, window.devicePixelRatio || 1);
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- theme
const root = document.documentElement;
let theme = (() => { try { return localStorage.getItem("relief:theme"); } catch { return null; } })()
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
function setTheme(t) {
  theme = t; root.dataset.theme = t;
  $("theme").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === t)));
  try { localStorage.setItem("relief:theme", t); } catch { /* private mode */ }
}
$("theme").addEventListener("click", (e) => { if (e.target.dataset.v) { setTheme(e.target.dataset.v); legend(); render(); } });
setTheme(theme);

const R = createRenderer();
if (!R) $("nogl").style.display = "block";

// ---------------------------------------------------------------- regions with tiles
const regDoc = await getJSON("regions/regions.json");
const regions = [];
for (const id of ORDER) {
  const reg = regDoc && regDoc.regions.find((r) => r.id === id);
  const tiles = reg && (await getJSON(`data/${id}/tiles/tiles.json`));
  if (tiles) regions.push({ reg, tiles });
}
const params = new URLSearchParams(location.search);
let cur = null;  // { reg, tiles, meta, zones, ext: [x0, y0, x1, y1] }
let shading = params.get("shade") !== "off";  // ocean regions only: soft shading of the sea floor
const override = params.get("exag") ? { exag: +params.get("exag"), k: +(params.get("k") ?? 0.8) } : null;
const view = { cx: 0, cy: 0, mpp: 1 };  // centre in region metres; metres per CSS pixel
const canvas = $("map"), ctx = canvas.getContext("2d");
const buf = document.createElement("canvas"), stitch = document.createElement("canvas");
const sctx = stitch.getContext("2d");

$("regions").innerHTML = regions.map(({ reg }) => `<button data-v="${reg.id}">${esc(reg.name.split(" (")[0])}</button>`).join("");
$("regions").addEventListener("click", (e) => { if (e.target.dataset.v) openRegion(e.target.dataset.v); });

// ---------------------------------------------------------------- tiles
const cache = new Map();  // key -> Promise<ImageBitmap>, least recently used first
function loadTile(id, z, x, y) {
  const key = `${id}/${z}/${x}_${y}`;
  if (cache.has(key)) { const p = cache.get(key); cache.delete(key); cache.set(key, p); return p; }
  const p = fetch(`data/${id}/tiles/${z}/${x}_${y}.webp`).then((r) => { if (!r.ok) throw new Error(key); return r.blob(); })
    .then((b) => createImageBitmap(b, { colorSpaceConversion: "none", premultiplyAlpha: "none" }));
  cache.set(key, p);
  if (cache.size > 120) { const old = cache.keys().next().value; cache.get(old).then((bm) => bm.close()).catch(() => {}); cache.delete(old); }
  return p;
}

// ---------------------------------------------------------------- view
const size = () => ({ w: canvas.clientWidth || 800, h: canvas.clientHeight || 600 });
function fit() {
  const [x0, y0, x1, y1] = cur.ext, { w, h } = size();
  view.cx = (x0 + x1) / 2; view.cy = (y0 + y1) / 2;
  view.mpp = Math.max((x1 - x0) / w, (y1 - y0) / h) * 1.02;
}
const fitMpp = () => { const [x0, y0, x1, y1] = cur.ext, { w, h } = size(); return Math.max((x1 - x0) / w, (y1 - y0) / h) * 1.02; };
function clampView() {
  const [x0, y0, x1, y1] = cur.ext, finest = cur.tiles.levels.at(-1).cell;
  view.mpp = Math.min(fitMpp() * 1.5, Math.max((finest / 4) * dpr, view.mpp));
  view.cx = Math.min(x1, Math.max(x0, view.cx)); view.cy = Math.min(y1, Math.max(y0, view.cy));
}
function zoomAt(factor, px, py) {
  const { w, h } = size(), X = view.cx + (px - w / 2) * view.mpp, Y = view.cy - (py - h / 2) * view.mpp;
  view.mpp /= factor; clampView();
  view.cx = X - (px - w / 2) * view.mpp; view.cy = Y + (py - h / 2) * view.mpp; clampView();
  render(); saveUrl();
}
function saveUrl() {
  const u = new URL(location.href);
  u.searchParams.set("area", cur.reg.id);
  u.searchParams.set("x", Math.round(view.cx)); u.searchParams.set("y", Math.round(view.cy)); u.searchParams.set("m", view.mpp.toFixed(1));
  history.replaceState(null, "", u);
}

// ---------------------------------------------------------------- render
let seq = 0;
async function render() {
  if (!cur || !R) return;
  const my = ++seq, { w, h } = size(), W = Math.round(w * dpr), H = Math.round(h * dpr);
  if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
  const { tiles } = cur, T = tiles.tile, Z = tiles.levels.length - 1, cellF = tiles.levels[Z].cell, [x0, y0, x1, y1] = cur.ext;
  const mppDev = view.mpp / dpr;
  const z = Math.min(Z, Math.max(0, Math.ceil(Z - Math.log2(mppDev / cellF)))), lv = tiles.levels[z], cz = lv.cell;
  // the view in metres, and the part of it that lies inside the region
  const vx0 = view.cx - (w * view.mpp) / 2, vx1 = view.cx + (w * view.mpp) / 2, vy0 = view.cy - (h * view.mpp) / 2, vy1 = view.cy + (h * view.mpp) / 2;
  const ix0 = Math.max(vx0, x0), ix1 = Math.min(vx1, x1), iy0 = Math.max(vy0, y0), iy1 = Math.min(vy1, y1);
  const bg = getComputedStyle(root).getPropertyValue("--raised").trim() || "#ecf1f5";
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  if (ix0 >= ix1 || iy0 >= iy1) { info(z, Z, cz, 0); return; }
  // stitched pixel range at level z (north-west origin), one pixel of margin
  const px0 = Math.max(0, Math.floor((ix0 - x0) / cz) - 1), px1 = Math.min(lv.size[0], Math.ceil((ix1 - x0) / cz) + 1);
  const py0 = Math.max(0, Math.floor((y1 - iy1) / cz) - 1), py1 = Math.min(lv.size[1], Math.ceil((y1 - iy0) / cz) + 1);
  const sw = px1 - px0, sh = py1 - py0;
  if (sw < 1 || sh < 1 || sw * sh > 6000 * 6000) return;
  const need = [];
  for (let ty = Math.floor(py0 / T); ty <= Math.floor((py1 - 1) / T); ty++) for (let tx = Math.floor(px0 / T); tx <= Math.floor((px1 - 1) / T); tx++) need.push([tx, ty]);
  info(z, Z, cz, need.length, true);
  const maps = await Promise.all(need.map(([tx, ty]) => loadTile(cur.reg.id, z, tx, ty).catch(() => null)));
  if (my !== seq) return;  // a newer view superseded this one
  stitch.width = sw; stitch.height = sh;
  sctx.imageSmoothingEnabled = false;
  need.forEach(([tx, ty], i) => { if (maps[i]) sctx.drawImage(maps[i], tx * T - px0, ty * T - py0); });
  // stitched extent in metres, then the inner rectangle as texture uv
  const sx0 = x0 + px0 * cz, sx1 = x0 + px1 * cz, sy1 = y1 - py0 * cz, sy0 = y1 - py1 * cz;
  const zw = cur.meta.size[0] * cur.meta.cell, zh = cur.meta.size[1] * cur.meta.cell;
  const src = {
    key: cur.reg.id, elev: stitch, ice: null, zones: cur.zones, dynamic: true, size: [sw, sh], cell: cz, base: tiles.encoding.base, step: tiles.encoding.step,
    zoneView: [(sx0 - x0) / zw, (y1 - sy1) / zh, (sx1 - x0) / zw, (y1 - sy0) / zh],
    view: [(ix0 - sx0) / (sx1 - sx0), (sy1 - iy1) / (sy1 - sy0), (ix1 - sx0) / (sx1 - sx0), (sy1 - iy0) / (sy1 - sy0)],
  };
  const bw = Math.max(1, Math.round(((ix1 - ix0) / view.mpp) * dpr)), bh = Math.max(1, Math.round(((iy1 - iy0) / view.mpp) * dpr));
  buf.width = bw; buf.height = bh;
  R.draw(buf, src, detunedStyle(theme, cur.reg.bathymetry, shading ? view.mpp / dpr : 0, override));
  const ox = ((ix0 - vx0) / view.mpp) * dpr, oy = ((vy1 - iy1) / view.mpp) * dpr;
  ctx.save();
  if (cur.reg.id === "world") {
    const toPx = (x, y) => [((x - vx0) / view.mpp) * dpr, ((vy1 - y) / view.mpp) * dpr];
    const outline = ringPath(equalEarthRing(), toPx);
    ctx.clip(outline); ctx.drawImage(buf, ox, oy); ctx.restore(); ctx.save();
    ctx.strokeStyle = theme === "dark" ? "#2c3a45" : "#ccd6dd"; ctx.lineWidth = dpr; ctx.stroke(outline);
  } else {
    ctx.drawImage(buf, ox, oy);
  }
  ctx.restore();
  scaleBar(W, H);
  info(z, Z, cz, need.length);
}

function niceLength(m) {
  const p = 10 ** Math.floor(Math.log10(m)), f = m / p;
  return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * p;
}
function scaleBar(W, H) {
  const len = niceLength(view.mpp * 110), px = (len / view.mpp) * dpr, label = len >= 1000 ? `${len / 1000} km` : `${len} m`;
  const x = 16 * dpr, y = H - 18 * dpr, dark = theme === "dark";
  ctx.save();
  ctx.fillStyle = dark ? "rgba(14,24,32,.72)" : "rgba(253,254,255,.8)";
  ctx.fillRect(x - 8 * dpr, y - 20 * dpr, px + 16 * dpr, 30 * dpr);
  ctx.fillStyle = dark ? "#f5fdff" : "#2d3439"; ctx.fillRect(x, y, px, 2 * dpr);
  ctx.font = `${12 * dpr}px "Instrument Sans", system-ui, sans-serif`; ctx.fillText(label, x, y - 6 * dpr);
  ctx.restore();
}
function info(z, Z, cz, n, loading = false) {
  $("info").textContent = `${loading ? "Loading… " : ""}Level ${z} of ${Z} · tiles at ${cz.toLocaleString("en-GB")} m · ${n} in view · 1 px = ${Math.round(view.mpp).toLocaleString("en-GB")} m`;
}
function legend() {
  if (!cur) return;
  $("legend").innerHTML = regionBars(detunedStyle(theme, cur.reg.bathymetry), cur.meta.zones.share_of_land);
}

// ---------------------------------------------------------------- open a region
async function openRegion(id) {
  const entry = regions.find((r) => r.reg.id === id) || regions[0];
  if (!entry) { $("info").textContent = "No tile pyramids are built yet. Run scripts/build_tiles.py <region>."; return; }
  const meta = await getJSON(`data/${entry.reg.id}/demo/meta.json`);
  const zonesImg = await new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = `data/${entry.reg.id}/demo/zones.png`; });
  cur = { ...entry, meta, zones: zonesImg, ext: entry.tiles.extent };
  $("regions").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === entry.reg.id)));
  $("shadeseg").hidden = entry.reg.bathymetry !== "ocean";  // shading is an ocean-basin option only
  $("shadeon").setAttribute("aria-pressed", String(shading));
  $("rname").textContent = entry.reg.name;
  $("rdesc").textContent = entry.reg.description;
  const finest = entry.tiles.levels.at(-1).cell;
  $("credits").innerHTML = "Tiles built " + esc(entry.tiles.built) + " from " + (entry.tiles.source === "hires" ? "the high-resolution build" : "first-pass data") +
    ` (finest ${finest.toLocaleString("en-GB")} m). Sources: ` + [...new Set(["Beck et al. (2023) Köppen-Geiger 1991–2020, CC BY 4.0", ...(entry.tiles.attribution || [])])].map(esc).join("; ") + ". Not for navigation.";
  legend();
  const m = parseFloat(params.get("m")), x = parseFloat(params.get("x")), y = parseFloat(params.get("y"));
  if (params.get("area") === entry.reg.id && m > 0 && Number.isFinite(x) && Number.isFinite(y)) { view.cx = x; view.cy = y; view.mpp = m; clampView(); }
  else fit();
  params.delete("x"); params.delete("y"); params.delete("m");
  render(); saveUrl();
}

// ---------------------------------------------------------------- interaction
const pointers = new Map();
let last = null;
canvas.addEventListener("pointerdown", (e) => { canvas.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]); last = null; });
canvas.addEventListener("pointermove", (e) => {
  if (!pointers.has(e.pointerId) || !cur) return;
  const prev = pointers.get(e.pointerId);
  pointers.set(e.pointerId, [e.clientX, e.clientY]);
  const pts = [...pointers.values()];
  if (pts.length === 1) {
    view.cx -= (e.clientX - prev[0]) * view.mpp; view.cy += (e.clientY - prev[1]) * view.mpp; clampView(); render();
  } else if (pts.length === 2) {
    const d = Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]), rect = canvas.getBoundingClientRect();
    if (last) zoomAt(d / last, (pts[0][0] + pts[1][0]) / 2 - rect.left, (pts[0][1] + pts[1][1]) / 2 - rect.top);
    last = d;
  }
});
const release = (e) => { pointers.delete(e.pointerId); last = null; if (cur) saveUrl(); };
canvas.addEventListener("pointerup", release); canvas.addEventListener("pointercancel", release);
canvas.addEventListener("wheel", (e) => { e.preventDefault(); const r = canvas.getBoundingClientRect(); zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top); }, { passive: false });
canvas.addEventListener("dblclick", (e) => { const r = canvas.getBoundingClientRect(); zoomAt(2, e.clientX - r.left, e.clientY - r.top); });
$("zin").addEventListener("click", () => zoomAt(2, size().w / 2, size().h / 2));
$("zout").addEventListener("click", () => zoomAt(0.5, size().w / 2, size().h / 2));
$("shadeon").addEventListener("click", () => { shading = !shading; $("shadeon").setAttribute("aria-pressed", String(shading)); render(); });
$("zfit").addEventListener("click", () => { if (cur) { fit(); render(); saveUrl(); } });
canvas.addEventListener("keydown", (e) => {
  const step = size().w * view.mpp * 0.15;
  if (e.key === "+" || e.key === "=") zoomAt(1.5, size().w / 2, size().h / 2);
  else if (e.key === "-") zoomAt(1 / 1.5, size().w / 2, size().h / 2);
  else if (e.key === "ArrowLeft") { view.cx -= step; clampView(); render(); }
  else if (e.key === "ArrowRight") { view.cx += step; clampView(); render(); }
  else if (e.key === "ArrowUp") { view.cy += step; clampView(); render(); }
  else if (e.key === "ArrowDown") { view.cy -= step; clampView(); render(); }
  else return;
  e.preventDefault();
});
let rt;
addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (cur) { clampView(); render(); } }, 150); });

if (regions.length) await openRegion(params.get("area") || regions[0].reg.id);
else $("info").textContent = "No tile pyramids are built yet. Run scripts/build_tiles.py <region>.";
window.__relief = { ready: true };

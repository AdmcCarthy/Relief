// Region examples: every region drawn in one fixed style (Detuned: stepped relief by climate zone, linear
// bathymetry, no contours, no illumination) from its 16-bit elevation WebP, plus the data plan per region.
import { createRenderer, loadImage } from "./relief.js";
import { detunedStyle, regionBars } from "./palette.js";
import { equalEarthRing, ringPath } from "./geo.js";

const ORDER = ["north_sea", "norwegian_sea", "barents_sea", "ne_europe", "atlantic", "world", "vestland"];
const getJSON = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const dpr = Math.min(2, window.devicePixelRatio || 1);

// ---------------------------------------------------------------- theme
const root = document.documentElement;
let theme = (() => { try { return localStorage.getItem("relief:theme"); } catch { return null; } })()
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const themeSeg = document.getElementById("theme");
function setTheme(t) {
  theme = t; root.dataset.theme = t;
  themeSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === t)));
  try { localStorage.setItem("relief:theme", t); } catch { /* private mode */ }
}
themeSeg.addEventListener("click", (e) => { if (e.target.dataset.v) { setTheme(e.target.dataset.v); drawAll(); } });
setTheme(theme);

const R = createRenderer();
if (!R) document.getElementById("nogl").style.display = "block";

// ---------------------------------------------------------------- data
const [regDoc, plan] = await Promise.all([getJSON("regions/regions.json"), getJSON("regions/sources.json")]);
const regions = regDoc ? ORDER.map((id) => regDoc.regions.find((r) => r.id === id)).filter(Boolean) : [];
const cardsEl = document.getElementById("cards");
const cards = regions.map((reg) => {
  const el = document.createElement("article");
  el.className = "card";
  el.innerHTML = `<canvas aria-label="${esc(reg.name)}"></canvas><div class="ph">Not built yet. Run <code>python scripts/render_region.py ${esc(reg.id)}</code>.</div>
    <div class="txt"><h3>${esc(reg.name)}</h3><p>${esc(reg.description)}</p>
    <div class="tags"><span class="tag">${esc(reg.crs.name)}</span><span class="tag">${reg.size_km[0].toLocaleString("en-GB")} × ${reg.size_km[1].toLocaleString("en-GB")} km</span></div>
    <div class="bars"></div><div class="data"></div><div class="links"></div></div>`;
  cardsEl.append(el);
  return { reg, el, canvas: el.querySelector("canvas"), bars: el.querySelector(".bars"), data: el.querySelector(".data"), links: el.querySelector(".links"), meta: null, src: null };
});

async function loadCard(c) {
  const base = `data/${c.reg.id}/demo/`;
  const meta = await getJSON(base + "meta.json");
  if (!meta) { c.el.classList.add("missing"); return; }
  try {
    const card = meta.card || null;  // a smaller texture for the card when the full one is wide (render_region.py); the zoom page has the detail
    const [elev, zones] = await Promise.all([loadImage(base + (card ? card.file : "elev.webp")), loadImage(base + "zones.png")]);
    c.meta = meta;
    c.drawnAt = card ? card.cell : meta.cell;
    c.src = { key: c.reg.id, elev, ice: null, zones, size: card ? card.size : meta.size, cell: c.drawnAt, base: meta.encoding.base, step: meta.encoding.step };
  } catch { c.el.classList.add("missing"); return; }
  const d = meta.data;
  if (d) {
    const names = d.sources.map((s) => `${esc(s.name)} (${s.res_m >= 1000 ? s.res_m / 1000 + " km" : s.res_m + " m"})`).join(", ");
    c.data.innerHTML = `<b>Drawn at ${c.drawnAt.toLocaleString("en-GB")} m</b> · ${d.kind === "hires" ? "high-resolution build" : "first-pass data"}<br>${names}`;
  } else {
    c.data.innerHTML = `<b>Drawn at ${c.drawnAt.toLocaleString("en-GB")} m</b> · Copernicus GLO-90, EMODnet 2024, Kartverket 50 m`;
  }
  const tiles = await getJSON(`data/${c.reg.id}/tiles/tiles.json`);
  const fine = tiles ? tiles.levels.at(-1).cell : null;
  c.fine = fine;
  c.links.innerHTML = (tiles ? `<a href="explore.html?area=${esc(c.reg.id)}">Zoom in: ${fine.toLocaleString("en-GB")} m tiles</a> · ` : "") + `<a href="vector.html?area=${esc(c.reg.id)}">Vector layers</a>`;
}

// Equal Earth is not a rectangle: clip the world to its outline.
function equalEarthOutline(bounds, W, H) {
  const [x0, y0, x1, y1] = bounds;
  return ringPath(equalEarthRing(), (x, y) => [((x - x0) / (x1 - x0)) * W, ((y1 - y) / (y1 - y0)) * H]);
}

function drawCard(c) {
  if (!c.src || !R) return;
  const st = detunedStyle(theme, c.reg.bathymetry, (c.meta.bounds[2] - c.meta.bounds[0]) / Math.round((c.canvas.clientWidth || 600) * dpr)), aspect = c.meta.size[1] / c.meta.size[0];
  const W = Math.round((c.canvas.clientWidth || 600) * dpr), H = Math.round(W * aspect);
  c.canvas.style.aspectRatio = `${c.meta.size[0]} / ${c.meta.size[1]}`;
  c.canvas.width = W; c.canvas.height = H;
  if (c.reg.id === "world") {
    const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H;
    R.draw(tmp, c.src, st);
    const ctx = c.canvas.getContext("2d"), outline = equalEarthOutline(c.meta.bounds, W, H);
    ctx.save(); ctx.clip(outline); ctx.drawImage(tmp, 0, 0); ctx.restore();
    ctx.strokeStyle = theme === "dark" ? "#2c3a45" : "#ccd6dd"; ctx.lineWidth = dpr; ctx.stroke(outline);
  } else {
    R.draw(c.canvas, c.src, st);
  }
  c.bars.innerHTML = regionBars(st, c.meta.zones.share_of_land);
}

function drawLegend() {
  const st = detunedStyle(theme);
  document.getElementById("legend").innerHTML = regionBars(st, { arid: 0 });
}

// ---------------------------------------------------------------- what each region is made of
function drawPlan() {
  const el = document.getElementById("plan");
  const res = (m) => (m >= 1000 ? `${m / 1000} km` : `${m} m`);
  el.innerHTML = `<thead><tr><th>Region</th><th>Example texture</th><th>Finest tiles</th><th>Sources</th><th>What improved</th></tr></thead><tbody>` +
    cards.map((c) => {
      const p = plan && plan.regions[c.reg.id], d = c.meta && c.meta.data;
      const srcs = d ? d.sources.map((s) => `${esc(s.name)} (${res(s.res_m)})`).join("; ") : "Copernicus GLO-90; EMODnet 2024; Kartverket 50 m";
      return `<tr><td class="n"><b>${esc(c.reg.name.split(" (")[0])}</b></td><td class="n">${c.meta ? res(c.drawnAt) : "–"}</td>
        <td class="n">${c.fine ? "<b>" + res(c.fine) + "</b>" : "none"}</td><td>${srcs}</td><td>${p ? esc(p.gain) : ""}</td></tr>`;
    }).join("") + "</tbody>";
}

function drawCredits() {
  const set = new Set(["Beck et al. (2023) Köppen-Geiger climate classification 1991–2020, CC BY 4.0"]);
  cards.forEach((c) => c.meta && c.meta.data && c.meta.data.attribution.forEach((a) => set.add(a)));
  document.getElementById("credits").innerHTML = "Sources: " + [...set].map(esc).join("; ") + ". Not for navigation. Code: MIT.";
}

function drawAll() { cards.forEach(drawCard); drawLegend(); }
let timer;
addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(drawAll, 200); });

await Promise.all(cards.map(loadCard));
drawAll(); drawPlan(); drawCredits();
window.__relief = { ready: true };

// Region examples: every region drawn in one fixed style (Detuned: stepped relief by climate zone, linear
// bathymetry, no contours, no illumination) from its 16-bit elevation WebP, plus the data plan per region.
import { createRenderer, loadImage } from "./relief.js";
import { detunedStyle, regionBars } from "./palette.js";

const ORDER = ["north_sea", "norwegian_sea", "barents_sea", "ne_europe", "world", "vestland"];
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
    const [elev, zones] = await Promise.all([loadImage(base + "elev.webp"), loadImage(base + "zones.png")]);
    c.meta = meta;
    c.src = { key: c.reg.id, elev, ice: null, zones, size: meta.size, cell: meta.cell, base: meta.encoding.base, step: meta.encoding.step };
  } catch { c.el.classList.add("missing"); return; }
  const d = meta.data;
  if (d) {
    const names = d.sources.map((s) => `${esc(s.name)} (${s.res_m >= 1000 ? s.res_m / 1000 + " km" : s.res_m + " m"})`).join(", ");
    c.data.innerHTML = `<b>Drawn at ${meta.cell.toLocaleString("en-GB")} m</b> · ${d.kind === "hires" ? "high-resolution build" : "first-pass data"}<br>${names}`;
  } else {
    c.data.innerHTML = `<b>Drawn at ${meta.cell.toLocaleString("en-GB")} m</b> · Copernicus GLO-90, EMODnet 2024, Kartverket 50 m`;
  }
  c.links.innerHTML = `<a href="vector.html?area=${esc(c.reg.id)}">Vector layers</a>`;
}

// Equal Earth is not a rectangle: clip the world to its outline (Šavrič, Patterson and Jenny 2019).
function equalEarthOutline(bounds, W, H) {
  const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796, R0 = 6371007.2;
  const [x0, y0, x1, y1] = bounds;
  const pt = (lat, lon) => {
    const th = Math.asin((Math.sqrt(3) / 2) * Math.sin((lat * Math.PI) / 180)), t2 = th * th, t6 = t2 * t2 * t2, lam = (lon * Math.PI) / 180;
    const x = (R0 * lam * Math.cos(th) * (2 * Math.sqrt(3) / 3)) / (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2));
    const y = R0 * th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2));
    return [((x - x0) / (x1 - x0)) * W, ((y1 - y) / (y1 - y0)) * H];
  };
  const path = new Path2D();
  for (let lat = -90; lat <= 90; lat += 2) { const [px, py] = pt(lat, 180); if (lat === -90) path.moveTo(px, py); else path.lineTo(px, py); }
  for (let lat = 90; lat >= -90; lat -= 2) { const [px, py] = pt(lat, -180); path.lineTo(px, py); }
  path.closePath();
  return path;
}

function drawCard(c) {
  if (!c.src || !R) return;
  const st = detunedStyle(theme), aspect = c.meta.size[1] / c.meta.size[0];
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

// ---------------------------------------------------------------- plan table
function drawPlan() {
  if (!plan) return;
  const el = document.getElementById("plan");
  const res = (m) => (m >= 1000 ? `${m / 1000} km` : `${m} m`);
  const top = (r, kind) => plan.regions[r.id][kind].map((id) => plan.sources[id]).filter((s) => s.status !== "unverified").slice(0, 2).map((s) => `${esc(s.name)} (${res(s.res_m)})`).join("; ");
  el.innerHTML = `<thead><tr><th>Region</th><th>Drawn now</th><th>Planned</th><th>What improves</th></tr></thead><tbody>` +
    regions.map((r) => {
      const p = plan.regions[r.id], c = cards.find((k) => k.reg.id === r.id), now = c && c.meta ? c.meta.cell : p.web_cell_m.now;
      return `<tr><td class="n"><b>${esc(r.name.split(" (")[0])}</b></td><td class="n">${res(now)} cells</td>
        <td><b>${res(p.web_cell_m.hires)} cells</b><br>Land: ${top(r, "land")}<br>Sea: ${top(r, "sea")}</td><td>${esc(p.gain)}</td></tr>`;
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

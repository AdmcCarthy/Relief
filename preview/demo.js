// Relief techniques page: case studies, sea-floor resolution comparison and a playground,
// all drawn by one WebGL renderer from one elevation texture.
import { createRenderer, loadImage } from "./relief.js";

const BASE = "data/vestland/demo/";
const meta = await fetch(BASE + "meta.json").then((r) => r.json());
const overlay = await fetch(BASE + "overlay.json").then((r) => r.json());
const R = createRenderer();
if (!R) { document.getElementById("nogl").style.display = "block"; throw new Error("no WebGL2"); }

// ---------------------------------------------------------------- theme
const root = document.documentElement;
let theme = (() => { try { return localStorage.getItem("relief:theme"); } catch { return null; } })()
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const themeSeg = document.getElementById("theme");
function setTheme(t) {
  theme = t; root.dataset.theme = t;
  themeSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === t));
  try { localStorage.setItem("relief:theme", t); } catch {}
}
themeSeg.addEventListener("click", (e) => { if (e.target.dataset.v) { setTheme(e.target.dataset.v); redrawAll(); } });
setTheme(theme);

// ---------------------------------------------------------------- palettes (stops: fraction of landMax / seaMax)
const LAND_STOPS = [0, 100, 250, 500, 750, 1000, 1250, 1500, 1800];
const SEA_STOPS = [0, 50, 100, 200, 300, 400, 500, 750, 1000];
const PAL = {
  light: {
    context: { land: [[0, "#eef0ea"], [0.3, "#e3e6de"], [0.65, "#d5d8d0"], [1, "#c6cac3"]], sea: [[0, "#e6eef4"], [0.2, "#d6e3ec"], [0.6, "#c2d5e3"], [1, "#adc6d9"]],
      coastCol: "#8a9aa6", lo: "#7b8c99", hi: "#ffffff", iceCol: "#ffffff", iceEdge: "#a9bccb" },
    showcase: { land: [[0, "#dfe8c9"], [0.06, "#cfdcb1"], [0.17, "#c9cf9e"], [0.33, "#d6c99b"], [0.5, "#cfb48f"], [0.7, "#bfa992"], [0.85, "#c9c3bc"], [1, "#eeeceb"]],
      sea: [[0, "#cfe9f5"], [0.06, "#a9d6ec"], [0.15, "#82c0e1"], [0.3, "#5ea7d3"], [0.5, "#3f8bc0"], [0.75, "#2a6ea6"], [1, "#1b4f80"]],
      coastCol: "#5d7383", lo: "#3c4d5b", hi: "#ffffff", iceCol: "#ffffff", iceEdge: "#8fa9bd" },
    bathy: { land: [[0, "#e7e9e5"], [1, "#d9dcd6"]], sea: [[0, "#d7eef8"], [0.06, "#a9d6ec"], [0.15, "#7fbfe0"], [0.3, "#5aa4d1"], [0.5, "#3a86bd"], [0.75, "#2669a1"], [1, "#174a7a"]],
      coastCol: "#6f8290", lo: "#2c5f86", hi: "#ffffff", iceCol: "#ffffff", iceEdge: "#a9bccb" },
  },
  dark: {
    context: { land: [[0, "#26313a"], [0.5, "#2e3a44"], [1, "#3a4752"]], sea: [[0, "#17252f"], [0.4, "#132029"], [1, "#0d1820"]],
      coastCol: "#4f6170", lo: "#0f1820", hi: "#5f7383", iceCol: "#c9d6df", iceEdge: "#7d93a3" },
    showcase: { land: [[0, "#34412e"], [0.12, "#3c4a33"], [0.3, "#4a5038"], [0.5, "#5c5845"], [0.7, "#6b6355"], [0.88, "#8a857f"], [1, "#b2aea9"]],
      sea: [[0, "#1f5571"], [0.1, "#1c4863"], [0.3, "#163a52"], [0.55, "#112d42"], [1, "#0a1c2c"]],
      coastCol: "#7a93a5", lo: "#0b141b", hi: "#cfe3ee", iceCol: "#e8f0f5", iceEdge: "#8ea7b8" },
    bathy: { land: [[0, "#28333c"], [1, "#323e48"]], sea: [[0, "#2a6f93"], [0.1, "#225d7d"], [0.3, "#1a4964"], [0.55, "#13374e"], [1, "#0a2033"]],
      coastCol: "#7f97a8", lo: "#0b141b", hi: "#d4ecf7", iceCol: "#d9e4eb", iceEdge: "#7d93a3" },
  },
};
function style(palette, opts = {}) {
  const P = PAL[theme][palette];
  return { land: P.land, sea: P.sea, landMax: 1800, seaMax: 1100, landStops: LAND_STOPS, seaStops: SEA_STOPS,
    coastCol: P.coastCol, lo: P.lo, hi: P.hi, iceCol: P.iceCol, iceEdge: P.iceEdge, ...opts };
}

// ---------------------------------------------------------------- colour bars
// Same interpolation as the shader's ramp texture, so the bar shows exactly the colours on the map.
function rampAt(stops, t) {
  t = Math.min(1, Math.max(0, t)); let k = 0;
  while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
  const [t0, c0] = stops[k], [t1, c1] = stops[k + 1], f = Math.min(1, Math.max(0, (t - t0) / (t1 - t0 || 1)));
  const a = [1, 3, 5].map((i) => parseInt(c0.slice(i, i + 2), 16)), b = [1, 3, 5].map((i) => parseInt(c1.slice(i, i + 2), 16));
  return `rgb(${a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(",")})`;
}
const fmtM = (v) => v.toLocaleString("en-GB");
function bar(label, stops, max, bands, stepped, ticks) {
  if (stepped) {  // hypsometric classes: one block per band, labelled with its range
    const cells = bands.map((lo, i) => {
      const hi = bands[i + 1];
      const mid = hi == null ? lo + (lo - bands[i - 1]) / 2 : (lo + hi) / 2;
      return `<span class="cb-band" style="background:${rampAt(stops, mid / max)}" title="${fmtM(lo)}${hi == null ? "+" : `–${fmtM(hi)}`} m"></span>`;
    }).join("");
    const labs = bands.map((v, i) => `<span>${fmtM(v)}${i === bands.length - 1 ? "+" : ""}</span>`).join("") + "<span></span>";
    return `<div class="cb"><span class="cb-l">${label}</span><div class="cb-steps" style="--n:${bands.length}">${cells}</div><div class="cb-labs" style="--n:${bands.length}">${labs}</div></div>`;
  }
  const grad = Array.from({ length: 24 }, (_, i) => `${rampAt(stops, i / 23)} ${(i / 23 * 100).toFixed(1)}%`).join(",");
  const tk = ticks.filter((v) => v / max < 0.85).map((v) => `<span style="left:${(v / max) * 100}%">${fmtM(v)}</span>`).join("");
  return `<div class="cb"><span class="cb-l">${label}</span><div class="cb-lin" style="background:linear-gradient(90deg,${grad})"></div><div class="cb-ticks">${tk}<span style="left:100%">${fmtM(max)}+</span></div></div>`;
}
function colourBars(st) {
  const kind = st.stepped ? "Hypsometric classes, m" : "Linear, m";
  return `<div class="cbs"><span class="cb-kind">${kind}</span>` +
    bar("Height", st.land, st.landMax, st.landStops, st.stepped, [0, 500, 1000, 1500]) +
    bar("Depth", st.sea, st.seaMax, st.seaStops, st.stepped, [0, 200, 500, 1000]) + "</div>";
}

// ---------------------------------------------------------------- sources
const [elev, ice] = await Promise.all([loadImage(BASE + "elev.webp"), loadImage(BASE + "glacier.png")]);
const main = { key: "main", elev, ice, size: meta.size, cell: meta.cell, base: meta.encoding.base, step: meta.encoding.step };

// ---------------------------------------------------------------- case studies
const CASES = [
  { id: "context", title: "Quiet context for data", text: "Muted tints and a soft shade keep the land legible while wells and fields, in story colours, carry the meaning.",
    tags: ["linear", "soft shade", "overlay"], best: "Maps whose job is the data on top: SubScout's default base.",
    s: () => style("context", { shade: "soft", shadeK: 0.35, seaShadeK: 0.25, coast: true, ice: true }), overlay: true },
  { id: "stepped", title: "Stepped tints", text: "Height and depth in classes. Every colour maps to one legend entry, so values can be read back.",
    tags: ["stepped", "classes"], best: "Print, legends, and readers who need to read heights.",
    s: () => style("showcase", { stepped: true, coast: true }) },
  { id: "linear", title: "Linear gradient", text: "One continuous ramp for land and one for sea. Smooth and calm, but it hides the shape of slopes.",
    tags: ["linear"], best: "Small maps and backgrounds behind text.",
    s: () => style("showcase", { coast: true }) },
  { id: "single", title: "Hillshade, one light", text: "The classic shaded relief: light from the north-west, slopes facing it lit, the rest in shadow.",
    tags: ["linear", "hillshade", "315°"], best: "Showing landforms: fjords, valleys, the trench.",
    s: () => style("showcase", { shade: "single", shadeK: 0.65, seaShadeK: 0.45, coast: true }) },
  { id: "soft", title: "Soft multi-directional shade", text: "Six lights round the compass, weighted to the north-west, plus sky light: no slope sinks into black.",
    tags: ["linear", "multi-directional", "sky light"], best: "Large areas with relief in every direction.",
    s: () => style("showcase", { shade: "soft", shadeK: 0.6, seaShadeK: 0.45, coast: true }) },
  { id: "tanaka", title: "Illuminated contours", text: "Tanaka's method: stepped tints whose edges are lit where they face the light and shaded where they face away.",
    tags: ["stepped", "contours", "Tanaka"], best: "Showpiece maps with a crafted, layered look.",
    s: () => style("showcase", { stepped: true, contours: "tanaka", landInt: 500, seaInt: 200, lineK: 0.9 }) },
  { id: "bathy", title: "Sea floor first", text: "Land falls back to a flat grey; depth carries the colour and the shade. Fjords show as deep as the trench.",
    tags: ["linear", "bathymetry", "soft shade"], best: "Offshore stories: fields, wells, pipelines, licences.",
    s: () => style("bathy", { shade: "soft", shadeK: 0.15, seaShadeK: 0.75, coast: true, contours: "lines", landInt: 1e6, seaInt: 100, lineK: 0.25, exag: 4 }) },
  { id: "ice", title: "Glaciers in white", text: "Folgefonna and Hardangerjøkulen from the glacier inventory, white with a cool edge, shaded with the land.",
    tags: ["soft shade", "glacier outlines"], best: "Mountain maps; the observed 'always white' layer.",
    s: () => style("showcase", { shade: "soft", shadeK: 0.6, seaShadeK: 0.4, coast: true, ice: true }) },
  { id: "lines", title: "Contour lines only", text: "Plain index contours over a near-flat tint: precise and light, and the cheapest to print.",
    tags: ["lines", "500 m / 200 m"], best: "Technical figures and overlays that need to stay thin.",
    s: () => style("context", { contours: "lines", landInt: 500, seaInt: 200, lineK: 0.6, coast: true }) },
];
const casesEl = document.getElementById("cases");
CASES.forEach((c) => {
  const card = document.createElement("article");
  card.className = "card";
  card.innerHTML = `<canvas width="${meta.size[0] / 2}" height="${meta.size[1] / 2}" aria-label="${c.title}"></canvas>
    <div class="txt"><h3>${c.title}</h3><p>${c.text}</p><div class="tags">${c.tags.map((t) => `<span class="tag">${t}</span>`).join("")}</div>
    <div class="cbwrap"></div><p class="best"><b>Best for:</b> ${c.best}</p></div>`;
  casesEl.append(card);
  c.canvas = card.querySelector("canvas");
  c.bars = card.querySelector(".cbwrap");
});
const dpr = Math.min(2, window.devicePixelRatio || 1);
function sizeTo(cv, aspect) { const w = Math.round(cv.clientWidth * dpr) || 600; cv.width = w; cv.height = Math.round(w * aspect); }

const [x0, y0, x1, y1] = meta.bounds;
function drawOverlay(cv) {
  const ctx = cv.getContext("2d"), sx = cv.width / (x1 - x0), sy = cv.height / (y1 - y0);
  const P = (x, y) => [(x - x0) * sx, (y1 - y) * sy];
  ctx.save(); ctx.lineWidth = Math.max(1, cv.width / 600);
  ctx.strokeStyle = theme === "dark" ? "#8cabc4" : "#3c4d5b"; ctx.fillStyle = theme === "dark" ? "rgba(140,171,196,.18)" : "rgba(60,77,91,.12)";
  overlay.fields.forEach((ring) => { ctx.beginPath(); ring.forEach(([x, y], i) => (i ? ctx.lineTo(...P(x, y)) : ctx.moveTo(...P(x, y)))); ctx.closePath(); ctx.fill(); ctx.stroke(); });
  const r = Math.max(2.5, cv.width / 170);
  overlay.wells.forEach(([x, y, yr, hit]) => { const [px, py] = P(x, y); ctx.beginPath(); ctx.arc(px, py, r, 0, 7);
    ctx.fillStyle = hit ? (theme === "dark" ? "#61b9ea" : "#00729f") : (theme === "dark" ? "#e49b68" : "#9c5313"); ctx.fill();
    ctx.strokeStyle = theme === "dark" ? "#15212a" : "#fdfeff"; ctx.lineWidth = r * 0.45; ctx.stroke(); });
  ctx.restore();
}
function drawCases() {
  CASES.forEach((c) => { const st = c.s(); sizeTo(c.canvas, meta.size[1] / meta.size[0]); R.draw(c.canvas, main, st); if (c.overlay) drawOverlay(c.canvas);
    c.bars.innerHTML = colourBars(st); });
}

// ---------------------------------------------------------------- sea-floor comparison (loaded when near view)
const CMP = [["gebco450", "GEBCO-like, about 450 m", "EMODnet averaged to GEBCO's 15″ grid"], ["emodnet115", "EMODnet DTM 2024, about 115 m", "European seas, all surveys composited"],
  ["kartverket50", "Kartverket, 50 m", "Norwegian waters, open model (CC BY 4.0)"]];
const cmpEl = document.getElementById("cmp");
CMP.forEach(([k, t, d]) => { const f = document.createElement("figure");
  f.innerHTML = `<canvas width="720" height="720" aria-label="${t}"></canvas><figcaption><b>${t}</b>${d} · ${(meta.files[k + ".webp"] / 1e3).toFixed(0)} KB</figcaption>`; cmpEl.append(f); });
const cmpSrc = {};
async function drawCompare() {
  for (const [k] of CMP) {
    if (!cmpSrc[k]) cmpSrc[k] = { key: k, elev: await loadImage(`${BASE}compare/${k}.webp`), ice: null, size: meta.compare.size, cell: meta.compare.cell, base: meta.encoding.base, step: meta.encoding.step };
  }
  cmpEl.querySelectorAll("canvas").forEach((cv, i) => { sizeTo(cv, 1);
    R.draw(cv, cmpSrc[CMP[i][0]], style("bathy", { shade: "soft", shadeK: 0.2, seaShadeK: 0.8, exag: 3, coast: true, landMax: 1800, seaMax: 400 })); });
}
let cmpReady = false;
new IntersectionObserver(([e]) => { if (e.isIntersecting && !cmpReady) { cmpReady = true; drawCompare(); } }, { rootMargin: "50% 0px" }).observe(cmpEl);

// ---------------------------------------------------------------- playground
const play = { palette: "showcase", stepped: "0", shade: "soft", contours: "none", zoom: "all" };
const ZOOM = {  // view rectangles in texture uv (x0, y0, x1, y1; y runs south)
  all: [0, 0, 1, 1],
  bergen: [0.18, 0.42, 0.44, 0.62],
  folgefonna: [0.48, 0.62, 0.74, 0.82],
  sogn: [0.30, 0.10, 0.80, 0.42],
};
const pc = document.getElementById("play"), stat = document.getElementById("stat");
const ctl = document.getElementById("ctl");
ctl.querySelectorAll(".seg").forEach((seg) => seg.addEventListener("click", (e) => { if (!e.target.dataset.v) return; play[seg.dataset.k] = e.target.dataset.v; drawPlay(); }));
["az", "alt", "exag", "ice"].forEach((id) => document.getElementById(id).addEventListener("input", () => drawPlay()));
let pending = false;
function drawPlay() {
  if (pending) return; pending = true;
  requestAnimationFrame(() => {
    pending = false;
    ctl.querySelectorAll(".seg").forEach((seg) => seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === play[seg.dataset.k])));
    const v = ZOOM[play.zoom], aspect = ((v[3] - v[1]) * meta.size[1]) / ((v[2] - v[0]) * meta.size[0]);
    sizeTo(pc, aspect); pc.style.aspectRatio = `${1 / aspect}`;
    const pst = style(play.palette, {
      stepped: play.stepped === "1", shade: play.shade, contours: play.contours, ice: document.getElementById("ice").checked, coast: true,
      az: +document.getElementById("az").value, alt: +document.getElementById("alt").value, exag: +document.getElementById("exag").value,
      shadeK: play.palette === "bathy" ? 0.15 : 0.6, seaShadeK: play.palette === "bathy" ? 0.75 : 0.45,
      landInt: play.palette === "bathy" ? 1e6 : (play.zoom === "all" ? 500 : 200), seaInt: play.zoom === "all" ? 200 : 100, lineK: play.contours === "tanaka" ? 0.85 : 0.5 });
    const ms = R.draw(pc, { ...main, view: v }, pst);
    document.getElementById("playbars").innerHTML = colourBars(pst);
    stat.textContent = `${pc.width} × ${pc.height} px drawn in ${ms.toFixed(1)} ms`;
  });
}

function redrawAll() { drawCases(); if (cmpReady) drawCompare(); drawPlay(); }
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(redrawAll, 200); });
redrawAll();
window.__relief = { ready: true };

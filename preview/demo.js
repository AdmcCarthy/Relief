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
// readiness is signalled after the new sections below

// ================================================================ new sections
const LB = [0, 50, 150, 300, 600, 1000, 1500, 2000];   // land steps (m)
const SB = [0, 20, 50, 100, 200, 500, 1000];           // sea steps (m depth): finest near the coast
const LMAX = 2000, SMAX = 1300;
const at = (breaks, cols, max) => breaks.map((b, i) => [b / max, cols[i]]).concat(cols.length > breaks.length ? [[1, cols.at(-1)]] : []);
const ZPAL = {
  light: {
    temperate: ["#d6e8b8", "#c6dea0", "#bad38f", "#cbcf92", "#d9c897", "#ccb8a0", "#d8d0c6", "#efece8"],
    boreal: ["#a9c7a6", "#97bb98", "#8aae8c", "#93a98b", "#a8ad96", "#ccb8a0", "#d8d0c6", "#efece8"],
    tundra: ["#e0e3dc", "#d6dad2", "#cdd1c9", "#c6c8c0", "#c4c0b6", "#ccb8a0", "#d8d0c6", "#efece8"],
    arid: ["#efe2c2", "#e9d6ac", "#e1c695", "#d6b382", "#c9a077", "#ccb8a0", "#d8d0c6", "#efece8"],
    sea: ["#e3f2f9", "#c6e5f3", "#a6d3eb", "#82bde0", "#5fa3d2", "#3f85bd", "#29689f", "#1b4f80"],
  },
  dark: {
    temperate: ["#46572f", "#4c5d33", "#536237", "#5d633b", "#665f42", "#655d50", "#85807a", "#aaa6a1"],
    boreal: ["#2c4232", "#304836", "#354d39", "#3f513e", "#4e5547", "#655d50", "#85807a", "#aaa6a1"],
    tundra: ["#55595a", "#585b5b", "#5b5d5c", "#5e5e5b", "#615d57", "#655d50", "#85807a", "#aaa6a1"],
    arid: ["#5e533c", "#665a3f", "#6c5c40", "#6e5a43", "#6a5747", "#655d50", "#85807a", "#aaa6a1"],
    sea: ["#2f7896", "#286a87", "#225c78", "#1c4e69", "#16405a", "#11334b", "#0c263c", "#081c2e"],
  },
};
function nlStyle(opts = {}) {
  const Z = ZPAL[theme];
  const land = at(LB, Z.temperate, LMAX);
  return { land, sea: at(SB, Z.sea, SMAX), landMax: LMAX, seaMax: SMAX, landStops: LB, seaStops: SB, stepped: true,
    coastCol: theme === "dark" ? "#7a93a5" : "#6f8290", lo: theme === "dark" ? "#0b141b" : "#3c4d5b", hi: theme === "dark" ? "#cfe3ee" : "#ffffff",
    iceCol: theme === "dark" ? "#e8f0f5" : "#ffffff", iceEdge: theme === "dark" ? "#8ea7b8" : "#8fa9bd", coast: true, ice: true,
    zones: opts.climate ? { temperate: land, boreal: at(LB, Z.boreal, LMAX), tundra: at(LB, Z.tundra, LMAX), arid: at(LB, Z.arid, LMAX) } : null, ...opts };
}

// piecewise colour bar: equal width per step so the fine shallow steps stay readable
function nlBar(label, cols, breaks, unit = "m") {
  const n = breaks.length;
  const cells = breaks.map((lo, i) => `<span class="cb-band" style="background:${cols[i]}" title="${fmtM(lo)}${i + 1 < n ? `–${fmtM(breaks[i + 1])}` : "+"} ${unit}"></span>`).join("");
  const labs = breaks.map((v, i) => `<span>${fmtM(v)}${i === n - 1 ? "+" : ""}</span>`).join("") + "<span></span>";
  return `<div class="cb"><span class="cb-l">${label}</span><div class="cb-steps" style="--n:${n}">${cells}</div><div class="cb-labs" style="--n:${n}">${labs}</div></div>`;
}
// band colours as the shader draws them: the ramp at each band's middle
function bandCols(stops, breaks, max) {
  return breaks.map((lo, i) => { const hi = breaks[i + 1] ?? lo + (lo - (breaks[i - 1] ?? 0)) / 2 * 2; return rampAt(stops, ((lo + hi) / 2) / max); });
}

const [zonesImg, sourcesImg] = await Promise.all([loadImage(BASE + "zones.png"), loadImage(BASE + "sources.png")]);
main.zones = zonesImg;
const ZNAMES = { temperate: ["Temperate, humid", "Cfb: the outer coast"], boreal: ["Boreal (subarctic)", "Dfb, Dfc: inland valleys and slopes"],
  tundra: ["Tundra (Arctic, alpine)", "ET: plateaus above the tree line"], arid: ["Arid", "BW, BS: deserts and steppes (not in Vestland)"] };
const ZONECOL = { temperate: "#6fa86a", boreal: "#3f7d6b", tundra: "#b9b7a8", arid: "#d6a85c" };

function sizeFig(cv, aspect) { const w = Math.round((cv.clientWidth || 360) * dpr); cv.width = w; cv.height = Math.round(w * aspect); }
const ASPECT = meta.size[1] / meta.size[0];

function drawClimate() {
  const Z = ZPAL[theme];
  const conv = document.getElementById("cl-conv"), zone = document.getElementById("cl-zone"), mapc = document.getElementById("cl-map");
  [conv, zone, mapc].forEach((c) => sizeFig(c, ASPECT));
  R.draw(conv, main, nlStyle({ shade: "soft", shadeK: 0.45, seaShadeK: 0.3 }));
  R.draw(zone, main, nlStyle({ climate: true, shade: "soft", shadeK: 0.45, seaShadeK: 0.3 }));
  // zone map: weights painted in zone colours over a pale land mask
  const ctx = mapc.getContext("2d"), tmp = document.createElement("canvas");
  tmp.width = zonesImg.width; tmp.height = zonesImg.height; const t = tmp.getContext("2d"); t.drawImage(zonesImg, 0, 0);
  const px = t.getImageData(0, 0, tmp.width, tmp.height), d = px.data, cols = ["temperate", "boreal", "tundra", "arid"].map((k) => [1, 3, 5].map((i) => parseInt(ZONECOL[k].slice(i, i + 2), 16)));
  for (let i = 0; i < d.length; i += 4) { const w = [d[i], d[i + 1], d[i + 2]]; const a = Math.max(0, 255 - w[0] - w[1] - w[2]); const ws = [...w, a];
    for (let j = 0; j < 3; j++) d[i + j] = Math.round(ws.reduce((s, v, k) => s + v * cols[k][j], 0) / 255); d[i + 3] = 255; }
  t.putImageData(px, 0, 0);
  ctx.imageSmoothingEnabled = true; ctx.drawImage(tmp, 0, 0, mapc.width, mapc.height);
  // land only: mask sea from the source map (0 = land)
  const sm = document.createElement("canvas"); sm.width = sourcesImg.width; sm.height = sourcesImg.height; const sc = sm.getContext("2d"); sc.drawImage(sourcesImg, 0, 0);
  const sp = sc.getImageData(0, 0, sm.width, sm.height); const seaCol = theme === "dark" ? [21, 33, 42] : [236, 241, 245];
  for (let i = 0; i < sp.data.length; i += 4) { const sea = sp.data[i] > 0; sp.data[i] = seaCol[0]; sp.data[i + 1] = seaCol[1]; sp.data[i + 2] = seaCol[2]; sp.data[i + 3] = sea ? 255 : 0; }
  sc.putImageData(sp, 0, 0); ctx.drawImage(sm, 0, 0, mapc.width, mapc.height);
  const sh = meta.zones.share_of_land;
  document.getElementById("cl-share").innerHTML = ["temperate", "boreal", "tundra"].map((k) => `<span class="sw" style="background:${ZONECOL[k]}"></span>${ZNAMES[k][0]} ${Math.round(sh[k] * 100)} %`).join("") + ` of land. Source: Beck et al. (2023), CC BY 4.0.`;
  document.getElementById("zonebars").innerHTML = ["tundra", "boreal", "temperate", "arid"].map((k) =>
    `<div class="zb"><h4>${ZNAMES[k][0]}</h4><p>${ZNAMES[k][1]}</p>${nlBar("Height", bandCols(at(LB, Z[k], LMAX), LB, LMAX), LB)}</div>`).join("");
}

function drawSteps() {
  const flat = document.getElementById("st-flat"), soft = document.getElementById("st-soft"), zoom = document.getElementById("st-zoom");
  [flat, soft].forEach((c) => sizeFig(c, ASPECT)); sizeFig(zoom, 1);
  R.draw(flat, main, nlStyle({ climate: true }));
  R.draw(soft, main, nlStyle({ climate: true, shade: "soft", shadeK: 0.45, seaShadeK: 0.85, exag: 3 }));
  if (cmpSrc.kartverket50) R.draw(zoom, cmpSrc.kartverket50, nlStyle({ shade: "soft", shadeK: 0.45, seaShadeK: 0.85, exag: 3 }));
  const Z = ZPAL[theme];
  document.getElementById("stepbars").innerHTML = `<div class="cbs"><span class="cb-kind">Non-linear steps, m</span>${nlBar("Depth", bandCols(at(SB, Z.sea, SMAX), SB, SMAX), SB)}${nlBar("Height", bandCols(at(LB, Z.temperate, LMAX), LB, LMAX), LB)}</div>`;
  document.getElementById("shade-notes").innerHTML = [
    "<b>At 200 m over the whole area</b>, soft shading on the sea floor works: the Norwegian Trench, its slope and the fjord basins gain form without hiding the depth classes.",
    "<b>At 50 m (Kartverket)</b> it shows real sea-floor features (sills, channels, glacial ridges), so it is worth using wherever the 50 m model exists.",
    "<b>On 450 m data (GEBCO)</b> it mainly shows the grid: smooth bowls and interpolation artefacts, so keep sea-floor shading off or very weak there.",
    "Sea-floor shading needs about 3× vertical exaggeration to show at all, against 2× on land: the sea floor is gentler than the mountains around it.",
  ].map((t) => `<li>${t}</li>`).join("");
}

function drawSources() {
  const c = document.getElementById("src-map"); sizeFig(c, ASPECT);
  const ctx = c.getContext("2d"), tmp = document.createElement("canvas"); tmp.width = sourcesImg.width; tmp.height = sourcesImg.height;
  const t = tmp.getContext("2d"); t.drawImage(sourcesImg, 0, 0);
  const px = t.getImageData(0, 0, tmp.width, tmp.height), d = px.data;
  const COL = theme === "dark" ? { 0: [53, 65, 75], 1: [214, 168, 92], 2: [111, 141, 165], 3: [196, 120, 106], 4: [85, 179, 189] }
                               : { 0: [226, 230, 222], 1: [214, 168, 92], 2: [150, 174, 194], 3: [196, 120, 106], 4: [26, 127, 136] };
  for (let i = 0; i < d.length; i += 4) { const k = COL[d[i]] ?? COL[0]; d[i] = k[0]; d[i + 1] = k[1]; d[i + 2] = k[2]; d[i + 3] = 255; }
  t.putImageData(px, 0, 0); ctx.imageSmoothingEnabled = false; ctx.drawImage(tmp, 0, 0, c.width, c.height);
  const hex = (k) => `rgb(${COL[k].join(",")})`;
  const S = meta.seabed, share = S.share_of_sea;
  document.getElementById("src-legend").innerHTML = [[4, "Kartverket 50 m"], [3, "Denmark 50 m"], [2, "EMODnet 115 m"], [1, "GEBCO 450 m"]]
    .map(([k, n]) => `<span class="sw" style="background:${hex(k)}"></span>${n}`).join("");
  const ov = S.overlap.kartverket;
  document.getElementById("src-stats").innerHTML = `<h3 style="margin:0 0 6px;font:600 15px var(--body)">This area</h3>
    <table><tbody>${["kartverket", "denmark", "emodnet", "gebco"].map((k) => `<tr><td>${{ kartverket: "Kartverket 50 m", denmark: "Denmark 50 m", emodnet: "EMODnet 115 m", gebco: "GEBCO 450 m" }[k]}</td><td>${k in share ? Math.round(share[k] * 100) + " % of the sea" : (S.available.includes(k) ? "available" : "not in this area")}</td></tr>`).join("")}</tbody></table>
    <p class="note" style="margin-top:12px">Where Kartverket and EMODnet overlap (${ov.overlap_cells.toLocaleString("en-GB")} cells), they agree to a median of ${ov.median_diff_m} m and within ${ov.p90_abs_diff_m} m for 90 % of cells: EMODnet already includes Kartverket's surveys, so the 50 m model adds resolution rather than different depths.</p>
    <p class="note">Denmark's model needs a free Dataforsyningen account to download; place its GeoTIFFs in <code>data/raw/&lt;area&gt;/denmark_dybdemodel50/</code> and the build uses them. GEBCO subsets go in <code>gebco/</code>.</p>`;
}

// contours for the eye (loaded when near view)
const LINE_METHODS = [["raw", "Raw marching squares", "Every cell crossing: faithful, jagged, heavy."],
  ["dp", "Douglas–Peucker", "1 cell tolerance, topology kept: keeps corners, angular look."],
  ["vw", "Visvalingam–Whyatt", "4 cell² area: drops small wiggles first; still angular."],
  ["dp_chaikin", "Douglas–Peucker + Chaikin ×3", "Corners cut into smooth curves inside the original line."],
  ["vw_catmull", "Visvalingam–Whyatt + Catmull–Rom", "Centripetal spline through the kept points: smooth, no loops."],
  ["blur_chaikin", "Blur + Douglas–Peucker + Chaikin ×2", "Recommended: grid blurred first, specks gone, calm curves."]];
let linesData = null;
async function drawLines() {
  if (!linesData) linesData = await fetch(BASE + "contours_visual.json").then((r) => r.json());
  const L = linesData, el = document.getElementById("lines");
  if (!el.children.length) el.innerHTML = LINE_METHODS.map(([k, t, d]) => `<figure class="pane"><canvas data-k="${k}"></canvas><figcaption><b>${t}</b>${d}</figcaption></figure>`).join("");
  const Z = ZPAL[theme];
  el.querySelectorAll("canvas").forEach((cv) => {
    sizeFig(cv, 1); const ctx = cv.getContext("2d"), k = cv.width / (L.size[0] * 4);
    ctx.fillStyle = theme === "dark" ? "#15212a" : "#fdfeff"; ctx.fillRect(0, 0, cv.width, cv.height);
    for (const f of L.methods[cv.dataset.k].lines) {
      const c = f.c; ctx.beginPath(); ctx.moveTo(c[0] * k, c[1] * k);
      for (let i = 2; i < c.length; i += 2) ctx.lineTo(c[i] * k, c[i + 1] * k);
      const idx = (f.k === "sea" ? SB : LB).indexOf(f.l);
      ctx.strokeStyle = f.k === "sea" ? Z.sea[Math.min(idx + 2, 7)] : (theme === "dark" ? "#a99f8c" : "#8b7d6b");
      ctx.lineWidth = (f.l === 100 || f.l === 300 ? 1.4 : 0.8) * dpr; ctx.stroke();
    }
  });
  document.getElementById("lines-table").innerHTML = `<thead><tr><th>Method</th><th>Points</th><th>Size</th><th>Self-crossing rings</th></tr></thead><tbody>` +
    LINE_METHODS.map(([k, t]) => { const m = L.methods[k]; return `<tr><td>${t}</td><td>${m.points.toLocaleString("en-GB")}</td><td>${Math.round(m.bytes / 1e3)} KB</td><td>${m.self_intersecting_rings}</td></tr>`; }).join("") + "</tbody>";
}

async function drawNew() {
  drawClimate(); drawSources();
  if (!cmpSrc.kartverket50) cmpSrc.kartverket50 = { key: "kartverket50", elev: await loadImage(`${BASE}compare/kartverket50.webp`), ice: null, size: meta.compare.size, cell: meta.compare.cell, base: meta.encoding.base, step: meta.encoding.step };
  drawSteps();
  if (linesReady) drawLines();
}
let linesReady = false;
new IntersectionObserver(([e]) => { if (e.isIntersecting && !linesReady) { linesReady = true; drawLines(); } }, { rootMargin: "50% 0px" }).observe(document.getElementById("lines"));
const _redraw = redrawAll;
redrawAll = () => { _redraw(); drawNew(); };  // eslint-disable-line no-func-assign
await drawNew();
window.__relief = { ready: true };

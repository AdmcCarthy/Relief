// Relief techniques page: case studies, sea-floor resolution comparison and a playground,
// all drawn by one WebGL renderer from one elevation texture.
import { createRenderer, loadImage } from "./relief.js";
import { LB, SB, LMAX, SMAX, at, ZPAL, DETUNED_SEA, ZK, tune, rampAt, fmtM, strip, axis } from "./palette.js";

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

// ---------------------------------------------------------------- palettes
// Class breaks, tints, tune() and the Detuned sea ramp live in palette.js, shared with the region examples.
function paletteSet(name) {
  const Z = ZPAL[theme], dark = theme === "dark", calm = dark ? -0.22 : 0.3;
  const land = (sat, mix) => Object.fromEntries(ZK.map((k) => [k, at(LB, Z[k].map((c) => tune(c, sat, mix)), LMAX)]));
  const sea = (sat, mix, cols = Z.sea) => at(SB, cols.map((c) => tune(c, sat, mix)), SMAX);
  const ink = dark ? { coastCol: "#7a93a5", lo: "#0b141b", hi: "#cfe3ee", iceCol: "#e8f0f5", iceEdge: "#8ea7b8" }
                   : { coastCol: "#6f8290", lo: "#3c4d5b", hi: "#ffffff", iceCol: "#ffffff", iceEdge: "#8fa9bd" };
  switch (name) {
    case "context":   // the relief set, muted: land and sea desaturated and lifted so data on top carries the colour
      return { ...ink, land: land(0.38, calm), sea: sea(0.4, calm), shadeK: 0.35, seaShadeK: 0.25 };
    case "bathy":     // land almost grey, sea floor at full strength
      return { ...ink, land: land(0.18, calm), sea: sea(1.1, 0), shadeK: 0.15, seaShadeK: 0.75 };
    case "detuned":   // own style: half-strength land tints, wide-range deep sea floor with strong shading
      return { ...ink, land: land(0.5, dark ? -0.08 : 0.08), sea: sea(1, 0, DETUNED_SEA[theme]), shadeK: 0.35, seaShadeK: 0.9 };
    default:          // relief: full-strength cross-blended tints
      return { ...ink, land: land(1, 0), sea: sea(1, 0), shadeK: 0.6, seaShadeK: 0.45 };
  }
}
// climate: false -> one (temperate) ramp everywhere. The coastline is off by default: at the scale of Norway's
// skerries it reads as noise; when on it is drawn at low opacity (coastK).
function style(name, opts = {}) {
  const { land, ...rest } = paletteSet(name);
  return { land: land.temperate, zones: opts.climate === false ? null : land, landMax: LMAX, seaMax: SMAX, landStops: LB, seaStops: SB,
    coast: false, coastK: 0.3, ...rest, ...opts };
}

// ---------------------------------------------------------------- colour bars
// One height strip per climate zone present (arid only where the area has any), then depth: the legend is
// honest about which tints appear where.
function colourBars(st) {
  const kind = (st.stepped ? "Hypsometric classes, m" : "Linear, m") + (st.zones ? " · by climate zone" : "");
  const arid = meta.zones.share_of_land.arid > 0;
  const land = st.zones ? [["Temperate", st.zones.temperate], ["Boreal", st.zones.boreal], ["Tundra", st.zones.tundra], ...(arid ? [["Arid", st.zones.arid]] : [])]
                        : [["Height", st.land]];
  return `<div class="cbs"><span class="cb-kind">${kind}</span><div class="cbg">` +
    land.map(([l, sp]) => strip(l, sp, st.landMax, st.landStops, st.stepped)).join("") + axis(st.landMax, st.landStops, st.stepped, [0, 500, 1000, 1500]) +
    strip("Depth", st.sea, st.seaMax, st.seaStops, st.stepped) + axis(st.seaMax, st.seaStops, st.stepped, [0, 200, 500, 1000]) + "</div></div>";
}

// ---------------------------------------------------------------- sources
const [elev, ice, zonesImg, sourcesImg] = await Promise.all([loadImage(BASE + "elev.webp"), loadImage(BASE + "glacier.png"), loadImage(BASE + "zones.png"), loadImage(BASE + "sources.png")]);
const main = { key: "main", elev, ice, zones: zonesImg, size: meta.size, cell: meta.cell, base: meta.encoding.base, step: meta.encoding.step };

// ---------------------------------------------------------------- case studies
const CASES = [
  { id: "context", title: "Quiet context for data", text: "The climate-aware tints, muted and lifted, with a soft shade: land stays legible while wells and fields, in story colours, carry the meaning.",
    tags: ["linear", "muted tints", "soft shade", "overlay"], best: "Maps whose job is the data on top: SubScout's default base.",
    s: () => style("context", { shade: "soft", ice: true }), overlay: true },
  { id: "stepped", title: "Stepped, climate-aware tints", text: "Non-linear classes (finest in shallow water) with a land ramp per climate zone: fresh green on the temperate coast, cooler green in boreal valleys, lichen grey on the tundra.",
    tags: ["stepped", "cross-blended", "classes"], best: "Print, legends, and readers who need to read heights.",
    s: () => style("relief", { stepped: true, ice: true }) },
  { id: "linear", title: "Linear, climate-aware", text: "One continuous ramp per climate zone and one for the sea. Smooth and calm, but it hides the shape of slopes.",
    tags: ["linear", "cross-blended"], best: "Small maps and backgrounds behind text.",
    s: () => style("relief", { ice: true }) },
  { id: "single", title: "Hillshade, one light", text: "The classic shaded relief: light from the north-west, slopes facing it lit, the rest in shadow.",
    tags: ["linear", "hillshade", "315°"], best: "Showing landforms: fjords, valleys, the trench.",
    s: () => style("relief", { shade: "single", shadeK: 0.65, seaShadeK: 0.45, ice: true }) },
  { id: "soft", title: "Soft multi-directional shade", text: "Six lights round the compass, weighted to the north-west, plus sky light: no slope sinks into black.",
    tags: ["linear", "multi-directional", "sky light"], best: "Large areas with relief in every direction.",
    s: () => style("relief", { shade: "soft", ice: true }) },
  { id: "tanaka", title: "Illuminated contours", text: "Tanaka's method: stepped tints whose edges are lit where they face the light and shaded where they face away.",
    tags: ["stepped", "contours", "Tanaka"], best: "Showpiece maps with a crafted, layered look.",
    s: () => style("relief", { stepped: true, contours: "tanaka", landInt: 500, seaInt: 200, lineK: 0.9, ice: true }) },
  { id: "bathy", title: "Sea floor first", text: "Land falls back to near-grey with a trace of its climate tint; depth carries the colour and the shade. Fjords show as deep as the trench.",
    tags: ["linear", "bathymetry", "soft shade"], best: "Offshore stories: fields, wells, pipelines, licences.",
    s: () => style("bathy", { shade: "soft", contours: "lines", landInt: 1e6, seaInt: 100, lineK: 0.25, exag: 4 }) },
  { id: "ice", title: "Glaciers in white", text: "Folgefonna and Hardangerjøkulen from the glacier inventory, white with a cool edge, shaded with the land.",
    tags: ["soft shade", "glacier outlines"], best: "Mountain maps; the observed 'always white' layer.",
    s: () => style("relief", { shade: "soft", ice: true }) },
  { id: "lines", title: "Contour lines only", text: "Plain index contours over a quiet tint: precise and light, and the cheapest to print.",
    tags: ["lines", "500 m / 200 m"], best: "Technical figures and overlays that need to stay thin.",
    s: () => style("context", { contours: "lines", landInt: 500, seaInt: 200, lineK: 0.32 }) },
  { id: "det-step", title: "Detuned, stepped", text: "A house style: land at half strength so it recedes, a wide-range sea floor in deep indigo with strong shading, in the same climate steps.",
    tags: ["stepped", "detuned", "soft shade"], best: "Offshore and coastal stories that still want a sense of place.",
    s: () => style("detuned", { stepped: true, shade: "soft", ice: true }) },
  { id: "det-lin", title: "Detuned, linear", text: "The same style as a continuous gradient: the sea floor reads as a landscape of its own, the land as a quiet frame.",
    tags: ["linear", "detuned", "soft shade"], best: "Maps where the sea floor is the subject.",
    s: () => style("detuned", { shade: "soft", ice: true }) },
  { id: "det-lines", title: "Detuned with sea-floor contours", text: "Detuned stepped tints with fine depth contours at 100 m: the sea floor gets the contour language usually kept for land.",
    tags: ["stepped", "detuned", "contours"], best: "Showpiece maps of the shelf and the trench.",
    s: () => style("detuned", { stepped: true, shade: "soft", contours: "lines", landInt: 1e6, seaInt: 100, lineK: 0.3, ice: true }) },
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
    R.draw(cv, cmpSrc[CMP[i][0]], style("bathy", { shade: "soft", shadeK: 0.2, seaShadeK: 0.8, exag: 3 })); });
}
let cmpReady = false;
new IntersectionObserver(([e]) => { if (e.isIntersecting && !cmpReady) { cmpReady = true; drawCompare(); } }, { rootMargin: "50% 0px" }).observe(cmpEl);

// ---------------------------------------------------------------- playground
const play = { palette: "relief", stepped: "0", shade: "soft", contours: "none", zoom: "all" };
const ZOOM = {  // view rectangles in texture uv (x0, y0, x1, y1; y runs south)
  all: [0, 0, 1, 1],
  bergen: [0.18, 0.42, 0.44, 0.62],
  folgefonna: [0.48, 0.62, 0.74, 0.82],
  sogn: [0.30, 0.10, 0.80, 0.42],
};
const pc = document.getElementById("play"), stat = document.getElementById("stat");
const ctl = document.getElementById("ctl");
ctl.querySelectorAll(".seg").forEach((seg) => seg.addEventListener("click", (e) => { if (!e.target.dataset.v) return; play[seg.dataset.k] = e.target.dataset.v; drawPlay(); }));
["az", "alt", "exag", "ice", "coast", "climate"].forEach((id) => document.getElementById(id).addEventListener("input", () => drawPlay()));
let pending = false;
function drawPlay() {
  if (pending) return; pending = true;
  requestAnimationFrame(() => {
    pending = false;
    ctl.querySelectorAll(".seg").forEach((seg) => seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === play[seg.dataset.k])));
    const v = ZOOM[play.zoom], aspect = ((v[3] - v[1]) * meta.size[1]) / ((v[2] - v[0]) * meta.size[0]);
    sizeTo(pc, aspect); pc.style.aspectRatio = `${1 / aspect}`;
    const pst = style(play.palette, {
      stepped: play.stepped === "1", shade: play.shade, contours: play.contours, ice: document.getElementById("ice").checked, coast: document.getElementById("coast").checked,
      climate: document.getElementById("climate").checked,
      az: +document.getElementById("az").value, alt: +document.getElementById("alt").value, exag: +document.getElementById("exag").value,
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
const nlStyle = (opts = {}) => style("relief", { stepped: true, climate: false, ice: true, ...opts });

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

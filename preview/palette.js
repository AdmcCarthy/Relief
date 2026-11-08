// Shared palette code: class breaks, cross-blended hypsometric tints by climate zone, the Detuned style and
// colour bars. Used by the region examples (regions.js) and the techniques page (demo.js).

// Non-linear steps (metres). Sea is finest near the coast, where most of the sea-floor shape is; land is coarser.
export const LB = [0, 50, 150, 300, 600, 1000, 1500, 2000];
export const SB = [0, 20, 50, 100, 200, 500, 1000];
export const LMAX = 2000, SMAX = 1300;
export const at = (breaks, cols, max) => breaks.map((b, i) => [b / max, cols[i]]).concat(cols.length > breaks.length ? [[1, cols.at(-1)]] : []);

// Cross-blended hypsometric tints (Patterson & Jenny): one land ramp per climate zone below 1,000 m and a shared
// alpine ramp above. ZPAL is the full-strength "relief" set; every other style is derived from it by detuning.
export const ZPAL = {
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
// "Detuned": the sea floor gets more room than the land (wider range, deeper indigo) while land is held back.
export const DETUNED_SEA = {
  light: ["#e8f0f2", "#cfe1e6", "#aacdd8", "#7eb0c5", "#5891ae", "#3a6d94", "#264b73", "#162b50"],
  dark: ["#3a8aa2", "#2f7690", "#25647d", "#1c526b", "#144157", "#0e3045", "#092336", "#06172a"],
};
// Ocean ramp for basins and the world (scripts/depth_ramp.py designs and checks it in OKLCH): the shelf ramp above uses
// up all its lightness by 1,300 m, so 76 % of the world's ocean floor (2,000 to 6,000 m, where spreading ridges, flanks,
// fracture zones and abyssal plains lie) is one colour. This one spreads a steady lightness step over 7,000 m.
export const OCEAN_SB = [0, 200, 1000, 2000, 3000, 4000, 5000, 6000, 7000], OCEAN_MAX = 7000;
export const DETUNED_OCEAN = {
  light: ["#e2f4f9", "#bfe2ed", "#83bddc", "#5c9acd", "#4579ba", "#355a9f", "#2a3e80", "#1e2763", "#131546"],
  dark: ["#71b7c8", "#56a5bd", "#2c83aa", "#1d679c", "#154b8a", "#113375", "#101e5c", "#0a0b42", "#040027"],
};
export const ZK = ["temperate", "boreal", "tundra", "arid"];

export const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export const hexOf = (v) => "#" + v.map((x) => Math.round(Math.min(255, Math.max(0, x))).toString(16).padStart(2, "0")).join("");
// Detune a colour: scale its saturation towards its own grey, then lift (mix > 0, towards white) or sink (< 0, towards black).
export function tune(h, sat, mix = 0) {
  const c = rgb(h), y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2], t = mix > 0 ? 255 : 0, m = Math.abs(mix);
  return hexOf(c.map((v) => { const g = y + (v - y) * sat; return g + (t - g) * m; }));
}

// The house style, fixed for the region examples: land tints at half strength (stepped classes, one ramp per climate
// zone), the sea floor on its own wide indigo ramp as a LINEAR gradient. No contours, no illumination, no coastline.
// Returned in the shape relief.js draws: `stepped` applies to land, `seaStepped` is false.
export function detunedStyle(theme, bathymetry = "shelf") {
  const dark = theme === "dark", Z = ZPAL[theme], ocean = bathymetry === "ocean";
  const land = Object.fromEntries(ZK.map((k) => [k, at(LB, Z[k].map((c) => tune(c, 0.5, dark ? -0.08 : 0.08)), LMAX)]));
  const sea = ocean ? at(OCEAN_SB, DETUNED_OCEAN[theme], OCEAN_MAX) : at(SB, DETUNED_SEA[theme], SMAX);
  return { land: land.temperate, zones: land, sea, landMax: LMAX, seaMax: ocean ? OCEAN_MAX : SMAX, landStops: LB, seaStops: ocean ? OCEAN_SB : SB,
    seaTicks: ocean ? [0, 1000, 2000, 3000, 4000, 5000, 6000] : [0, 250, 500, 1000],
    stepped: true, seaStepped: false, shade: "none", contours: "none", coast: false, ice: false };
}

// ---------------------------------------------------------------- colour bars
// Same interpolation as the shader's ramp texture, so a bar shows exactly the colours on the map.
export function rampAt(stops, t) {
  t = Math.min(1, Math.max(0, t)); let k = 0;
  while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
  const [t0, c0] = stops[k], [t1, c1] = stops[k + 1], f = Math.min(1, Math.max(0, (t - t0) / (t1 - t0 || 1)));
  const a = rgb(c0), b = rgb(c1);
  return `rgb(${a.map((v, j) => Math.round(v + (b[j] - v) * f)).join(",")})`;
}
export const fmtM = (v) => v.toLocaleString("en-GB");

// One block per class, labelled with its range (stepped), or a continuous gradient (linear).
export function strip(label, stops, max, bands, stepped) {
  if (stepped) {
    const cells = bands.map((lo, i) => {
      const hi = bands[i + 1];
      const mid = hi == null ? lo + (lo - bands[i - 1]) / 2 : (lo + hi) / 2;
      return `<span class="cb-band" style="background:${rampAt(stops, mid / max)}" title="${fmtM(lo)}${hi == null ? "+" : `–${fmtM(hi)}`} m"></span>`;
    }).join("");
    return `<span class="cb-l">${label}</span><div class="cb-steps" style="--n:${bands.length}">${cells}</div>`;
  }
  const grad = Array.from({ length: 24 }, (_, i) => `${rampAt(stops, i / 23)} ${(i / 23 * 100).toFixed(1)}%`).join(",");
  return `<span class="cb-l">${label}</span><div class="cb-lin" style="background:linear-gradient(90deg,${grad})"></div>`;
}
export function axis(max, bands, stepped, ticks) {
  if (stepped) return `<span></span><div class="cb-labs" style="--n:${bands.length}">${bands.map((v, i) => `<span>${fmtM(v)}${i === bands.length - 1 ? "+" : ""}</span>`).join("")}<span></span></div>`;
  const tk = ticks.filter((v) => v / max < 0.85).map((v) => `<span style="left:${(v / max) * 100}%">${fmtM(v)}</span>`).join("");
  return `<span></span><div class="cb-ticks">${tk}<span style="left:100%">${fmtM(max)}+</span></div>`;
}

// Legend for the Detuned style: one stepped height strip per climate zone present, then a linear depth gradient.
export function regionBars(st, share) {
  const present = ZK.filter((k) => k !== "arid" || (share && share.arid > 0.005));
  const names = { temperate: "Temperate", boreal: "Boreal", tundra: "Tundra", arid: "Arid" };
  return `<div class="cbs"><span class="cb-kind">Relief: stepped classes by climate zone, m · Bathymetry: linear, m</span><div class="cbg">` +
    present.map((k) => strip(names[k], st.zones[k], st.landMax, st.landStops, true)).join("") + axis(st.landMax, st.landStops, true, []) +
    strip("Depth", st.sea, st.seaMax, st.seaStops, false) + axis(st.seaMax, st.seaStops, false, st.seaTicks ?? [0, 250, 500, 1000]) + "</div></div>";
}

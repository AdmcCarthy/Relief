// Browser smoke test for the Pages site: runs the gallery and the zoom viewer in headless Chromium (software WebGL 2).
// Not part of pytest (needs Node and Playwright). Usage, from the repo root:
//   mkdir -p /tmp/site/data /tmp/site/regions && cp preview/*.html preview/*.js /tmp/site/ && cp -r data/out/* /tmp/site/data/ \
//     && cp regions/*.json regions/*.geojson /tmp/site/regions/ && (cd /tmp/site && python3 -m http.server 8765 &)
//   NODE_PATH=<dir with node_modules/playwright> node tests/e2e/check_pages.mjs [http://localhost:8765] [shots-dir]
// Exits 1 when a page throws, a request fails (except Vestland's tiles, which do not exist), or the viewer misbehaves.
import { createRequire } from "node:module";
const require = createRequire(process.env.NODE_PATH ? `${process.env.NODE_PATH}/` : import.meta.url);
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://localhost:8765", SHOTS = process.argv[3];
const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const problems = [];
page.on("pageerror", (e) => problems.push("page error: " + e.message));
page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("404")) problems.push("console: " + m.text()); });
page.on("response", (r) => { if (r.status() >= 400 && !r.url().includes("vestland/tiles")) problems.push(`${r.status()} ${r.url()}`); });
const textureBytes = { card: 0, full: 0, cards: 0 };  // what the gallery downloads for its example textures
page.on("response", (r) => { const m = r.url().match(/demo\/(elev_card|elev)\.webp$/); if (!m) return; const n = +(r.headers()["content-length"] || 0); if (m[1] === "elev") textureBytes.full += n; else { textureBytes.card += n; textureBytes.cards++; } });
const shot = (name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png` });
const check = (ok, what) => { console.log(ok ? "ok  " : "FAIL", what); if (!ok) problems.push(what); };
const ready = () => page.waitForFunction(() => window.__relief && window.__relief.ready, null, { timeout: 60000 });

await page.goto(`${BASE}/index.html`, { waitUntil: "networkidle", timeout: 90000 }); await ready();
check(await page.evaluate(() => !!document.createElement("canvas").getContext("webgl2")), "WebGL 2 available");
check(textureBytes.cards >= 5 && textureBytes.card + textureBytes.full < 20e6,
  `gallery loads card-sized textures (${textureBytes.cards} cards, ${((textureBytes.card + textureBytes.full) / 1e6).toFixed(1)} MB in all; full textures would be about 39 MB)`);
const cards = await page.$$eval(".card", (c) => c.map((x) => x.classList.contains("missing")));
check(cards.length === 7 && cards.every((m) => !m), `gallery: 7 region cards, none missing (${cards.length})`);
check((await page.$$eval("#plan tbody tr", (r) => r.length)) === 7, "data plan table has 7 rows");
await shot("gallery");

await page.goto(`${BASE}/explore.html?area=north_sea`, { waitUntil: "networkidle", timeout: 90000 }); await ready();
const info = () => page.$eval("#info", (e) => e.textContent);
const settle = async () => { for (let i = 0; i < 40; i++) { await page.waitForTimeout(250); if (!(await info()).startsWith("Loading")) break; } await page.waitForTimeout(300); };
await settle();
const fit = await info();
const box = await page.$eval("#map", (c) => { const r = c.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
await page.mouse.move(box.x + box.w * 0.58, box.y + box.h * 0.38);
for (let i = 0; i < 14; i++) { await page.mouse.wheel(0, -300); await page.waitForTimeout(100); }
await settle();
const zoomed = await info();
const level = (t) => +t.match(/Level (\d+)/)[1];
check(level(zoomed) > level(fit) && zoomed.includes("150 m"), `zooming in reaches the finest tiles (${fit.slice(0, 22)} -> ${zoomed.slice(0, 40)})`);
check(page.url().includes("m="), "view is kept in the URL");
await shot("explore_zoom");
for (const id of ["norwegian_sea", "barents_sea", "ne_europe", "atlantic", "world"]) {
  await page.click(`#regions button[data-v="${id}"]`); await settle();
  check(/^Level \d+ of \d+ · tiles at/.test(await info()), `${id} opens`);
  await shot(`explore_${id}`);
}
// the sea-floor shading toggle belongs to ocean regions only
await page.click('#regions button[data-v="atlantic"]'); await settle();
check(await page.$eval("#shadeseg", (e) => !e.hidden), "shading toggle shown for the Atlantic (ocean scale)");
await page.click("#shadeon"); await settle();
check((await page.$eval("#shadeon", (e) => e.getAttribute("aria-pressed"))) === "false", "shading can be switched off");
await page.click('#regions button[data-v="north_sea"]'); await settle();
check(await page.$eval("#shadeseg", (e) => e.hidden), "no shading toggle on a shelf region");
await browser.close();
if (problems.length) { console.log("\nProblems:\n - " + problems.join("\n - ")); process.exit(1); }
console.log("\nall checks passed");

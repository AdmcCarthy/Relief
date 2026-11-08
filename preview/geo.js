// Equal Earth (Šavrič, Patterson and Jenny 2019), EPSG:8857, on a sphere of the WGS 84 authalic radius.
const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796, R0 = 6371007.2;

export function equalEarth(lat, lon) {
  const th = Math.asin((Math.sqrt(3) / 2) * Math.sin((lat * Math.PI) / 180)), t2 = th * th, t6 = t2 * t2 * t2, lam = (lon * Math.PI) / 180;
  const x = (R0 * lam * Math.cos(th) * (2 * Math.sqrt(3) / 3)) / (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2));
  const y = R0 * th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2));
  return [x, y];
}

// The edge of the world in projected metres, as a closed ring.
export function equalEarthRing(stepDeg = 2) {
  const ring = [];
  for (let lat = -90; lat <= 90; lat += stepDeg) ring.push(equalEarth(lat, 180));
  for (let lat = 90; lat >= -90; lat -= stepDeg) ring.push(equalEarth(lat, -180));
  return ring;
}

// A canvas Path2D for that ring, given a function from metres to canvas pixels.
export function ringPath(ring, toPx) {
  const path = new Path2D();
  ring.forEach(([x, y], i) => { const [px, py] = toPx(x, y); if (i) path.lineTo(px, py); else path.moveTo(px, py); });
  path.closePath();
  return path;
}

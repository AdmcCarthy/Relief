// Relief renderer: one WebGL2 context draws every technique from a single 16-bit elevation texture
// (height = base + (R*256 + G) * step), then copies the result into the target 2D canvas.
// Techniques are uniforms: colour ramp (linear or stepped), hillshade (none, single light, soft
// multi-directional), illuminated (Tanaka) contours, coastline, glacier white.

const VS = `#version 300 es
in vec2 p; out vec2 uv;
uniform vec4 uView;  // x0, y0, x1, y1 in texture uv (y down)
void main(){ uv = mix(uView.xy, uView.zw, vec2(p.x*0.5+0.5, 0.5-p.y*0.5)); gl_Position = vec4(p,0.,1.); }`;

const FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uElev, uIce, uRamp;
uniform vec2 uTex; uniform float uCell, uBase, uStep;
uniform float uLandMax, uSeaMax;           // ramp ranges, metres
uniform float uLandStops[12], uSeaStops[12]; uniform int uNLand, uNSea;
uniform int uStepped, uShade, uContours, uIceOn, uCoast;
uniform float uAz, uAlt, uExag, uShadeK, uSeaShadeK, uLineK;
uniform float uLandInt, uSeaInt;           // contour intervals, metres
uniform vec3 uIceCol, uIceEdge, uCoastCol, uHi, uLo;
uniform int uDark;
uniform float uTpp;  // texels per screen pixel: > 1 when the map is shown smaller than its data

float hAt(ivec2 t){ t = clamp(t, ivec2(0), ivec2(uTex)-1); vec4 c = texelFetch(uElev, t, 0);
  return uBase + (floor(c.r*255.+.5)*256. + floor(c.g*255.+.5)) * uStep; }
float h(vec2 u){ vec2 q = u*uTex - 0.5; ivec2 i = ivec2(floor(q)); vec2 f = fract(q);
  return mix(mix(hAt(i), hAt(i+ivec2(1,0)), f.x), mix(hAt(i+ivec2(0,1)), hAt(i+ivec2(1,1)), f.x), f.y); }
float hs(vec2 u, vec2 step_){ // 3x3 tent-weighted blur; step_ in uv. A hand-made mip level: features
  float a = 0.; float w = 0.;  // smaller than a screen pixel (skerries, noise) average away instead of speckling
  for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++){ float k = (i==0?2.:1.)*(j==0?2.:1.);
    a += k*h(u + vec2(float(i), float(j))*step_); w += k; }
  return a/w; }
float bandOf(float v, bool land){ // stepped: snap to the middle of the band containing v
  float lo = 0., hi = 0.;
  for (int k = 0; k < 12; k++){ int n = land ? uNLand : uNSea; if (k >= n) break;
    float s = land ? uLandStops[k] : uSeaStops[k]; if (v >= s) { lo = s; hi = (k+1 < n) ? (land ? uLandStops[k+1] : uSeaStops[k+1]) : s + (s-lo+1.); } }
  return (lo + hi) * 0.5; }
vec3 ramp(float z){
  if (z > 0.) { float v = uStepped == 1 ? bandOf(z, true) : z; return texture(uRamp, vec2(clamp(v/uLandMax,0.,1.), 0.25)).rgb; }
  float d = -z; float v = uStepped == 1 ? bandOf(d, false) : d; return texture(uRamp, vec2(clamp(v/uSeaMax,0.,1.), 0.75)).rgb; }
float lightAt(vec3 n, float az, float alt){ vec3 L = vec3(sin(az)*cos(alt), cos(az)*cos(alt), sin(alt)); return max(dot(n, L), 0.); }
void main(){
  vec2 px = 1.0/uTex;
  float m = max(1., uTpp);                          // footprint of one screen pixel, in texels
  float z = m > 1.2 ? hs(uv, px * m * .5) : h(uv);  // generalise by scale: sub-pixel islands fade out
  vec2 d = px * m;                                  // slopes measured over the same footprint: no sparkle
  float dzx = (h(uv+vec2(d.x,0.)) - h(uv-vec2(d.x,0.))) / (2.*uCell*m);
  float dzy = (h(uv-vec2(0.,d.y)) - h(uv+vec2(0.,d.y))) / (2.*uCell*m);   // texture y runs south
  vec3 n = normalize(vec3(-dzx*uExag, -dzy*uExag, 1.));
  vec3 col = ramp(z);
  float sh = 1.;
  if (uShade == 1) { float l = lightAt(n, radians(uAz), radians(uAlt)); float flat_ = sin(radians(uAlt)); sh = l / max(flat_, .2); }
  if (uShade == 2) { // soft: six lights round the compass weighted to the north-west, plus sky light
    float acc = 0., wsum = 0.;
    for (int k = 0; k < 6; k++){ float a = radians(uAz) + float(k)*1.0472; float w = 1. + .8*cos(float(k)*1.0472);
      acc += w*lightAt(n, a, radians(uAlt)); wsum += w; }
    sh = (acc/wsum) / max(sin(radians(uAlt)), .2) * .7 + n.z * .3; }
  float k = z > 0. ? uShadeK : uSeaShadeK;
  if (uShade > 0) col *= mix(1., clamp(sh, 0., 1.6), k);
  if (uContours > 0) {
    float zs = hs(uv, px * max(1.5, m));
    float I = zs > 0. ? uLandInt : uSeaInt; float f = (zs > 0. ? zs : -zs) / I;
    float d = abs(fract(f + .5) - .5) / max(fwidth(f), 1e-5);
    float line = (1. - smoothstep(.6, 1.4, d)) * clamp(1.6 - fwidth(f) * 3.5, 0., 1.);  // fade where lines crowd under ~2 px
    if (uContours == 1) col = mix(col, uLo, line * uLineK);
    else { // Tanaka: edges facing the light are lit, others shaded
      vec2 g = normalize(vec2(dFdx(zs), -dFdy(zs)) + 1e-9); vec2 L = vec2(sin(radians(uAz)), cos(radians(uAz)));
      float t = dot(-g, L) * (zs > 0. ? 1. : -1.);
      col = mix(col, t > 0. ? uHi : uLo, line * uLineK * abs(t)); } }
  if (uIceOn == 1) { float ice = texture(uIce, uv).r; vec3 ic = uIceCol * mix(1., clamp(sh, .75, 1.15), .6);
    col = mix(col, ic, smoothstep(.35, .65, ice));
    float e = 1. - smoothstep(.0, 1.2, abs(ice - .5) / max(fwidth(ice), 1e-4)); col = mix(col, uIceEdge, e * .7); }
  if (uCoast == 1) { float zc = z - .5; float c = 1. - smoothstep(.4, 1.3, abs(zc) / max(fwidth(zc), 1e-4)); col = mix(col, uCoastCol, c * .8); }
  o = vec4(col, 1.);
}`;

export const hex = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16) / 255);

export function createRenderer() {
  const cv = document.createElement("canvas");
  const gl = cv.getContext("webgl2", { preserveDrawingBuffer: true, antialias: false });
  if (!gl) return null;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const prog = gl.createProgram();
  gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
  gl.useProgram(prog);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = (n) => gl.getUniformLocation(prog, n);
  const textures = new Map();
  function tex(key, img, { filter = gl.NEAREST, format = "rgb" } = {}) {
    if (textures.has(key)) return textures.get(key);
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, format === "r" ? gl.R8 : gl.RGB8, format === "r" ? gl.RED : gl.RGB, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    textures.set(key, t); return t;
  }
  function rampTex(land, sea) {  // 256 x 2 colour table built from stop colours
    const W = 256, data = new Uint8Array(W * 2 * 4);
    [land, sea].forEach((stops, row) => { for (let i = 0; i < W; i++) {
      const t = i / (W - 1); let k = 0; while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
      const [t0, c0] = stops[k], [t1, c1] = stops[k + 1], f = Math.min(1, Math.max(0, (t - t0) / (t1 - t0 || 1)));
      const a = hex(c0), b = hex(c1); for (let j = 0; j < 3; j++) data[(row * W + i) * 4 + j] = Math.round((a[j] + (b[j] - a[j]) * f) * 255); data[(row * W + i) * 4 + 3] = 255; } });
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, W, 2, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }
  // draw `style` for `src` = {elev: Image, ice: Image|null, size:[w,h], cell, base, step, view:[x0,y0,x1,y1]} into target 2D canvas
  function draw(target, src, style) {
    const W = target.width, H = target.height;
    cv.width = W; cv.height = H; gl.viewport(0, 0, W, H);
    const t0 = performance.now();
    gl.activeTexture(gl.TEXTURE2);
    const r = rampTex(style.land, style.sea);  // created on unit 2 so it cannot displace the elevation or ice textures
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex(src.key, src.elev)); gl.uniform1i(U("uElev"), 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, src.ice ? tex(src.key + ":ice", src.ice, { filter: gl.LINEAR, format: "r" }) : null); gl.uniform1i(U("uIce"), 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, r); gl.uniform1i(U("uRamp"), 2);
    const view = src.view ?? [0, 0, 1, 1];
    gl.uniform4f(U("uView"), ...view);
    gl.uniform1f(U("uTpp"), ((view[2] - view[0]) * src.size[0]) / W);
    gl.uniform2f(U("uTex"), src.size[0], src.size[1]); gl.uniform1f(U("uCell"), src.cell);
    gl.uniform1f(U("uBase"), src.base); gl.uniform1f(U("uStep"), src.step);
    gl.uniform1f(U("uLandMax"), style.landMax); gl.uniform1f(U("uSeaMax"), style.seaMax);
    const pad = (a) => Array.from({ length: 12 }, (_, i) => a[i] ?? 1e9);
    gl.uniform1fv(U("uLandStops"), pad(style.landStops)); gl.uniform1fv(U("uSeaStops"), pad(style.seaStops));
    gl.uniform1i(U("uNLand"), style.landStops.length); gl.uniform1i(U("uNSea"), style.seaStops.length);
    gl.uniform1i(U("uStepped"), style.stepped ? 1 : 0);
    gl.uniform1i(U("uShade"), { none: 0, single: 1, soft: 2 }[style.shade ?? "none"]);
    gl.uniform1i(U("uContours"), { none: 0, lines: 1, tanaka: 2 }[style.contours ?? "none"]);
    gl.uniform1i(U("uIceOn"), style.ice && src.ice ? 1 : 0); gl.uniform1i(U("uCoast"), style.coast ? 1 : 0);
    gl.uniform1f(U("uAz"), style.az ?? 315); gl.uniform1f(U("uAlt"), style.alt ?? 40); gl.uniform1f(U("uExag"), style.exag ?? 2);
    gl.uniform1f(U("uShadeK"), style.shadeK ?? 0.6); gl.uniform1f(U("uSeaShadeK"), style.seaShadeK ?? 0.4); gl.uniform1f(U("uLineK"), style.lineK ?? 0.6);
    gl.uniform1f(U("uLandInt"), style.landInt ?? 200); gl.uniform1f(U("uSeaInt"), style.seaInt ?? 100);
    gl.uniform3f(U("uIceCol"), ...hex(style.iceCol ?? "#ffffff")); gl.uniform3f(U("uIceEdge"), ...hex(style.iceEdge ?? "#9fb3c2"));
    gl.uniform3f(U("uCoastCol"), ...hex(style.coastCol ?? "#7f8f9a")); gl.uniform3f(U("uHi"), ...hex(style.hi ?? "#ffffff"));
    gl.uniform3f(U("uLo"), ...hex(style.lo ?? "#3c4d5b"));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.deleteTexture(r);
    const ctx = target.getContext("2d"); ctx.drawImage(cv, 0, 0);
    gl.finish();
    return performance.now() - t0;
  }
  return { draw };
}

export function loadImage(url) {
  return new Promise((res, rej) => { const i = new Image(); i.decoding = "async"; i.onload = () => res(i); i.onerror = rej; i.src = url; });
}

// Site data loader: manifest.json + WRRZ binary containers + imagery texture.
// Formats (defined by sim/handlib/bake.py):
//   WRRZ + u32 jsonLen + json + u32 binLen + zlib(RFC1950) payload
//   payload = concatenated section raws in JSON "s" (dict) insertion order.

async function inflate(u8) {
  const ds = new DecompressionStream("deflate");
  const src = new Response(u8.slice().buffer);
  src.body.pipeThrough(ds);
  const ab = await new Response(ds.readable).arrayBuffer();
  return new Uint8Array(ab);
}

async function readContainer(url) {
  const buf = new Uint8Array(await (await fetch(url)).arrayBuffer());
  if (String.fromCharCode(...buf.subarray(0, 4)) !== "WRRZ")
    throw new Error(`bad asset header at ${url}`);
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const jLen = dv.getUint32(4, true);
  const meta = JSON.parse(new TextDecoder().decode(buf.subarray(8, 8 + jLen)));
  const bLen = dv.getUint32(8 + jLen, true);
  const offs = 8 + jLen + 4;
  const bin = buf.subarray(offs, offs + bLen);
  const raw = await inflate(bin);
  const out = { h: meta.h };
  let p = 0;
  for (const key of Object.keys(meta.s)) {
    const n = meta.s[key];
    out[key] = raw.subarray(p, p + n);
    p += n;
  }
  return out;
}

// packed u16 (cm, little endian) -> Float32Array of meters
function u16Meters(u8, n, scaleCm) {
  const u16 = new Uint16Array(u8.buffer ?? u8, u8.byteOffset ?? 0, n);
  const f = new Float32Array(n);
  const k = scaleCm / 100.0;
  for (let i = 0; i < n; i++) f[i] = u16[i] * k;
  return f;
}

export async function loadSite(site) {
  const base = `/static/data/${site}/`;
  const man = await (await fetch(base + "manifest.json")).json();

  const t = await readContainer(base + "terrain.bin");
  const n = man.nx * man.nz;
  const terrain = {
    nx: man.nx, nz: man.nz,
    elevM: u16Meters(t.elev, n, t.h.scales.elev),
    threshM: u16Meters(t.thresh, n, t.h.scales.thresh),
    outM: u16Meters(t.out, n, t.h.scales.out),
    settleU8: new Uint8Array(t.settle.buffer, t.settle.byteOffset, n),
    slopeU8: new Uint8Array(t.slope.buffer, t.slope.byteOffset, 2 * n), // x-block, z-block
    originM: t.h.origin_cm / 100.0,
  };

  const b = await readContainer(base + "buildings.bin");
  const bn = b.h.n;
  const buildings = {
    n: bn,
    a: new Float32Array(b.f.buffer, b.f.byteOffset, bn * 11),
  };

  const rd = await readContainer(base + "roads.bin");
  const roads = { n: rd.h.n, lines: [] };
  let p = 0;
  for (const k of Object.keys(rd.h.lines)) {
    const m = rd.h.lines[k].n;
    roads.lines.push({
      name: rd.h.lines[k].name, class: rd.h.lines[k].class,
      f: new Float32Array(rd.bin.buffer, rd.bin.byteOffset + p, m * 6), m,
    });
    p += m * 6 * 4;
  }

  const rv = await readContainer(base + "rivers.bin");
  const rivers = { n: rv.h.n, lines: [] };
  p = 0;
  for (const k of Object.keys(rv.h.lines)) {
    const m = rv.h.lines[k].n;
    rivers.lines.push({
      name: rv.h.lines[k].name, order: rv.h.lines[k].order,
      f: new Float32Array(rv.bin.buffer, rv.bin.byteOffset + p, m * 6), m,
    });
    p += m * 6 * 4;
  }

  let imageryOk = false;
  try {
    imageryOk = (await fetch(base + "imagery.jpg", { method: "HEAD" })).ok;
  } catch { imageryOk = false; }

  return {
    manifest: man,
    terrain, buildings, roads, rivers,
    imageryUrl: imageryOk ? base + "imagery.jpg" : null,
  };
}

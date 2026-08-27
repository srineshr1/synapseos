#!/usr/bin/env node
/**
 * Multipart-upload SynapseOS ISOs via the Worker admin API (bypasses wrangler 300 MiB limit).
 *
 * Requires ISO_UPLOAD_SECRET (Bearer) matching the Worker secret.
 *
 * Usage:
 *   ISO_UPLOAD_SECRET=... node tools/upload-isos-r2.mjs
 *   ISO_UPLOAD_SECRET=... node tools/upload-isos-r2.mjs path/to/a.iso [more...]
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomBytes } from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const BASE =
  process.env.SYNAPSEOS_UPLOAD_URL ||
  "https://synapseaios.rudraksha-srinesh.workers.dev";
const PART_SIZE = Number(process.env.ISO_PART_SIZE || 32 * 1024 * 1024); // 32 MiB
const CONCURRENCY = Number(process.env.ISO_UPLOAD_CONCURRENCY || 3);

function die(msg) {
  console.error(msg);
  process.exit(1);
}

const secret = process.env.ISO_UPLOAD_SECRET;
if (!secret) die("Set ISO_UPLOAD_SECRET to the Worker secret value.");

function authHeaders(extra = {}) {
  return { Authorization: `Bearer ${secret}`, ...extra };
}

function isoObjectName(filePath) {
  const base = path.basename(filePath).replace(/\.prev$/, "");
  if (!/^synapseos-\d{4}\.\d{2}\.\d{2}-x86_64\.iso$/.test(base)) {
    die(`Not a SynapseOS ISO name: ${filePath}`);
  }
  return base;
}

async function pickLatestThree() {
  const dir = path.join(ROOT, "out");
  const entries = await fsp.readdir(dir);
  const pat = /^synapseos-(\d{4}\.\d{2}\.\d{2})-x86_64\.iso(\.prev)?$/;
  const best = new Map();
  for (const name of entries) {
    const m = name.match(pat);
    if (!m) continue;
    const date = m[1];
    const isPrev = Boolean(m[2]);
    const full = path.join(dir, name);
    const prev = best.get(date);
    if (!prev || (prev.isPrev && !isPrev)) {
      best.set(date, { full, isPrev, date });
    }
  }
  return [...best.values()]
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .slice(0, 3)
    .map((x) => x.full);
}

async function initUpload(name) {
  const res = await fetch(`${BASE}/_admin/iso-upload/init`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) die(`init failed (${res.status}): ${await res.text()}`);
  return res.json();
}

async function uploadPart(key, uploadId, partNumber, buf) {
  const url = new URL(`${BASE}/_admin/iso-upload/part`);
  url.searchParams.set("key", key);
  url.searchParams.set("uploadId", uploadId);
  url.searchParams.set("partNumber", String(partNumber));
  const res = await fetch(url, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/octet-stream" }),
    body: buf,
    duplex: "half",
  });
  if (!res.ok) {
    throw new Error(`part ${partNumber} failed (${res.status}): ${await res.text()}`);
  }
  return res.json();
}

async function completeUpload(key, uploadId, parts) {
  const res = await fetch(`${BASE}/_admin/iso-upload/complete`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ key, uploadId, parts }),
  });
  if (!res.ok) die(`complete failed (${res.status}): ${await res.text()}`);
  return res.json();
}

async function abortUpload(key, uploadId) {
  try {
    await fetch(`${BASE}/_admin/iso-upload/abort`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ key, uploadId }),
    });
  } catch {
    /* best-effort */
  }
}

async function mapPool(items, limit, fn) {
  const results = new Array(items.length);
  let i = 0;
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      results[idx] = await fn(items[idx], idx);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

async function uploadFile(filePath) {
  const name = isoObjectName(filePath);
  const size = (await fsp.stat(filePath)).size;
  const partCount = Math.ceil(size / PART_SIZE);
  console.log(`\n→ ${name} (${(size / 1e9).toFixed(2)} GB, ${partCount} parts of ~${PART_SIZE / 1024 / 1024} MiB)`);

  const { key, uploadId } = await initUpload(name);
  console.log(`  uploadId=${uploadId}`);

  const partIndexes = Array.from({ length: partCount }, (_, i) => i + 1);
  let doneBytes = 0;
  const started = Date.now();

  try {
    const parts = await mapPool(partIndexes, CONCURRENCY, async (partNumber) => {
      const start = (partNumber - 1) * PART_SIZE;
      const end = Math.min(start + PART_SIZE, size);
      const fh = await fsp.open(filePath, "r");
      try {
        const buf = Buffer.alloc(end - start);
        await fh.read(buf, 0, buf.length, start);
        let attempt = 0;
        for (;;) {
          try {
            const uploaded = await uploadPart(key, uploadId, partNumber, buf);
            doneBytes += buf.length;
            const pct = ((doneBytes / size) * 100).toFixed(1);
            const mbps = doneBytes / 1e6 / ((Date.now() - started) / 1000);
            process.stdout.write(
              `\r  progress ${pct}%  ${mbps.toFixed(1)} MB/s  part ${partNumber}/${partCount}   `,
            );
            return { partNumber: uploaded.partNumber, etag: uploaded.etag };
          } catch (err) {
            attempt += 1;
            if (attempt >= 4) throw err;
            await new Promise((r) => setTimeout(r, 1000 * attempt));
          }
        }
      } finally {
        await fh.close();
      }
    });

    process.stdout.write("\n");
    const result = await completeUpload(key, uploadId, parts);
    console.log(`  ✓ complete size=${result.size} etag=${result.etag}`);
    console.log(`  download: ${BASE}/downloads/${name}`);
    return result;
  } catch (err) {
    console.error(`\n  ✗ failed: ${err.message || err}`);
    await abortUpload(key, uploadId);
    throw err;
  }
}

async function main() {
  const files =
    process.argv.length > 2
      ? process.argv.slice(2).map((p) => path.resolve(p))
      : await pickLatestThree();

  if (!files.length) die("No ISOs found under out/");
  console.log(`Uploading ${files.length} ISO(s) to ${BASE}`);
  for (const f of files) {
    if (!fs.existsSync(f)) die(`Missing file: ${f}`);
    await uploadFile(f);
  }
  console.log("\nAll uploads finished.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

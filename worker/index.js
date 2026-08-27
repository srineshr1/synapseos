/**
 * SynapseOS marketing site + ISO downloads from R2.
 *
 * GET  /downloads/<filename.iso>  — stream ISO from R2
 * POST /_admin/iso-upload/init    — start multipart upload (secret-gated)
 * PUT  /_admin/iso-upload/part    — upload one part
 * POST /_admin/iso-upload/complete
 * POST /_admin/iso-upload/abort
 */

const ISO_PREFIX = "isos/";

function isIsoKey(name) {
  return /^synapseos-\d{4}\.\d{2}\.\d{2}-x86_64\.iso$/.test(name);
}

function unauthorized() {
  return new Response("Unauthorized", { status: 401 });
}

function badRequest(msg) {
  return new Response(msg, { status: 400 });
}

function checkUploadAuth(request, env) {
  const secret = env.ISO_UPLOAD_SECRET;
  if (!secret) return false;
  const header = request.headers.get("Authorization") || "";
  return header === `Bearer ${secret}`;
}

async function handleAdminUpload(request, env, url) {
  if (!checkUploadAuth(request, env)) return unauthorized();

  if (url.pathname === "/_admin/iso-upload/init" && request.method === "POST") {
    const body = await request.json();
    const name = body?.name;
    if (!name || !isIsoKey(name)) return badRequest("invalid name");
    const key = `${ISO_PREFIX}${name}`;
    const multipart = await env.ISOS.createMultipartUpload(key, {
      httpMetadata: {
        contentType: "application/octet-stream",
        contentDisposition: `attachment; filename="${name}"`,
      },
      customMetadata: {
        uploadedAt: new Date().toISOString(),
      },
    });
    return Response.json({ key, uploadId: multipart.uploadId });
  }

  if (url.pathname === "/_admin/iso-upload/part" && request.method === "PUT") {
    const key = url.searchParams.get("key");
    const uploadId = url.searchParams.get("uploadId");
    const partNumber = Number(url.searchParams.get("partNumber"));
    if (!key || !key.startsWith(ISO_PREFIX) || !uploadId || !partNumber) {
      return badRequest("key, uploadId, partNumber required");
    }
    const multipart = env.ISOS.resumeMultipartUpload(key, uploadId);
    const uploaded = await multipart.uploadPart(partNumber, request.body);
    return Response.json({ partNumber: uploaded.partNumber, etag: uploaded.etag });
  }

  if (url.pathname === "/_admin/iso-upload/complete" && request.method === "POST") {
    const body = await request.json();
    const { key, uploadId, parts } = body || {};
    if (!key || !key.startsWith(ISO_PREFIX) || !uploadId || !Array.isArray(parts)) {
      return badRequest("key, uploadId, parts required");
    }
    const multipart = env.ISOS.resumeMultipartUpload(key, uploadId);
    const object = await multipart.complete(
      parts
        .map((p) => ({ partNumber: p.partNumber, etag: p.etag }))
        .sort((a, b) => a.partNumber - b.partNumber),
    );
    return Response.json({ key: object.key, size: object.size, etag: object.etag });
  }

  if (url.pathname === "/_admin/iso-upload/abort" && request.method === "POST") {
    const body = await request.json();
    const { key, uploadId } = body || {};
    if (!key || !uploadId) return badRequest("key, uploadId required");
    const multipart = env.ISOS.resumeMultipartUpload(key, uploadId);
    await multipart.abort();
    return Response.json({ aborted: true });
  }

  return new Response("Not Found", { status: 404 });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/_admin/iso-upload")) {
      return handleAdminUpload(request, env, url);
    }

    if (url.pathname === "/downloads" || url.pathname === "/downloads/") {
      return Response.redirect(new URL("/#download", url).toString(), 302);
    }

    if (url.pathname.startsWith("/downloads/")) {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method Not Allowed", { status: 405 });
      }

      const name = decodeURIComponent(url.pathname.slice("/downloads/".length));
      if (!name || name.includes("..") || name.includes("/") || !isIsoKey(name)) {
        return new Response("Not Found", { status: 404 });
      }

      const key = `${ISO_PREFIX}${name}`;
      const object =
        request.method === "HEAD"
          ? await env.ISOS.head(key)
          : await env.ISOS.get(key, {
              range: request.headers,
              onlyIf: request.headers,
            });

      if (object === null) {
        return new Response("ISO not found", { status: 404 });
      }

      const headers = new Headers();
      object.writeHttpMetadata(headers);
      headers.set("etag", object.httpEtag);
      headers.set("Accept-Ranges", "bytes");
      headers.set("Content-Disposition", `attachment; filename="${name}"`);
      if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/octet-stream");
      }
      headers.set("Cache-Control", "public, max-age=3600");
      if (object.size != null) {
        headers.set("Content-Length", String(object.size));
      }

      if (request.method === "HEAD") {
        return new Response(null, { status: 200, headers });
      }

      const status = object.range != null ? 206 : 200;
      return new Response(object.body, { status, headers });
    }

    return env.ASSETS.fetch(request);
  },
};

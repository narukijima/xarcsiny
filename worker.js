// xarcsiny.com: static files, one canonical host, and byte ranges for audio so every browser can seek.
const RANGE = /^bytes=(\d*)-(\d*)$/;

async function audio(request, env) {
  const res = await env.ASSETS.fetch(new Request(request.url, { headers: { accept: "*/*" } }));
  if (!res.ok) return res;
  const headers = new Headers(res.headers);
  headers.set("Accept-Ranges", "bytes");
  const match = RANGE.exec(request.headers.get("range") || "");
  if (!match || (!match[1] && !match[2])) return new Response(res.body, { status: 200, headers });
  const body = await res.arrayBuffer();
  const size = body.byteLength;
  const start = match[1] ? Number(match[1]) : Math.max(0, size - Number(match[2]));
  const end = match[1] && match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
  if (start >= size || start > end) {
    headers.set("Content-Range", `bytes */${size}`);
    return new Response(null, { status: 416, headers });
  }
  headers.set("Content-Range", `bytes ${start}-${end}/${size}`);
  headers.set("Content-Length", String(end - start + 1));
  return new Response(body.slice(start, end + 1), { status: 206, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.xarcsiny.com") {
      url.hostname = "xarcsiny.com";
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/ja" || url.pathname.startsWith("/ja/")) {
      url.pathname = url.pathname.slice(3) || "/";
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname.startsWith("/audio/") && request.method === "GET") return audio(request, env);
    return env.ASSETS.fetch(request);
  },
};

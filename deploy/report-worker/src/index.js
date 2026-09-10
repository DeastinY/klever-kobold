// A mailbox for wrong-answer reports. Anyone running pf2e serve can POST one;
// reading them back needs the admin key. Nothing else.
//
//   POST /report          JSON body, see LIMITS for the fields  -> {ok, id}
//   GET  /reports?key=…   the newest 200 as JSON                 -> [{…}]
//   GET  /reports.md?key=… the same as Markdown, one section per report
//   GET  /                a one-line health check
//
// Rate limit: 20 reports per IP per day, on a hash of the IP.

const LIMITS = { question: 2000, answer: 8000, correction: 8000, source_url: 500,
                 sources: 4000, model: 100, index_tag: 100, app: 100 };
const CORS = { "Access-Control-Allow-Origin": "*",
               "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
               "Access-Control-Allow-Headers": "Content-Type" };

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...CORS } });

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function clean(body) {
  const out = {};
  for (const [field, max] of Object.entries(LIMITS)) {
    let v = body[field];
    if (field === "sources" && Array.isArray(v)) v = JSON.stringify(v.slice(0, 24));
    if (v === undefined || v === null) continue;
    if (typeof v !== "string") return null;
    out[field] = v.slice(0, max);
  }
  return out;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });

    if (request.method === "POST" && url.pathname === "/report") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "JSON body required" }, 400); }
      const r = clean(body);
      if (!r || !r.question || !r.answer || !r.correction)
        return json({ error: "question, answer and correction are required" }, 400);
      const ip = request.headers.get("CF-Connecting-IP") || "";
      const ipHash = await sha256(ip + (env.SALT || ""));
      const { count } = await env.DB.prepare(
        "SELECT COUNT(*) AS count FROM reports WHERE ip_hash = ? AND received_at > datetime('now', '-1 day')"
      ).bind(ipHash).first();
      if (count >= 20) return json({ error: "that is plenty for one day; thank you" }, 429);
      const res = await env.DB.prepare(
        `INSERT INTO reports (question, answer, correction, source_url, sources, model, index_tag, app, ip_hash)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(r.question, r.answer, r.correction, r.source_url || null, r.sources || null,
             r.model || null, r.index_tag || null, r.app || null, ipHash).run();
      return json({ ok: true, id: res.meta.last_row_id });
    }

    if (request.method === "GET" && (url.pathname === "/reports" || url.pathname === "/reports.md")) {
      if (!env.ADMIN_KEY || url.searchParams.get("key") !== env.ADMIN_KEY)
        return json({ error: "admin key required" }, 401);
      const { results } = await env.DB.prepare(
        "SELECT id, received_at, question, answer, correction, source_url, sources, model, index_tag, app FROM reports ORDER BY id DESC LIMIT 200"
      ).all();
      if (url.pathname === "/reports") return json(results);
      const md = results.map(r =>
        `## #${r.id} · ${r.received_at} · ${r.model || "?"} · ${r.index_tag || "?"}\n\n` +
        `**Q:** ${r.question}\n\n**Answer given:**\n\n${r.answer}\n\n**Correction:**\n\n${r.correction}\n\n` +
        (r.source_url ? `Source: ${r.source_url}\n\n` : "") +
        (r.sources ? `Retrieved: ${JSON.parse(r.sources).map(s => s.name).join(", ")}\n\n` : "")
      ).join("\n---\n\n");
      return new Response(md, { headers: { "Content-Type": "text/markdown; charset=utf-8", ...CORS } });
    }

    if (request.method === "GET" && url.pathname === "/")
      return new Response("pf2e report mailbox: POST /report", { headers: CORS });
    return json({ error: "not found" }, 404);
  }
};

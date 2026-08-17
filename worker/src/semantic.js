const EMBEDDING_MODEL = "@cf/qwen/qwen3-embedding-0.6b";
const DEFAULT_TOP_K = 100;
const MAX_TOP_K = 500;

function json(body, status = 200) {
  return Response.json(body, {
    status,
    headers: { "cache-control": "no-store", "x-content-type-options": "nosniff" },
  });
}

function clampTopK(value) {
  const n = Number(value || DEFAULT_TOP_K);
  return Math.max(1, Math.min(MAX_TOP_K, Number.isFinite(n) ? Math.floor(n) : DEFAULT_TOP_K));
}

function vectorId(value) {
  return String(value || "").slice(0, 64);
}

export async function handleSemantic(request, env, pathname) {
  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  if (!env.AI || !env.OPPORTUNITY_VECTORS) return json({ error: "semantic_unavailable" }, 503);

  let body;
  try { body = await request.json(); } catch { return json({ error: "invalid_json" }, 400); }

  if (pathname.endsWith("/query")) {
    const text = String(body.text || "").trim();
    if (!text) return json({ error: "missing_text" }, 400);
    const embedding = await env.AI.run(EMBEDDING_MODEL, { text: [text] });
    const vector = embedding?.data?.[0];
    if (!Array.isArray(vector)) return json({ error: "embedding_failed" }, 502);
    const result = await env.OPPORTUNITY_VECTORS.query(vector, {
      topK: clampTopK(body.topK),
      returnMetadata: "all",
    });
    return json({ model: EMBEDDING_MODEL, matches: result.matches || [] });
  }

  if (pathname.endsWith("/upsert")) {
    const documents = Array.isArray(body.documents) ? body.documents.slice(0, 100) : [];
    if (!documents.length) return json({ error: "missing_documents" }, 400);
    const texts = documents.map((doc) => String(doc.text || "").trim());
    if (texts.some((text) => !text)) return json({ error: "missing_document_text" }, 400);
    const embedding = await env.AI.run(EMBEDDING_MODEL, { text: texts });
    const vectors = embedding?.data;
    if (!Array.isArray(vectors) || vectors.length !== documents.length) return json({ error: "embedding_failed" }, 502);
    const mutation = await env.OPPORTUNITY_VECTORS.upsert(documents.map((doc, index) => ({
      id: vectorId(doc.id),
      values: vectors[index],
      namespace: doc.namespace ? String(doc.namespace) : undefined,
      metadata: {
        event_id: String(doc.id || ""),
        source: String(doc.source || ""),
        kind: String(doc.kind || ""),
        profile: String(doc.profile || ""),
        content_hash: String(doc.content_hash || ""),
      },
    })));
    return json({ model: EMBEDDING_MODEL, count: documents.length, mutation });
  }

  return json({ error: "not_found" }, 404);
}

import { handleSemantic } from "./semantic.js";

const DATA_PREFIX = "/data/outputs/current/";
const SEMANTIC_PREFIX = "/internal/semantic/";
const ALLOWED = new Set([
  "daily_activity.json",
  "packages.json",
  "standalone.json",
  "fr_metrics.json",
  "marc_horizon.json",
  "health.json",
  "brief.json",
  "opportunities_today.json",
  "hidden_gems.json",
]);

function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": status === 200 ? "public, max-age=30, stale-while-revalidate=120" : "no-store",
      "x-content-type-options": "nosniff",
      ...extraHeaders,
    },
  });
}

async function legacyFallback(env, name, pointer) {
  const legacy = await env.DASHBOARD_DATA.get(name);
  if (legacy === null) return null;
  return jsonResponse(legacy, 200, {
    "x-fedpulse-generation": "legacy-fallback",
    "x-fedpulse-pointer-generation": pointer?.generation || "none",
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // Semantic mutation/query HTTP is intentionally dark by default. Production
    // indexing uses authenticated Cloudflare API/Actions paths; an HTTP surface
    // may be enabled later only behind explicit service authentication.
    if (url.pathname.startsWith(SEMANTIC_PREFIX)) {
      if (env.SEMANTIC_HTTP_ENABLED === "1") return handleSemantic(request, env, url.pathname);
      return jsonResponse(JSON.stringify({ error: "not_found" }), 404);
    }
    if (!url.pathname.startsWith(DATA_PREFIX)) {
      return env.ASSETS.fetch(request);
    }

    const name = url.pathname.slice(DATA_PREFIX.length);
    if (!ALLOWED.has(name)) {
      return jsonResponse(JSON.stringify({ error: "not_found" }), 404);
    }

    const pointer = await env.DASHBOARD_DATA.get("current.json", { type: "json" });
    if (pointer?.generation) {
      const key = `generation/${pointer.generation}/${name}`;
      const value = await env.DASHBOARD_DATA.get(key);
      if (value !== null) {
        return jsonResponse(value, 200, { "x-fedpulse-generation": pointer.generation });
      }

      const declared = Boolean(pointer?.files && Object.prototype.hasOwnProperty.call(pointer.files, name));
      if (!declared) {
        // A static dashboard release can briefly lead the data schema. During that
        // transition only, an older flat key is an acceptable compatibility source.
        const fallback = await legacyFallback(env, name, pointer);
        if (fallback) return fallback;
      }

      // If the manifest says the object exists but KV cannot read it, the generation
      // is genuinely incomplete. Never hide that corruption behind stale data.
      console.error(JSON.stringify({ event: "missing_generation_object", generation: pointer.generation, name, declared }));
      return jsonResponse(JSON.stringify({ error: "incomplete_generation", generation: pointer.generation, name }), 503);
    }

    const fallback = await legacyFallback(env, name, pointer);
    if (fallback) return fallback;
    return jsonResponse(JSON.stringify({ error: "snapshot_unavailable" }), 503);
  },
};

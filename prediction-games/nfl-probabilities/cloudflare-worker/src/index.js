/**
 * NFL Probabilities — Cloudflare Worker proxy
 *
 * Holds Apps Script URL + token as secrets. The browser only sees this Worker.
 *
 * Routes:
 *   GET  /games         → latest week matchups
 *   POST /predictions   → save username forecasts
 */

export default {
  async fetch(request, env) {
    // Public API with no cookies — allow any origin (file://, local servers, production).
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (!env.APPS_SCRIPT_URL || !env.APPS_SCRIPT_TOKEN) {
      return json_(
        { error: "Worker secrets are not configured" },
        500,
        corsHeaders
      );
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (request.method === "GET" && (path === "/games" || path === "/")) {
        return await proxyGames_(env, corsHeaders, request);
      }

      if (request.method === "GET" && path === "/user-predictions") {
        return await proxyUserPredictions_(env, corsHeaders, request);
      }

      if (request.method === "GET" && path === "/others") {
        return await proxyOthers_(env, corsHeaders, request);
      }

      if (request.method === "POST" && path === "/predictions") {
        return await proxyPredictions_(request, env, corsHeaders);
      }

      return json_({ error: "Not found" }, 404, corsHeaders);
    } catch (err) {
      return json_(
        { error: err.message || "Proxy request failed" },
        502,
        corsHeaders
      );
    }
  },
};

async function proxyGames_(env, corsHeaders, request) {
  const incoming = new URL(request.url);
  const user = incoming.searchParams.get("user") || "";

  const target =
    env.APPS_SCRIPT_URL +
    "?token=" +
    encodeURIComponent(env.APPS_SCRIPT_TOKEN) +
    "&action=games" +
    (user ? "&user=" + encodeURIComponent(user) : "");

  const response = await fetch(target, {
    method: "GET",
    redirect: "follow",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.ok ? 200 : response.status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

async function proxyUserPredictions_(env, corsHeaders, request) {
  const incoming = new URL(request.url);
  const user = incoming.searchParams.get("user") || "";
  const week = incoming.searchParams.get("week") || "";

  const target =
    env.APPS_SCRIPT_URL +
    "?token=" +
    encodeURIComponent(env.APPS_SCRIPT_TOKEN) +
    "&action=userpredictions" +
    "&user=" +
    encodeURIComponent(user) +
    "&week=" +
    encodeURIComponent(week);

  const response = await fetch(target, {
    method: "GET",
    redirect: "follow",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.ok ? 200 : response.status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

async function proxyOthers_(env, corsHeaders, request) {
  const incoming = new URL(request.url);
  const week = incoming.searchParams.get("week") || "";

  const target =
    env.APPS_SCRIPT_URL +
    "?token=" +
    encodeURIComponent(env.APPS_SCRIPT_TOKEN) +
    "&action=others" +
    (week ? "&week=" + encodeURIComponent(week) : "");

  const response = await fetch(target, {
    method: "GET",
    redirect: "follow",
  });

  const text = await response.text();
  return new Response(text, {
    status: response.ok ? 200 : response.status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

async function proxyPredictions_(request, env, corsHeaders) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json_({ error: "Invalid JSON body" }, 400, corsHeaders);
  }

  const target =
    env.APPS_SCRIPT_URL +
    "?token=" +
    encodeURIComponent(env.APPS_SCRIPT_TOKEN);

  const response = await fetch(target, {
    method: "POST",
    redirect: "follow",
    headers: { "Content-Type": "text/plain;charset=utf-8" },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  return new Response(text, {
    status: response.ok ? 200 : response.status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function json_(obj, status, corsHeaders) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

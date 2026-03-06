async function supabaseFetch(env, path, { params = {}, method = "GET", body = null, useServiceRole = false } = {}) {
  const key = useServiceRole ? env.SUPABASE_SERVICE_ROLE_KEY : env.SUPABASE_ANON_KEY;
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };
  if (method !== "GET") headers["Prefer"] = "return=representation";
  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, data };
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const adminMode = url.searchParams.get("admin") === "1";
  const providedKey = request.headers.get("X-Notice-Admin-Key") || "";
  const isAdmin = adminMode && providedKey === env.NOTICE_ADMIN_KEY;

  const params = {
    select: "id,title,body,author,is_published,created_at,updated_at",
    order: "created_at.desc,id.desc",
  };
  if (!isAdmin) params["is_published"] = "eq.true";

  const { ok, data } = await supabaseFetch(env, "notices", { params });
  if (!ok || !Array.isArray(data)) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  const items = data.map((r) => ({
    notice_id: r.id,
    title: r.title || "",
    body: r.body || "",
    author: r.author || "관리자",
    is_published: r.is_published ? 1 : 0,
    created_at: r.created_at || "",
    updated_at: r.updated_at || "",
  }));

  return Response.json({ count: items.length, items, admin_mode: isAdmin });
}

export async function onRequestPost({ request, env }) {
  const providedKey = request.headers.get("X-Notice-Admin-Key") || "";
  if (!env.NOTICE_ADMIN_KEY) {
    return Response.json({ error: "notice admin key is not configured" }, { status: 503 });
  }
  if (providedKey !== env.NOTICE_ADMIN_KEY) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const title = String(payload.title || "").trim();
  const body = String(payload.body || "").trim();
  const author = String(payload.author || "관리자").trim() || "관리자";
  const isPublished = Boolean(payload.is_published);
  const noticeId = payload.notice_id ? parseInt(payload.notice_id, 10) : null;

  if (!title || !body) {
    return Response.json({ error: "title/body required" }, { status: 400 });
  }

  const now = new Date().toISOString();

  if (noticeId) {
    const { ok, data } = await supabaseFetch(env, `notices?id=eq.${noticeId}`, {
      method: "PATCH",
      body: { title, body, author, is_published: isPublished, updated_at: now },
      useServiceRole: true,
    });
    if (!ok) return Response.json({ error: "update failed" }, { status: 502 });
    const item = Array.isArray(data) ? data[0] : data;
    return Response.json({ ok: true, item: { notice_id: item?.id || noticeId, title, body, author, is_published: isPublished ? 1 : 0 } });
  } else {
    const { ok, data } = await supabaseFetch(env, "notices", {
      method: "POST",
      body: { title, body, author, is_published: isPublished, created_at: now, updated_at: now },
      useServiceRole: true,
    });
    if (!ok) return Response.json({ error: "insert failed" }, { status: 502 });
    const item = Array.isArray(data) ? data[0] : data;
    return Response.json({ ok: true, item: { notice_id: item?.id, title, body, author, is_published: isPublished ? 1 : 0 } });
  }
}

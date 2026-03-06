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

// POST /api/inquiry/replies
export async function onRequestPost({ request, env }) {
  const adminKeyHeader = request.headers.get("X-Inquiry-Admin-Key") || "";
  const isAdmin = Boolean(env.INQUIRY_ADMIN_KEY) && adminKeyHeader === env.INQUIRY_ADMIN_KEY;

  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const inquiryId = parseInt(payload.inquiry_id, 10);
  const nickname = String(payload.nickname || "").trim().slice(0, 40);
  const body = String(payload.body || "").trim().slice(0, 3000);

  if (!inquiryId || isNaN(inquiryId) || !nickname || !body) {
    return Response.json({ error: "inquiry_id, 닉네임, 내용은 필수입니다." }, { status: 400 });
  }

  // Verify inquiry exists
  const { ok: checkOk, data: checkData } = await supabaseFetch(env, "inquiries", {
    params: { select: "id", id: `eq.${inquiryId}` },
  });
  if (!checkOk || !Array.isArray(checkData) || checkData.length === 0) {
    return Response.json({ error: "문의글을 찾을 수 없습니다." }, { status: 404 });
  }

  const now = new Date().toISOString();
  const { ok, data } = await supabaseFetch(env, "inquiry_replies", {
    method: "POST",
    body: { inquiry_id: inquiryId, is_admin: isAdmin, nickname, body, created_at: now },
    useServiceRole: isAdmin,
  });

  if (!ok) return Response.json({ error: "답변 등록에 실패했습니다." }, { status: 502 });

  // Mark inquiry as closed if admin replied
  if (isAdmin) {
    await supabaseFetch(env, `inquiries?id=eq.${inquiryId}`, {
      method: "PATCH",
      body: { is_closed: true, updated_at: now },
      useServiceRole: true,
    });
  }

  const item = Array.isArray(data) ? data[0] : data;
  return Response.json({ ok: true, item: { id: item?.id, is_admin: isAdmin, nickname, body } });
}

const SUBJECTS = new Set([
  "", "재정학", "세법학개론", "회계학개론", "상법", "민법",
  "행정소송법", "국세기본법", "국세징수법", "소득세법",
  "법인세법", "부가가치세법", "조세범처벌법",
]);

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

// GET /api/inquiry/posts?limit=60
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const limit = Math.min(100, Math.max(1, parseInt(url.searchParams.get("limit") || "60", 10))) || 60;

  const { ok: postsOk, data: posts } = await supabaseFetch(env, "inquiries", {
    params: {
      select: "id,nickname,title,body,subject,year,question_no,is_closed,created_at,updated_at",
      order: "created_at.desc,id.desc",
      limit: String(limit),
    },
  });

  if (!postsOk || !Array.isArray(posts)) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  if (posts.length === 0) {
    return Response.json({ count: 0, items: [] });
  }

  const postIds = posts.map((p) => p.id).join(",");
  const { ok: repliesOk, data: replies } = await supabaseFetch(env, "inquiry_replies", {
    params: {
      select: "id,inquiry_id,is_admin,nickname,body,created_at",
      inquiry_id: `in.(${postIds})`,
      order: "created_at.asc,id.asc",
    },
  });

  const replyMap = {};
  if (repliesOk && Array.isArray(replies)) {
    for (const r of replies) {
      const pid = r.inquiry_id;
      if (!replyMap[pid]) replyMap[pid] = [];
      replyMap[pid].push({
        id: r.id,
        is_admin: Boolean(r.is_admin),
        nickname: r.nickname || "",
        body: r.body || "",
        created_at: r.created_at || "",
        updated_at: r.created_at || "",
      });
    }
  }

  const items = posts.map((p) => ({
    id: p.id,
    nickname: p.nickname || "",
    title: p.title || "",
    body: p.body || "",
    subject: p.subject || "",
    year: p.year || 0,
    question_no: p.question_no || 0,
    is_closed: Boolean(p.is_closed),
    created_at: p.created_at || "",
    updated_at: p.updated_at || "",
    answers: replyMap[p.id] || [],
  }));

  return Response.json({ count: items.length, items });
}

// POST /api/inquiry/posts
export async function onRequestPost({ request, env }) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const nickname = String(payload.nickname || "").trim().slice(0, 40);
  const title = String(payload.title || "").trim().slice(0, 160);
  const body = String(payload.body || "").trim().slice(0, 3000);
  const subject = String(payload.subject || "").trim();
  const year = parseInt(payload.year || 0, 10) || 0;
  const questionNo = parseInt(payload.question_no || 0, 10) || 0;

  if (!nickname || !title || !body) {
    return Response.json({ error: "닉네임, 제목, 내용은 필수입니다." }, { status: 400 });
  }
  if (subject && !SUBJECTS.has(subject)) {
    return Response.json({ error: "invalid subject" }, { status: 400 });
  }

  const now = new Date().toISOString();
  const { ok, data } = await supabaseFetch(env, "inquiries", {
    method: "POST",
    body: { nickname, title, body, subject, year, question_no: questionNo, created_at: now, updated_at: now },
  });

  if (!ok) return Response.json({ error: "등록에 실패했습니다." }, { status: 502 });
  const item = Array.isArray(data) ? data[0] : data;
  return Response.json({ ok: true, id: item?.id });
}

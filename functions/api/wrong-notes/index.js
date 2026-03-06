const SUBJECTS = new Set([
  "재정학", "세법학개론", "회계학개론", "상법", "민법",
  "행정소송법", "국세기본법", "국세징수법", "소득세법",
  "법인세법", "부가가치세법", "조세범처벌법",
]);
const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);

function normalizeUserId(value) {
  const v = String(value || "").trim();
  return v ? v.slice(0, 64) : "guest";
}

async function supabaseFetch(env, path, { params = {}, method = "GET", body = null } = {}) {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const headers = {
    apikey: env.SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
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

// GET /api/wrong-notes?user_id=&source=&subject=&importance=&comment=
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const userId = normalizeUserId(url.searchParams.get("user_id"));
  const source = url.searchParams.get("source")?.trim().toLowerCase() || "";
  const subject = url.searchParams.get("subject") || "";
  const importance = url.searchParams.get("importance")?.toLowerCase() || "";
  const comment = url.searchParams.get("comment") || "";

  if (source && source !== "question" && source !== "ox") {
    return Response.json({ error: "invalid source" }, { status: 400 });
  }
  if (subject && !SUBJECTS.has(subject)) {
    return Response.json({ error: "invalid subject" }, { status: 400 });
  }
  if (importance && !IMPORTANCE_LEVELS.has(importance)) {
    return Response.json({ error: "invalid importance" }, { status: 400 });
  }

  const params = {
    select: "year,subject,question_no,importance,comment,updated_at,source",
    "user_id": `eq.${userId}`,
    order: "updated_at.desc,year.desc,subject.asc,question_no.asc",
  };
  if (source) params["source"] = `eq.${source}`;
  if (subject) params["subject"] = `eq.${subject}`;
  if (importance) params["importance"] = `eq.${importance}`;
  if (comment) params["comment"] = `like.*${comment}*`;

  const { ok, data } = await supabaseFetch(env, "user_notes", { params });
  if (!ok || !Array.isArray(data)) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  const items = data.map((r) => ({
    year: r.year,
    subject: r.subject,
    question_no: r.question_no,
    source: r.source || "question",
    importance: r.importance || "",
    comment: r.comment || "",
    updated_at: r.updated_at || "",
    question_preview: "",
    answer: "",
    explanation: "",
  }));

  return Response.json({ user_id: userId, count: items.length, items });
}

// POST /api/wrong-notes
export async function onRequestPost({ request, env }) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }

  const userId = normalizeUserId(String(payload.user_id || ""));
  const source = (String(payload.source || "question")).trim().toLowerCase();
  const normalizedSource = source === "ox" ? "ox" : "question";
  const subject = String(payload.subject || "").trim();
  const importance = String(payload.importance || "").trim().toLowerCase();
  const comment = String(payload.comment || "").trim();
  const year = parseInt(payload.year, 10);
  const questionNo = parseInt(payload.question_no, 10);

  if (!year || isNaN(year) || isNaN(questionNo)) {
    return Response.json({ error: "invalid year/question_no" }, { status: 400 });
  }
  if (!SUBJECTS.has(subject)) {
    return Response.json({ error: "invalid subject" }, { status: 400 });
  }

  const normalizedImportance = IMPORTANCE_LEVELS.has(importance) ? importance : "";
  const now = new Date().toISOString();

  // Delete if both importance and comment are empty
  if (!normalizedImportance && !comment) {
    await supabaseFetch(env, `user_notes?user_id=eq.${userId}&source=eq.${normalizedSource}&year=eq.${year}&subject=eq.${encodeURIComponent(subject)}&question_no=eq.${questionNo}`, {
      method: "DELETE",
    });
    return Response.json({ ok: true, user_id: userId });
  }

  // Upsert
  const { ok } = await supabaseFetch(env, "user_notes?on_conflict=user_id,source,year,subject,question_no", {
    method: "POST",
    body: {
      user_id: userId,
      source: normalizedSource,
      year,
      subject,
      question_no: questionNo,
      importance: normalizedImportance,
      comment,
      updated_at: now,
    },
    params: {},
  });

  if (!ok) return Response.json({ error: "database error" }, { status: 502 });
  return Response.json({ ok: true, user_id: userId });
}

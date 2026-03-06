const SUBJECTS = new Set([
  "재정학", "세법학개론", "회계학개론", "상법", "민법",
  "행정소송법", "국세기본법", "국세징수법", "소득세법",
  "법인세법", "부가가치세법", "조세범처벌법",
]);

async function querySupabase(env, path, params = {}) {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/${path}`);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const res = await fetch(url.toString(), {
    headers: {
      apikey: env.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${env.SUPABASE_ANON_KEY}`,
    },
  });
  if (!res.ok) return null;
  return res.json();
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const yearText = url.searchParams.get("year") || "";
  const subject = url.searchParams.get("subject") || "";
  const year = parseInt(yearText, 10);

  if (!year || isNaN(year)) {
    return Response.json({ error: "invalid year" }, { status: 400 });
  }
  if (!SUBJECTS.has(subject)) {
    return Response.json({ error: "invalid subject" }, { status: 400 });
  }

  const rows = await querySupabase(env, "questions", {
    select: "original_no,stem,stem_html,options,options_html,answer,distributed_answer,explanation",
    year: `eq.${year}`,
    subject: `eq.${subject}`,
    order: "original_no.asc",
  });

  if (!rows) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  const questions = rows.map((r) => ({
    original_no: r.original_no,
    stem: r.stem || "",
    stem_html: r.stem_html || "",
    options: Array.isArray(r.options) ? r.options : [],
    options_html: Array.isArray(r.options_html) ? r.options_html : [],
    answer: r.answer || "",
    distributed_answer: r.distributed_answer || "",
    explanation: r.explanation || "",
  }));

  return Response.json({ year, subject, count: questions.length, questions });
}

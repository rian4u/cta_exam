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
  const yearText = url.searchParams.get("year") || "2025";
  const subject = url.searchParams.get("subject") || "재정학";
  const year = parseInt(yearText, 10);

  if (!year || isNaN(year)) {
    return Response.json({ error: "invalid year" }, { status: 400 });
  }

  const rows = await querySupabase(env, "ox_questions", {
    select: "original_no,source_no,stable_id,question,answer,explanation",
    year: `eq.${year}`,
    subject: `eq.${subject}`,
    order: "original_no.asc",
  });

  if (!rows) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  const questions = rows.map((r) => ({
    original_no: r.original_no,
    source_no: r.source_no || r.original_no,
    stable_id: r.stable_id || "",
    question: r.question || "",
    answer: r.answer || "",
    explanation: r.explanation || "",
  }));

  return Response.json({ year, subject, count: questions.length, questions });
}

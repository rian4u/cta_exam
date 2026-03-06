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

// GET /api/wrong-notes/map?user_id=&source=question&year=2025&subject=재정학
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const userId = normalizeUserId(url.searchParams.get("user_id"));
  const source = url.searchParams.get("source")?.trim().toLowerCase() || "question";
  const yearText = url.searchParams.get("year") || "";
  const subject = url.searchParams.get("subject") || "";
  const year = parseInt(yearText, 10);

  if (!year || isNaN(year)) {
    return Response.json({ error: "invalid year" }, { status: 400 });
  }
  if (source !== "question" && source !== "ox") {
    return Response.json({ error: "invalid source" }, { status: 400 });
  }
  if (!SUBJECTS.has(subject)) {
    return Response.json({ error: "invalid subject" }, { status: 400 });
  }

  const supabaseUrl = new URL(`${env.SUPABASE_URL}/rest/v1/user_notes`);
  supabaseUrl.searchParams.set("select", "question_no,importance,comment,updated_at");
  supabaseUrl.searchParams.set("user_id", `eq.${userId}`);
  supabaseUrl.searchParams.set("source", `eq.${source}`);
  supabaseUrl.searchParams.set("year", `eq.${year}`);
  supabaseUrl.searchParams.set("subject", `eq.${subject}`);

  const res = await fetch(supabaseUrl.toString(), {
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
  });

  if (!res.ok) {
    return Response.json({ error: "database error" }, { status: 502 });
  }

  const rows = await res.json().catch(() => []);
  const items = {};
  for (const r of rows) {
    const imp = r.importance || "";
    const normalizedImp = IMPORTANCE_LEVELS.has(imp) ? imp : "";
    items[String(r.question_no)] = {
      importance: normalizedImp,
      comment: r.comment || "",
      updated_at: r.updated_at || "",
    };
  }

  return Response.json({ user_id: userId, year, subject, source, items });
}

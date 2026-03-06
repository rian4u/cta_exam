const nicknameInput   = document.getElementById("inq-nickname");
const titleInput      = document.getElementById("inq-title");
const bodyInput       = document.getElementById("inq-body");
const subjectInput    = document.getElementById("inq-subject");
const yearInput       = document.getElementById("inq-year");
const questionNoInput = document.getElementById("inq-question-no");
const submitButton    = document.getElementById("inq-submit");
const refreshButton   = document.getElementById("inq-refresh");
const formMessage     = document.getElementById("inq-message");
const listMessage     = document.getElementById("inq-list-message");
const listEl          = document.getElementById("inq-list");

const adminLoginCard  = document.getElementById("admin-login-card");
const adminKeyInput   = document.getElementById("admin-key-input");
const adminLoginBtn   = document.getElementById("admin-login-btn");
const adminLogoutBtn  = document.getElementById("admin-logout-btn");
const adminStatus     = document.getElementById("admin-status");

const NICKNAME_KEY    = "inq:nickname";
const ADMIN_KEY_STORE = "inq:adminKey";

const state = {
  apiBase: "",
  apiReady: false,
  adminKey: "",
};

// ── 관리자 모드 ──────────────────────────────────────────────────────────────
function initAdminMode() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("admin") === "1") {
    if (adminLoginCard) adminLoginCard.style.display = "";
  }
  const storedKey = localStorage.getItem(ADMIN_KEY_STORE) || "";
  if (storedKey) {
    state.adminKey = storedKey;
    if (adminStatus) adminStatus.textContent = "관리자 모드 활성";
    if (adminLogoutBtn) adminLogoutBtn.style.display = "";
    if (adminLoginBtn) adminLoginBtn.style.display = "none";
  }
}

adminLoginBtn?.addEventListener("click", () => {
  const key = adminKeyInput?.value.trim();
  if (!key) return;
  state.adminKey = key;
  localStorage.setItem(ADMIN_KEY_STORE, key);
  if (adminStatus) adminStatus.textContent = "관리자 모드 활성";
  if (adminLogoutBtn) adminLogoutBtn.style.display = "";
  if (adminLoginBtn) adminLoginBtn.style.display = "none";
  if (adminKeyInput) adminKeyInput.value = "";
  loadPosts();
});

adminLogoutBtn?.addEventListener("click", () => {
  state.adminKey = "";
  localStorage.removeItem(ADMIN_KEY_STORE);
  if (adminStatus) adminStatus.textContent = "";
  if (adminLogoutBtn) adminLogoutBtn.style.display = "none";
  if (adminLoginBtn) adminLoginBtn.style.display = "";
  loadPosts();
});

// ── API 탐색 ─────────────────────────────────────────────────────────────────
function getApiCandidates() {
  const candidates = [];
  const { origin, protocol, hostname } = window.location;
  if (origin && origin !== "null" && protocol.startsWith("http")) candidates.push(origin);
  if (hostname) candidates.push(`http://${hostname}:8000`);
  candidates.push("http://127.0.0.1:8000");
  candidates.push("http://localhost:8000");
  return [...new Set(candidates)];
}

async function verifyApiReady() {
  for (const base of getApiCandidates()) {
    try {
      const res = await fetch(`${base}/api/health`, { mode: "cors" });
      if (!res.ok) continue;
      state.apiBase = base;
      state.apiReady = true;
      return true;
    } catch (_) {}
  }
  state.apiReady = false;
  state.apiBase = "";
  return false;
}

function ensureApi() {
  if (state.apiReady) return Promise.resolve(true);
  return verifyApiReady();
}

// ── 닉네임 저장/복원 ─────────────────────────────────────────────────────────
function saveNickname() {
  const val = String(nicknameInput?.value || "").trim();
  if (val) localStorage.setItem(NICKNAME_KEY, val);
  else localStorage.removeItem(NICKNAME_KEY);
}

function restoreNickname() {
  const val = localStorage.getItem(NICKNAME_KEY) || "";
  if (val && nicknameInput) nicknameInput.value = val;
}

// ── 유틸 ─────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch (_) {
    return String(iso).slice(0, 16);
  }
}

// ── 답변 폼 생성 ─────────────────────────────────────────────────────────────
function createReplyForm(postId) {
  const wrap = document.createElement("div");
  wrap.className = "qa-answer-form";

  const textarea = document.createElement("textarea");
  textarea.className = "wrong-input qa-answer-input";
  textarea.rows = 3;
  textarea.placeholder = state.adminKey ? "관리자 답변을 입력하세요." : "답변을 남기세요.";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "exam-back";
  btn.textContent = state.adminKey ? "관리자 답변 등록" : "답변 등록";

  btn.addEventListener("click", async () => {
    const nickname = String(nicknameInput?.value || "").trim() || (state.adminKey ? "관리자" : "");
    const body = textarea.value.trim();
    saveNickname();
    if (!nickname || !body) {
      if (listMessage) listMessage.textContent = "닉네임과 내용이 필요합니다.";
      return;
    }
    if (!await ensureApi()) {
      if (listMessage) listMessage.textContent = "API에 연결할 수 없습니다.";
      return;
    }
    btn.disabled = true;
    try {
      const headers = { "Content-Type": "application/json" };
      if (state.adminKey) headers["X-Inquiry-Admin-Key"] = state.adminKey;
      const res = await fetch(`${state.apiBase}/api/inquiry/replies`, {
        method: "POST",
        headers,
        body: JSON.stringify({ inquiry_id: postId, nickname, body }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (listMessage) listMessage.textContent = data.error || "답변 등록에 실패했습니다.";
        return;
      }
      textarea.value = "";
      if (listMessage) listMessage.textContent = "답변이 등록되었습니다.";
      await loadPosts();
    } catch (_) {
      if (listMessage) listMessage.textContent = "오류가 발생했습니다.";
    } finally {
      btn.disabled = false;
    }
  });

  wrap.append(textarea, btn);
  return wrap;
}

// ── 게시글 렌더링 ────────────────────────────────────────────────────────────
function renderPosts(items) {
  if (!listEl) return;
  listEl.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "qa-empty";
    empty.textContent = "등록된 문의가 없습니다.";
    listEl.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "qa-item";

    const details = document.createElement("details");
    details.className = "qa-disclosure";

    const summary = document.createElement("summary");
    summary.className = "qa-summary";

    const titleEl = document.createElement("div");
    titleEl.className = "qa-title";
    if (item.is_closed) {
      const badge = document.createElement("span");
      badge.className = "qa-badge qa-badge-closed";
      badge.textContent = "답변완료";
      titleEl.appendChild(badge);
      titleEl.append(" ");
    }
    titleEl.append(document.createTextNode(item.title || "(제목 없음)"));

    const meta = document.createElement("div");
    meta.className = "qa-meta";
    const parts = [item.nickname || "익명", formatDate(item.created_at)];
    if (item.subject) {
      let ref = item.subject;
      if (Number(item.year) > 0) ref += ` ${item.year}`;
      if (Number(item.question_no) > 0) ref += `-${item.question_no}번`;
      parts.push(ref);
    }
    meta.textContent = parts.join(" | ");

    const content = document.createElement("div");
    content.className = "qa-content";

    const bodyEl = document.createElement("div");
    bodyEl.className = "qa-body";
    bodyEl.textContent = item.body || "";

    const replyList = document.createElement("div");
    replyList.className = "qa-answer-list";
    const replies = Array.isArray(item.answers) ? item.answers : [];
    if (!replies.length) {
      const empty = document.createElement("div");
      empty.className = "qa-answer-empty";
      empty.textContent = "등록된 답변이 없습니다.";
      replyList.appendChild(empty);
    } else {
      replies.forEach((r) => {
        const rCard = document.createElement("div");
        rCard.className = "qa-answer-item" + (r.is_admin ? " qa-answer-admin" : "");

        const rMeta = document.createElement("div");
        rMeta.className = "qa-answer-meta";
        if (r.is_admin) {
          const badge = document.createElement("span");
          badge.className = "qa-badge qa-badge-admin";
          badge.textContent = "관리자";
          rMeta.appendChild(badge);
          rMeta.append(" ");
        }
        rMeta.append(`${r.nickname || "익명"} | ${formatDate(r.created_at)}`);

        const rBody = document.createElement("div");
        rBody.className = "qa-answer-body";
        rBody.textContent = r.body || "";

        rCard.append(rMeta, rBody);
        replyList.appendChild(rCard);
      });
    }

    summary.append(titleEl, meta);
    content.append(bodyEl, replyList, createReplyForm(item.id));
    details.append(summary, content);
    card.appendChild(details);
    listEl.appendChild(card);
  });
}

// ── 목록 로드 ────────────────────────────────────────────────────────────────
async function loadPosts() {
  if (!await ensureApi()) {
    if (listMessage) listMessage.textContent = "API에 연결할 수 없습니다.";
    renderPosts([]);
    return;
  }
  try {
    const res = await fetch(`${state.apiBase}/api/inquiry/posts?limit=60`, { mode: "cors" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (listMessage) listMessage.textContent = data.error || "문의 목록을 불러오지 못했습니다.";
      renderPosts([]);
      return;
    }
    if (listMessage) listMessage.textContent = "";
    renderPosts(Array.isArray(data.items) ? data.items : []);
  } catch (_) {
    if (listMessage) listMessage.textContent = "목록을 불러오는 중 오류가 발생했습니다.";
    renderPosts([]);
  }
}

// ── 문의 등록 ────────────────────────────────────────────────────────────────
async function submitPost() {
  saveNickname();
  const nickname   = String(nicknameInput?.value || "").trim();
  const title      = String(titleInput?.value || "").trim();
  const body       = String(bodyInput?.value || "").trim();
  const subject    = String(subjectInput?.value || "").trim();
  const year       = Number(yearInput?.value || 0);
  const questionNo = Number(questionNoInput?.value || 0);

  if (!nickname || !title || !body) {
    if (formMessage) formMessage.textContent = "닉네임, 제목, 내용은 필수입니다.";
    return;
  }
  if (!await ensureApi()) {
    if (formMessage) formMessage.textContent = "API에 연결할 수 없습니다.";
    return;
  }

  if (submitButton) submitButton.disabled = true;
  try {
    const res = await fetch(`${state.apiBase}/api/inquiry/posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname, title, body, subject, year, question_no: questionNo }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (formMessage) formMessage.textContent = data.error || "등록에 실패했습니다.";
      return;
    }
    if (titleInput) titleInput.value = "";
    if (bodyInput) bodyInput.value = "";
    if (yearInput) yearInput.value = "";
    if (questionNoInput) questionNoInput.value = "";
    if (subjectInput) subjectInput.value = "";
    if (formMessage) formMessage.textContent = "문의가 등록되었습니다.";
    await loadPosts();
  } catch (_) {
    if (formMessage) formMessage.textContent = "등록 중 오류가 발생했습니다.";
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
}

// ── 초기화 ───────────────────────────────────────────────────────────────────
restoreNickname();
initAdminMode();
submitButton?.addEventListener("click", submitPost);
refreshButton?.addEventListener("click", loadPosts);
nicknameInput?.addEventListener("change", saveNickname);
loadPosts();

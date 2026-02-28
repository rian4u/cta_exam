const list = document.getElementById("notice-list");
const message = document.getElementById("notice-message");
const adminCard = document.getElementById("notice-admin-card");
const adminKeyInput = document.getElementById("notice-admin-key");
const titleInput = document.getElementById("notice-title");
const bodyInput = document.getElementById("notice-body");
const publishedInput = document.getElementById("notice-published");
const saveButton = document.getElementById("notice-save");

const state = {
  apiReady: false,
  apiBase: "",
  adminMode: new URLSearchParams(window.location.search).get("admin") === "1",
};

function getApiBaseCandidates() {
  const candidates = [];
  const { origin, protocol, hostname } = window.location;
  if (origin && origin !== "null" && protocol.startsWith("http")) {
    candidates.push(origin);
  }
  if (hostname) {
    candidates.push(`http://${hostname}:8000`);
  }
  candidates.push("http://127.0.0.1:8000");
  candidates.push("http://localhost:8000");
  return [...new Set(candidates)];
}

async function verifyApiReady() {
  for (const base of getApiBaseCandidates()) {
    try {
      const response = await fetch(`${base}/api/health`, { mode: "cors" });
      if (!response.ok) {
        continue;
      }
      state.apiReady = true;
      state.apiBase = base;
      return;
    } catch (_) {}
  }
  state.apiReady = false;
  state.apiBase = "";
}

function renderNotices(items) {
  list.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "notice-empty";
    empty.textContent = "??? ??? ????.";
    list.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("li");
    row.className = "notice-item";

    const details = document.createElement("details");
    details.className = "notice-disclosure";

    const summary = document.createElement("summary");
    summary.className = "notice-summary";

    const summaryMain = document.createElement("div");
    summaryMain.className = "notice-summary-main";

    const date = document.createElement("span");
    date.className = "notice-date";
    date.textContent = String(item.updated_at || item.created_at || "-").slice(0, 10);

    const textWrap = document.createElement("div");
    textWrap.className = "notice-summary-text";

    const title = document.createElement("h3");
    title.className = "notice-title";
    const titleSuffix = Number(item.is_published) === 1 ? "" : " (???)";
    title.textContent = `${item.title || "(?? ??)"}${titleSuffix}`;

    const meta = document.createElement("div");
    meta.className = "notice-meta";
    meta.textContent = `${item.author || "???"}`;

    const body = document.createElement("p");
    body.className = "notice-body-text";
    body.textContent = item.body || "";

    textWrap.append(title, meta);
    summaryMain.append(date, textWrap);
    summary.append(summaryMain);
    details.append(summary, body);
    row.append(details);
    list.appendChild(row);
  });
}

async function loadNotices() {
  if (!state.apiReady || !state.apiBase) {
    await verifyApiReady();
  }
  if (!state.apiReady) {
    message.textContent = "공지 API에 연결할 수 없습니다.";
    renderNotices([]);
    return;
  }
  const query = new URLSearchParams();
  if (state.adminMode) {
    query.set("admin", "1");
  }
  const headers = {};
  if (state.adminMode && adminKeyInput?.value.trim()) {
    headers["X-Notice-Admin-Key"] = adminKeyInput.value.trim();
  }
  const response = await fetch(`${state.apiBase}/api/notices?${query.toString()}`, { headers });
  if (!response.ok) {
    message.textContent = "공지 목록을 불러오지 못했습니다.";
    renderNotices([]);
    return;
  }
  const payload = await response.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  message.textContent = "";
  renderNotices(items);
}

async function saveNotice() {
  const title = titleInput?.value.trim() || "";
  const body = bodyInput?.value.trim() || "";
  const key = adminKeyInput?.value.trim() || "";
  if (!title || !body) {
    message.textContent = "제목과 내용을 입력해 주세요.";
    return;
  }
  if (!key) {
    message.textContent = "관리자 키가 필요합니다.";
    return;
  }
  if (!state.apiReady || !state.apiBase) {
    await verifyApiReady();
  }
  if (!state.apiReady) {
    message.textContent = "공지 API에 연결할 수 없습니다.";
    return;
  }

  const response = await fetch(`${state.apiBase}/api/notices`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Notice-Admin-Key": key,
    },
    body: JSON.stringify({
      title,
      body,
      author: "관리자",
      is_published: publishedInput?.checked ? 1 : 0,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    message.textContent = payload.error || "공지 등록에 실패했습니다.";
    return;
  }

  message.textContent = "공지 등록이 완료되었습니다.";
  if (titleInput) titleInput.value = "";
  if (bodyInput) bodyInput.value = "";
  await loadNotices();
}

async function init() {
  if (adminCard) {
    adminCard.classList.toggle("hidden", !state.adminMode);
  }
  await loadNotices();
  if (state.adminMode && saveButton) {
    saveButton.addEventListener("click", saveNotice);
  }
}

init();

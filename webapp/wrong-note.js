const SUBJECTS = ["재정학", "세법학개론", "회계학개론", "상법", "민법", "행정소송법"];
const USER_STORAGE_KEY = "taxexam:user-id";
const DEFAULT_USER_ID = "guest";

const state = {
  apiReady: false,
  apiBase: "",
  selectedImportances: new Set(["red", "yellow", "green", "gray"]),
  userId: DEFAULT_USER_ID,
  searchTimer: null,
};
const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);

const userInput = document.getElementById("wrong-filter-user");
const subjectSelect = document.getElementById("wrong-filter-subject");
const trafficButtons = [...document.querySelectorAll("#wrong-filter-traffic .traffic-btn")];
const commentInput = document.getElementById("wrong-filter-comment");
const message = document.getElementById("wrong-message");
const resultList = document.getElementById("wrong-result-list");

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
      message.textContent = "";
      return;
    } catch (_) {}
  }
  state.apiReady = false;
  state.apiBase = "";
  message.textContent = "DB API에 연결되지 않았습니다. webapp/server.py 서버를 실행한 후 다시 시도해 주세요.";
}

function initSubjectFilter() {
  SUBJECTS.forEach((subject) => {
    const option = document.createElement("option");
    option.value = subject;
    option.textContent = subject;
    subjectSelect.appendChild(option);
  });
}

function renderTrafficFilter() {
  trafficButtons.forEach((button) => {
    button.classList.toggle("active", state.selectedImportances.has(button.dataset.importance || ""));
  });
}

function normalizeImportance(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return IMPORTANCE_LEVELS.has(normalized) ? normalized : "green";
}

function normalizeUserId(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return DEFAULT_USER_ID;
  }
  return normalized.slice(0, 64);
}

function applyUserId(value, { persist = true } = {}) {
  const userId = normalizeUserId(value);
  state.userId = userId;
  if (userInput && userInput.value !== userId) {
    userInput.value = userId;
  }
  if (persist) {
    try {
      localStorage.setItem(USER_STORAGE_KEY, userId);
    } catch (_) {}
  }
}

function initUserId() {
  const storedUserId = (() => {
    try {
      return localStorage.getItem(USER_STORAGE_KEY) || "";
    } catch (_) {
      return "";
    }
  })();
  applyUserId(storedUserId, { persist: false });
}

function buildLight(importance) {
  const normalizedImportance = normalizeImportance(importance);
  const light = document.createElement("span");
  light.className = "wrong-result-light traffic-btn";
  if (IMPORTANCE_LEVELS.has(normalizedImportance)) {
    light.classList.add(`traffic-${normalizedImportance}`, "active");
    light.setAttribute("aria-label", normalizedImportance);
  } else {
    light.classList.add("wrong-result-light-none");
    light.setAttribute("aria-label", "미지정");
  }
  return light;
}

function renderResults(items) {
  resultList.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "wrong-result-empty";
    empty.textContent = "검색 결과가 없습니다.";
    resultList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("li");
    row.className = "wrong-result-item";

    const query = new URLSearchParams({
      year: String(item.year),
      subject: item.subject,
      questionNo: String(item.question_no),
      userId: state.userId,
    });

    const titleRow = document.createElement("div");
    titleRow.className = "wrong-result-title-row";

    const link = document.createElement("a");
    link.className = "wrong-result-link";
    link.href = `./mock-exam.html?${query.toString()}`;
    link.textContent = `${item.subject} | ${item.year}년 | ${item.question_no}번`;

    titleRow.append(link, buildLight(item.importance || ""));

    const commentRow = document.createElement("div");
    commentRow.className = "wrong-result-comment-row";

    const comment = document.createElement("div");
    comment.className = "wrong-result-comment";
    comment.textContent = item.comment || "(코멘트 없음)";

    const updated = document.createElement("span");
    updated.className = "wrong-result-updated";
    updated.textContent = item.updated_at || "-";

    commentRow.append(comment, updated);

    const preview = document.createElement("div");
    preview.className = "wrong-result-preview";
    preview.textContent = item.question_preview || "";

    row.append(titleRow, commentRow, preview);
    resultList.appendChild(row);
  });
}

async function searchWrongNotes() {
  if (!state.apiReady || !state.apiBase) {
    await verifyApiReady();
  }
  if (!state.apiReady) {
    return;
  }

  const query = new URLSearchParams();
  query.set("user_id", state.userId);
  if (subjectSelect.value) {
    query.set("subject", subjectSelect.value);
  }
  const keyword = commentInput.value.trim();
  if (keyword) {
    query.set("comment", keyword);
  }

  const response = await fetch(`${state.apiBase}/api/wrong-notes?${query.toString()}`);
  if (!response.ok) {
    message.textContent = "오답노트 검색 중 오류가 발생했습니다.";
    return;
  }

  const payload = await response.json();
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  const items =
    state.selectedImportances.size === 0
      ? []
      : rawItems.filter((item) => state.selectedImportances.has(normalizeImportance(item.importance)));
  renderResults(items);
  message.textContent = `검색 결과 ${items.length}건`;
}

function scheduleSearch() {
  if (state.searchTimer) {
    clearTimeout(state.searchTimer);
  }
  state.searchTimer = window.setTimeout(() => {
    searchWrongNotes();
  }, 160);
}

function bindEvents() {
  if (userInput) {
    userInput.addEventListener("change", () => {
      applyUserId(userInput.value);
      scheduleSearch();
    });
  }
  subjectSelect.addEventListener("change", scheduleSearch);
  commentInput.addEventListener("input", scheduleSearch);

  trafficButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.dataset.importance || "";
      if (state.selectedImportances.has(value)) {
        state.selectedImportances.delete(value);
      } else {
        state.selectedImportances.add(value);
      }
      renderTrafficFilter();
      scheduleSearch();
    });
  });
}

async function init() {
  initUserId();
  initSubjectFilter();
  renderTrafficFilter();
  bindEvents();
  await verifyApiReady();
  await searchWrongNotes();
}

init();

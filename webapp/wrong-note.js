const SUBJECTS = ["재정학", "회계학개론", "상법", "민법", "행정소송법", "국세기본법", "국세징수법", "소득세법", "법인세법", "부가가치세법", "조세범처벌법"];
const USER_STORAGE_KEY = "taxexam:device-id";
const LEGACY_USER_STORAGE_KEY = "taxexam:user-id";
const DEFAULT_USER_ID = "";

const state = {
  apiReady: false,
  apiBase: "",
  selectedImportances: new Set(["red", "yellow", "green", "gray"]),
  userId: DEFAULT_USER_ID,
  searchTimer: null,
};
const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);

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
  return IMPORTANCE_LEVELS.has(normalized) ? normalized : "";
}

function normalizeUserId(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return DEFAULT_USER_ID;
  }
  return normalized.slice(0, 64);
}

function generateDeviceId() {
  try {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `device-${window.crypto.randomUUID()}`;
    }
  } catch (_) {}
  return `device-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function applyUserId(value, { persist = true } = {}) {
  const userId = normalizeUserId(value);
  state.userId = userId;
  if (persist) {
    try {
      localStorage.setItem(USER_STORAGE_KEY, userId);
    } catch (_) {}
  }
}

function initUserId() {
  const storedUserId = (() => {
    try {
      return (
        localStorage.getItem(USER_STORAGE_KEY) ||
        localStorage.getItem(LEGACY_USER_STORAGE_KEY) ||
        ""
      );
    } catch (_) {
      return "";
    }
  })();
  const nextUserId = normalizeUserId(storedUserId) || generateDeviceId();
  applyUserId(nextUserId);
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
    empty.textContent = "?? ??? ????.";
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
    const source = String(item.source || "question").trim().toLowerCase();
    if (source === "ox") {
      query.set("source", "ox");
    }

    const titleRow = document.createElement("div");
    titleRow.className = "wrong-result-title-row";

    let trigger = null;
    if (source === "ox") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "wrong-result-trigger";
      button.textContent = `${item.subject} OX | ${item.question_no}?`;
      trigger = button;
    } else {
      const link = document.createElement("a");
      link.className = "wrong-result-link";
      link.href = `./mock-exam.html?${query.toString()}`;
      link.textContent = `${item.subject} | ${item.year}? | ${item.question_no}?`;
      trigger = link;
    }

    titleRow.append(trigger, buildLight(item.importance || ""));

    if (source === "ox") {
      const explainBox = document.createElement("div");
      explainBox.className = "wrong-result-inline-explain hidden";

      const answer = document.createElement("div");
      answer.className = "wrong-result-inline-answer";
      answer.textContent = `?? ${item.answer || "-"}`;

      const explanation = document.createElement("div");
      explanation.className = "wrong-result-inline-body";
      explanation.textContent = item.explanation || "?? ??? ????.";

      explainBox.append(answer, explanation);
      row.append(titleRow, explainBox);
      trigger.addEventListener("click", () => {
        explainBox.classList.toggle("hidden");
      });
    } else {
      row.append(titleRow);
    }

    const commentRow = document.createElement("div");
    commentRow.className = "wrong-result-comment-row";

    const comment = document.createElement("div");
    comment.className = "wrong-result-comment";
    comment.textContent = item.comment || "(??? ??)";

    const updated = document.createElement("span");
    updated.className = "wrong-result-updated";
    updated.textContent = item.updated_at || "-";

    commentRow.append(comment, updated);

    const preview = document.createElement("div");
    preview.className = "wrong-result-preview";
    preview.textContent = item.question_preview || "";

    row.append(commentRow, preview);
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
  const allColorsSelected = state.selectedImportances.size === IMPORTANCE_LEVELS.size;
  const items =
    state.selectedImportances.size === 0
      ? []
      : rawItems.filter((item) => {
          const importance = normalizeImportance(item.importance);
          if (!importance) {
            return allColorsSelected;
          }
          return state.selectedImportances.has(importance);
        });
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

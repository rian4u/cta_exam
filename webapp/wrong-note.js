const SUBJECTS = [
  "재정학",
  "세법학개론",
  "회계학개론",
  "상법",
  "민법",
  "행정소송법",
  "국세기본법",
  "국세징수법",
  "소득세법",
  "법인세법",
  "부가가치세법",
  "조세범처벌법",
];
const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);
const LocalUserData = window.TaxExamLocalData || null;

const state = {
  selectedImportances: new Set(["red", "yellow", "green", "gray"]),
  searchTimer: null,
};

const subjectSelect = document.getElementById("wrong-filter-subject");
const trafficButtons = [...document.querySelectorAll("#wrong-filter-traffic .traffic-btn")];
const commentInput = document.getElementById("wrong-filter-comment");
const message = document.getElementById("wrong-message");
const resultList = document.getElementById("wrong-result-list");

function normalizeImportance(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return IMPORTANCE_LEVELS.has(normalized) ? normalized : "";
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
    empty.textContent = "조회 결과가 없습니다.";
    resultList.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("li");
    row.className = "wrong-result-item";

    const titleRow = document.createElement("div");
    titleRow.className = "wrong-result-title-row";

    const source = String(item.source || "question").trim().toLowerCase();
    let trigger = null;

    if (source === "ox") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "wrong-result-trigger";
      button.textContent = String(item.subject || "") + " OX | " + String(item.question_no || 0) + "번";
      trigger = button;
    } else {
      const link = document.createElement("a");
      const query = new URLSearchParams({
        year: String(item.year || 0),
        subject: item.subject || "",
        questionNo: String(item.question_no || 0),
      });
      link.className = "wrong-result-link";
      link.href = `./mock-exam.html?${query.toString()}`;
      link.textContent =
        String(item.subject || "") +
        " | " +
        String(item.year || 0) +
        "년 | " +
        String(item.question_no || 0) +
        "번";
      trigger = link;
    }

    titleRow.append(trigger, buildLight(item.importance || ""));

    if (source === "ox") {
      const explainBox = document.createElement("div");
      explainBox.className = "wrong-result-inline-explain hidden";

      const answer = document.createElement("div");
      answer.className = "wrong-result-inline-answer";
      answer.textContent = "정답 " + (item.answer || "-");

      const explanation = document.createElement("div");
      explanation.className = "wrong-result-inline-body";
      explanation.textContent = item.explanation || "해설 정보가 없습니다.";

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
    comment.textContent = item.comment || "(코멘트 없음)";

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

function getAllNotes() {
  if (!LocalUserData || typeof LocalUserData.listNotes !== "function") {
    return [];
  }
  return LocalUserData.listNotes();
}

function filterNotes() {
  const selectedSubject = String(subjectSelect.value || "").trim();
  const keyword = String(commentInput.value || "")
    .trim()
    .toLowerCase();
  const allItems = getAllNotes();

  if (state.selectedImportances.size === 0) {
    return [];
  }

  return allItems.filter((item) => {
    const importance = normalizeImportance(item.importance);
    if (importance) {
      if (!state.selectedImportances.has(importance)) {
        return false;
      }
    } else if (state.selectedImportances.size !== IMPORTANCE_LEVELS.size) {
      return false;
    }

    if (selectedSubject && item.subject !== selectedSubject) {
      return false;
    }

    if (keyword) {
      const haystack = [
        item.subject || "",
        item.comment || "",
        item.question_preview || "",
        item.explanation || "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(keyword)) {
        return false;
      }
    }

    return true;
  });
}

function searchWrongNotes() {
  const items = filterNotes();
  renderResults(items);
  message.textContent = "검색 결과 " + String(items.length) + "건";
}

function scheduleSearch() {
  if (state.searchTimer) {
    clearTimeout(state.searchTimer);
  }
  state.searchTimer = window.setTimeout(() => {
    searchWrongNotes();
  }, 120);
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

  window.addEventListener("storage", (event) => {
    if (event.key === "taxexam:user-notes:v1") {
      searchWrongNotes();
    }
  });
}

function init() {
  initSubjectFilter();
  renderTrafficFilter();
  bindEvents();
  searchWrongNotes();
}

init();

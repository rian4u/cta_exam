const SUBJECTS = ["재정학", "회계학개론", "상법", "민법", "행정소송법", "국세기본법", "국세징수법", "소득세법", "법인세법", "부가가치세법", "조세범처벌법"];
const OX_YEAR = 2025;
const TAX_EXAM_DATE_2026 = new Date(2026, 3, 25);
const ALL_FILTER_COLORS = ["red", "yellow", "green", "gray"];
const DEFAULT_IMPORTANCE = "";
const USER_STORAGE_KEY = "taxexam:device-id";
const LEGACY_USER_STORAGE_KEY = "taxexam:user-id";

const TEXT = {
  noData: "선택한 과목 OX 데이터가 없습니다.",
  noFilteredData: "해당 조건에 맞는 문제가 없습니다.",
  loadFailed: "OX 데이터를 불러오지 못했습니다. webapp/server.py 서버를 확인해 주세요.",
  apiNotReady: "DB API에 연결되지 않았습니다. webapp/server.py 서버를 실행한 후 다시 시도해 주세요.",
  next: "다음",
  close: "닫기",
};

const state = {
  selectedSubject: "",
  enabledFilters: new Set(),
  apiReady: false,
  apiBase: "",
  userId: "",
  allQuestions: [],
  questions: [],
  currentIndex: 0,
  answers: {},
  explanationOpen: false,
  trafficMap: {},
  reviewOpen: false,
};

const setupPanel = document.getElementById("ox-setup-panel");
const examPanel = document.getElementById("ox-exam-panel");
const subjectGrid = document.getElementById("ox-subject-grid");
const startButton = document.getElementById("ox-start-button");
const setupMessage = document.getElementById("ox-setup-message");
const examLabel = document.getElementById("ox-exam-label");
const examDday = document.getElementById("ox-exam-dday");
const questionPanel = document.getElementById("ox-question-panel");
const statusQuestion = document.getElementById("ox-status-question");
const optionPanel = document.getElementById("ox-option-panel");
const optionList = document.getElementById("ox-option-list");
const explainPopup = document.getElementById("ox-explain-popup");
const explainPopupBody = document.getElementById("ox-explain-popup-body");
const explainClose = document.getElementById("ox-explain-close");
const explainCloseTop = document.getElementById("ox-explain-close-top");
const reviewPanel = document.getElementById("ox-review-panel");
const reviewSummary = document.getElementById("ox-review-summary");
const reviewList = document.getElementById("ox-review-list");
const reviewRestart = document.getElementById("ox-review-restart");
const filterButtons = [...document.querySelectorAll("#ox-filter-traffic-group .traffic-btn")];
const trafficButtons = [...document.querySelectorAll("#ox-traffic-group .traffic-btn")];

function stripLeadingQuestionNo(text) {
  return String(text || "")
    .replace(/^\s*(?:문제\s*)?(?:\d+|[①-⑳]|[OX])\s*[\.\)\]:：\-]\s*/u, "")
    .trimStart();
}

function normalizeImportanceColor(color) {
  const normalized = String(color || "").trim().toLowerCase();
  return ALL_FILTER_COLORS.includes(normalized) ? normalized : DEFAULT_IMPORTANCE;
}

function normalizeUserId(value) {
  const normalized = String(value || "").trim();
  return normalized ? normalized.slice(0, 64) : "";
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
  if (!persist) {
    return;
  }
  try {
    localStorage.setItem(USER_STORAGE_KEY, userId);
  } catch (_) {}
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

function getDdayLabel(targetDate) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(targetDate);
  target.setHours(0, 0, 0, 0);
  const diffDays = Math.ceil((target.getTime() - today.getTime()) / 86400000);
  return `D-${Math.max(0, diffDays)}`;
}

function renderExamDday() {
  if (examDday) {
    examDday.textContent = getDdayLabel(TAX_EXAM_DATE_2026);
  }
}

function createChoiceButtons(values, container, onClick) {
  container.innerHTML = "";
  values.forEach((value) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "choice-button";
    button.textContent = String(value);
    button.addEventListener("click", () => onClick(value));
    container.appendChild(button);
  });
}

function setActiveButton(container, matcher) {
  [...container.querySelectorAll(".choice-button")].forEach((button) => {
    button.classList.toggle("active", matcher(button.textContent));
  });
}

function shuffle(items) {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
  }
  return copy;
}

function renderFilterLights() {
  filterButtons.forEach((button) => {
    const color = button.dataset.filter || "";
    button.classList.toggle("active", state.enabledFilters.has(color));
  });
}

function refreshStartButton() {
  startButton.disabled = !state.selectedSubject;
}

function selectSubject(subject) {
  state.selectedSubject = subject;
  state.enabledFilters.clear();
  renderFilterLights();
  setActiveButton(subjectGrid, (label) => label === subject);
  setupMessage.textContent = "";
  refreshStartButton();
}

function normalizeQuestions(rows) {
  const normalized = rows.map((row) => ({
    originalNo: Number(row.original_no),
    stem: stripLeadingQuestionNo(row.question || ""),
    answer: String(row.answer || "").toUpperCase(),
    explanation: String(row.explanation || ""),
  }));
  return shuffle(normalized);
}

function typesetMath(targetNodes = []) {
  if (!window.MathJax || typeof window.MathJax.typesetPromise !== "function") {
    return;
  }
  const elements = targetNodes.filter(Boolean);
  if (!elements.length) {
    return;
  }
  window.MathJax.typesetPromise(elements).catch(() => {});
}

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
      if (!setupMessage.textContent || setupMessage.textContent === TEXT.apiNotReady) {
        setupMessage.textContent = "";
      }
      return;
    } catch (_) {}
  }
  state.apiReady = false;
  state.apiBase = "";
  setupMessage.textContent = TEXT.apiNotReady;
}

async function loadQuestionsFromDb() {
  if (!state.apiReady || !state.apiBase) {
    throw new Error("api not ready");
  }
  const query = new URLSearchParams({
    year: String(OX_YEAR),
    subject: state.selectedSubject,
  });
  const response = await fetch(`${state.apiBase}/api/ox/questions?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`ox question api failed: ${response.status}`);
  }
  const payload = await response.json();
  return normalizeQuestions(payload.questions ?? []);
}

async function loadTrafficMap() {
  if (!state.apiReady || !state.apiBase) {
    state.trafficMap = {};
    return;
  }
  const query = new URLSearchParams({
    user_id: state.userId,
    source: "ox",
    year: String(OX_YEAR),
    subject: state.selectedSubject,
  });
  const response = await fetch(`${state.apiBase}/api/wrong-notes/map?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`wrong note map api failed: ${response.status}`);
  }
  const payload = await response.json();
  const items = payload && typeof payload.items === "object" ? payload.items : {};
  const nextMap = {};
  Object.entries(items).forEach(([key, value]) => {
    if (!value || typeof value !== "object") {
      return;
    }
    const importance = normalizeImportanceColor(value.importance);
    const comment = String(value.comment || "");
    if (!importance && !comment) {
      return;
    }
    nextMap[String(key)] = {
      importance,
      comment,
      updatedAt: String(value.updated_at || ""),
    };
  });
  state.trafficMap = nextMap;
}

function getQuestionKey(question) {
  return String(question.originalNo);
}

function getQuestionNote(question) {
  const note = state.trafficMap[getQuestionKey(question)];
  if (!note || typeof note !== "object") {
    return { importance: DEFAULT_IMPORTANCE, comment: "", updatedAt: "" };
  }
  return {
    importance: normalizeImportanceColor(note.importance),
    comment: String(note.comment || ""),
    updatedAt: String(note.updatedAt || note.updated_at || ""),
  };
}

function getQuestionTraffic(question) {
  return getQuestionNote(question).importance;
}

async function setQuestionTraffic(question, color) {
  const key = getQuestionKey(question);
  const currentNote = getQuestionNote(question);
  const nextImportance = normalizeImportanceColor(color);
  const nextNote = {
    importance: nextImportance,
    comment: currentNote.comment,
    updatedAt: currentNote.updatedAt,
  };

  if (!nextNote.importance && !nextNote.comment) {
    delete state.trafficMap[key];
  } else {
    state.trafficMap[key] = nextNote;
  }

  if (!state.apiReady || !state.apiBase) {
    return;
  }

  const response = await fetch(`${state.apiBase}/api/wrong-notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      source: "ox",
      year: OX_YEAR,
      subject: state.selectedSubject,
      question_no: question.originalNo,
      importance: nextNote.importance,
      comment: nextNote.comment,
    }),
  });
  if (!response.ok) {
    throw new Error(`wrong note upsert failed: ${response.status}`);
  }
}

function applyQuestionFilter() {
  const activeFilters = [...state.enabledFilters].filter((color) => ALL_FILTER_COLORS.includes(color));
  const showAll = activeFilters.length === 0;
  const filtered = state.allQuestions.filter((question) => {
    if (showAll) {
      return true;
    }
    const traffic = getQuestionTraffic(question);
    return activeFilters.includes(traffic);
  });
  state.questions = shuffle(filtered);
}

function reflowAfterFilterChange() {
  applyQuestionFilter();
  setupMessage.textContent = "";
  if (state.currentIndex >= state.questions.length) {
    state.currentIndex = 0;
  }
  state.explanationOpen = false;
  renderExam();
}

function getCurrentQuestion() {
  return state.questions[state.currentIndex] || null;
}

function getSelectedChoice(question) {
  return state.answers[getQuestionKey(question)];
}

function renderOptions(question) {
  optionList.innerHTML = "";
  const selected = getSelectedChoice(question);
  ["O", "X"].forEach((choice) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button ox-choice-button";
    if (selected === choice) {
      button.classList.add("active");
    }
    if (selected) {
      if (choice === question.answer) {
        button.classList.add("correct-choice");
      } else if (choice === selected) {
        button.classList.add("wrong-choice");
      }
    }
    button.textContent = choice;
    button.addEventListener("click", () => handleOptionSelect(choice));
    optionList.appendChild(button);
  });
}

function renderTrafficButtons(question) {
  const traffic = getQuestionTraffic(question);
  trafficButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.traffic === traffic);
  });
}

function createInlineTrafficGroup(question) {
  const wrap = document.createElement("div");
  wrap.className = "traffic-group ox-review-traffic";
  ALL_FILTER_COLORS.forEach((color) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `traffic-btn traffic-${color}`;
    button.dataset.traffic = color;
    button.setAttribute("aria-label", color);
    button.classList.toggle("active", getQuestionTraffic(question) === color);
    button.addEventListener("click", async () => {
      const current = getQuestionTraffic(question);
      try {
        await setQuestionTraffic(question, current === color ? "" : color);
      } catch (_) {}
      renderTrafficButtons(question);
      renderReviewList();
    });
    wrap.appendChild(button);
  });
  return wrap;
}

function getAnsweredQuestionsForReview() {
  return state.questions.filter((question) => !!getSelectedChoice(question));
}

function hideReviewPanel() {
  state.reviewOpen = false;
  reviewPanel?.classList.add("hidden");
  questionPanel?.classList.remove("hidden");
  optionPanel?.classList.remove("hidden");
}

function renderReviewList() {
  if (!reviewList || !reviewSummary) {
    return;
  }
  const solved = getAnsweredQuestionsForReview();
  const wrongCount = solved.filter((question) => getSelectedChoice(question) !== question.answer).length;
  reviewSummary.textContent = `? ${solved.length}?? ?? | ?? ${wrongCount}??`;
  reviewList.innerHTML = "";
  if (!solved.length) {
    const empty = document.createElement("div");
    empty.className = "qa-empty";
    empty.textContent = "??? ??? ????.";
    reviewList.appendChild(empty);
    return;
  }
  solved.forEach((question) => {
    const item = document.createElement("article");
    item.className = "ox-review-item";

    const head = document.createElement("div");
    head.className = "ox-review-item-head";

    const title = document.createElement("div");
    title.className = "ox-review-title";
    title.textContent = question.stem || "";

    const myAnswer = getSelectedChoice(question) || "-";
    const meta = document.createElement("div");
    meta.className = "ox-review-meta";
    meta.textContent = `? ? ${myAnswer} | ?? ${question.answer || "-"}`;
    if (myAnswer && question.answer && myAnswer !== question.answer) {
      meta.classList.add("is-wrong");
    }

    const body = document.createElement("div");
    body.className = "ox-review-body";
    body.textContent = question.explanation || "?? ??? ????.";

    head.append(title, createInlineTrafficGroup(question));
    item.append(head, meta, body);
    reviewList.appendChild(item);
  });
  typesetMath([reviewList]);
}

function showReviewPanel() {
  state.reviewOpen = true;
  closeExplanationPopup();
  questionPanel?.classList.add("hidden");
  optionPanel?.classList.add("hidden");
  reviewPanel?.classList.remove("hidden");
  renderReviewList();
}

function syncExplanationPopupBounds() {
  if (!questionPanel || !optionPanel) {
    return;
  }
  const questionRect = questionPanel.getBoundingClientRect();
  const optionRect = optionPanel.getBoundingClientRect();
  const examRect = examPanel.getBoundingClientRect();
  const left = Math.min(questionRect.left, optionRect.left);
  const top = Math.min(questionRect.top, optionRect.top);
  const right = Math.max(questionRect.right, optionRect.right);
  const bottom = Math.max(questionRect.bottom, optionRect.bottom);
  explainPopup.style.left = `${left - examRect.left}px`;
  explainPopup.style.top = `${top - examRect.top}px`;
  explainPopup.style.width = `${right - left}px`;
  explainPopup.style.height = `${bottom - top}px`;
  explainPopup.style.right = "auto";
}

function openExplanationPopup() {
  state.explanationOpen = true;
  syncExplanationPopupBounds();
  explainPopup.classList.remove("hidden");
}

function closeExplanationPopup() {
  state.explanationOpen = false;
  explainPopup.classList.add("hidden");
}

function renderExplanationPopup(question) {
  if (!state.explanationOpen) {
    closeExplanationPopup();
    return;
  }
  const answerText = question.answer ? `정답: ${question.answer}` : "정답 정보 없음";
  const explanationText = question.explanation || "해설 정보가 없습니다.";
  explainPopupBody.textContent = `${answerText}\n\n${explanationText}`;
  explainClose.textContent =
    state.currentIndex < state.questions.length - 1 ? TEXT.next : TEXT.close;
  renderTrafficButtons(question);
  openExplanationPopup();
}

function renderExam() {
  if (state.reviewOpen) {
    examLabel.textContent = `${state.selectedSubject} OX ??`;
    renderReviewList();
    return;
  }
  const totalFiltered = state.questions.length;
  const question = getCurrentQuestion();
  examLabel.textContent = `${state.selectedSubject} OX (총 ${totalFiltered} 문제)`;
  if (!question) {
    statusQuestion.textContent = TEXT.noFilteredData;
    optionList.innerHTML = "";
    closeExplanationPopup();
    return;
  }

  statusQuestion.textContent = question.stem || "";
  renderOptions(question);
  renderExplanationPopup(question);
  const mathTargets = [statusQuestion];
  if (state.explanationOpen) {
    mathTargets.push(explainPopupBody);
  }
  typesetMath(mathTargets);
}

function handleOptionSelect(value) {
  const question = getCurrentQuestion();
  if (!question) {
    return;
  }
  state.answers[getQuestionKey(question)] = value;
  state.explanationOpen = true;
  renderExam();
}

function moveToNextQuestion() {
  if (state.currentIndex < state.questions.length - 1) {
    state.currentIndex += 1;
    state.explanationOpen = false;
    renderExam();
    return;
  }
  showReviewPanel();
}

function toggleFilterColor(color) {
  if (!color) {
    return;
  }
  if (state.enabledFilters.has(color)) {
    state.enabledFilters.delete(color);
  } else {
    state.enabledFilters.add(color);
  }
  renderFilterLights();
  if (state.allQuestions.length > 0) {
    if (state.reviewOpen) {
      renderReviewList();
    } else {
      reflowAfterFilterChange();
    }
  }
}

function showExamPanel() {
  setupPanel.classList.add("hidden");
  examPanel.classList.remove("hidden");
}

function showSetupPanel() {
  state.enabledFilters.clear();
  renderFilterLights();
  setupPanel.classList.remove("hidden");
  examPanel.classList.add("hidden");
  closeExplanationPopup();
}

async function startExam() {
  if (!state.apiReady) {
    await verifyApiReady();
  }
  if (!state.apiReady) {
    setupMessage.textContent = TEXT.apiNotReady;
    refreshStartButton();
    return;
  }

  setupMessage.textContent = "";
  startButton.disabled = true;
  try {
    const rows = await loadQuestionsFromDb();
    if (rows.length === 0) {
      setupMessage.textContent = TEXT.noData;
      return;
    }
    state.enabledFilters.clear();
    renderFilterLights();
    state.allQuestions = rows;
    await loadTrafficMap();
    applyQuestionFilter();
    state.currentIndex = 0;
    state.answers = {};
    state.explanationOpen = false;
    hideReviewPanel();
    showExamPanel();
    renderExam();
  } catch (_) {
    setupMessage.textContent = TEXT.loadFailed;
  } finally {
    refreshStartButton();
  }
}

function initEvents() {
  startButton.addEventListener("click", startExam);
  filterButtons.forEach((button) => {
    button.addEventListener("click", () => toggleFilterColor(button.dataset.filter || ""));
  });
  explainClose.addEventListener("click", moveToNextQuestion);
  if (explainCloseTop) {
    explainCloseTop.addEventListener("click", closeExplanationPopup);
  }
  trafficButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const question = getCurrentQuestion();
      if (!question) {
        return;
      }
      const value = button.dataset.traffic || "";
      const current = getQuestionTraffic(question);
      try {
        await setQuestionTraffic(question, current === value ? "" : value);
      } catch (_) {}
      renderTrafficButtons(question);
      if (state.enabledFilters.size > 0) {
        reflowAfterFilterChange();
      }
    });
  });
  window.addEventListener("resize", () => {
    if (state.explanationOpen) {
      syncExplanationPopupBounds();
    }
  });
  reviewRestart?.addEventListener("click", () => {
    startExam();
  });
}

async function init() {
  initUserId();
  createChoiceButtons(SUBJECTS, subjectGrid, selectSubject);
  await verifyApiReady();
  state.enabledFilters.clear();
  renderFilterLights();
  renderExamDday();
  initEvents();
  showSetupPanel();
  refreshStartButton();
}

init();

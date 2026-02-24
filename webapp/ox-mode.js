const SUBJECTS = ["재정학", "세법학개론", "회계학개론", "상법", "민법", "행정소송법"];
const OX_YEAR = 2025;
const TAX_EXAM_DATE_2026 = new Date(2026, 3, 25);
const ALL_FILTER_COLORS = ["red", "yellow", "green", "gray"];
const DEFAULT_IMPORTANCE = "green";

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
  enabledFilters: new Set(ALL_FILTER_COLORS),
  apiReady: false,
  apiBase: "",
  allQuestions: [],
  questions: [],
  currentIndex: 0,
  answers: {},
  explanationOpen: false,
  trafficMap: {},
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
const topFilterButtons = [...document.querySelectorAll("#ox-filter-traffic-group .traffic-btn")];
const filterButtons = [...topFilterButtons];
const trafficButtons = [...document.querySelectorAll("#ox-traffic-group .traffic-btn")];

function stripLeadingQuestionNo(text) {
  return String(text || "").replace(/^\s*(?:문제\s*)?(?:\d+|[①-⑳]|[OX])\s*[\.\)\]:：\-]\s*/u, "").trimStart();
}
function normalizeImportanceColor(color) {
  const normalized = String(color || "")
    .trim()
    .toLowerCase();
  return ALL_FILTER_COLORS.includes(normalized) ? normalized : DEFAULT_IMPORTANCE;
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
  if (!examDday) {
    return;
  }
  examDday.textContent = getDdayLabel(TAX_EXAM_DATE_2026);
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
  const buttons = [...container.querySelectorAll(".choice-button")];
  buttons.forEach((button) => {
    button.classList.toggle("active", matcher(button.textContent));
  });
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
  setActiveButton(subjectGrid, (label) => label === subject);
  setupMessage.textContent = "";
  refreshStartButton();
}

function normalizeQuestions(rows) {
  const sorted = [...rows].sort((a, b) => a.original_no - b.original_no);
  return sorted.map((row) => ({
    originalNo: row.original_no,
    stem: stripLeadingQuestionNo(row.question || ""),
    answer: String(row.answer || "").toUpperCase(),
    explanation: row.explanation || "",
  }));
}

function typesetMath(targetNodes = []) {
  if (!window.MathJax || typeof window.MathJax.typesetPromise !== "function") {
    return;
  }
  const elements = targetNodes.filter(Boolean);
  if (elements.length === 0) {
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
  const candidates = getApiBaseCandidates();
  for (const base of candidates) {
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

function getTrafficStorageKey() {
  return `ox-traffic:${OX_YEAR}:${state.selectedSubject}`;
}

function loadTrafficMap() {
  try {
    const raw = localStorage.getItem(getTrafficStorageKey());
    const parsed = raw ? JSON.parse(raw) : {};
    const nextMap = {};
    if (parsed && typeof parsed === "object") {
      Object.entries(parsed).forEach(([key, value]) => {
        const normalized = normalizeImportanceColor(value);
        if (normalized !== DEFAULT_IMPORTANCE) {
          nextMap[String(key)] = normalized;
        }
      });
    }
    state.trafficMap = nextMap;
    saveTrafficMap();
  } catch (_) {
    state.trafficMap = {};
  }
}

function saveTrafficMap() {
  try {
    localStorage.setItem(getTrafficStorageKey(), JSON.stringify(state.trafficMap));
  } catch (_) {}
}

function getQuestionKey(question) {
  return String(question.originalNo);
}

function getQuestionTraffic(question) {
  return normalizeImportanceColor(state.trafficMap[getQuestionKey(question)]);
}
function setQuestionTraffic(question, color) {
  const key = getQuestionKey(question);
  const normalizedColor = normalizeImportanceColor(color);
  if (normalizedColor === DEFAULT_IMPORTANCE) {
    delete state.trafficMap[key];
  } else {
    state.trafficMap[key] = normalizedColor;
  }
  saveTrafficMap();
}

function applyQuestionFilter() {
  const showAll = state.enabledFilters.size === ALL_FILTER_COLORS.length;
  state.questions = state.allQuestions.filter((question) => {
    if (showAll) {
      return true;
    }
    return state.enabledFilters.has(getQuestionTraffic(question));
  });
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
  closeExplanationPopup();
  renderExam();
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
    reflowAfterFilterChange();
  }
}

function showExamPanel() {
  setupPanel.classList.add("hidden");
  examPanel.classList.remove("hidden");
}

function showSetupPanel() {
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
    state.allQuestions = rows;
    loadTrafficMap();
    applyQuestionFilter();
    state.currentIndex = 0;
    state.answers = {};
    state.explanationOpen = false;
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
    explainCloseTop.addEventListener("click", () => {
      closeExplanationPopup();
    });
  }
  trafficButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const question = getCurrentQuestion();
      if (!question) {
        return;
      }
      const value = button.dataset.traffic || "";
      const current = getQuestionTraffic(question);
      setQuestionTraffic(question, current === value ? "" : value);
      renderTrafficButtons(question);
      if (state.enabledFilters.size !== ALL_FILTER_COLORS.length) {
        reflowAfterFilterChange();
      }
    });
  });
  window.addEventListener("resize", () => {
    if (state.explanationOpen) {
      syncExplanationPopupBounds();
    }
  });
}

async function init() {
  createChoiceButtons(SUBJECTS, subjectGrid, selectSubject);
  await verifyApiReady();
  renderFilterLights();
  renderExamDday();
  initEvents();
  showSetupPanel();
  refreshStartButton();
}

init();



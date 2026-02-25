const SUBJECTS = ["재정학", "세법학개론", "회계학개론", "상법", "민법", "행정소송법"];
const YEARS = [2025, 2024, 2023, 2022, 2021, 2020];
const OPEN_YEARS = new Set([2025, 2024, 2023]);
const TAX_EXAM_DATE_2026 = new Date(2026, 3, 25);
const DEFAULT_IMPORTANCE = "";
const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);
const USER_STORAGE_KEY = "taxexam:device-id";
const LEGACY_USER_STORAGE_KEY = "taxexam:user-id";
const DEFAULT_USER_ID = "";

const TEXT = {
  explainOpen: "해설보기",
  explainClose: "해설닫기",
  answerLabel: "정답",
  distAnswerLabel: "배포정답",
  answerMissing: "정답 정보 없음",
  distMissing: "배포정답 정보 없음",
  explanationMissing: "해설 정보가 없습니다.",
  question: "문제",
  noData: "선택한 과목/연도 데이터가 없습니다.",
  loadFailed:
    "문제 데이터를 불러오지 못했습니다. webapp/server.py 서버를 확인해 주세요.",
  apiNotReady:
    "DB API에 연결되지 않았습니다. webapp/server.py 서버를 실행한 후 다시 시도해 주세요.",
  yearLocked: "현재는 2023~2025년만 오픈되어 있습니다.",
  yearSuffix: "년",
};

const state = {
  selectedSubject: "",
  selectedYear: null,
  userId: DEFAULT_USER_ID,
  apiReady: false,
  apiBase: "",
  questions: [],
  currentIndex: 0,
  answers: {},
  explanationOpen: false,
  notePopupOpen: false,
  wrongNotes: {},
  initialTargetNo: null,
  calc: {
    display: "0",
    memory: 0,
    grandTotal: 0,
    justEvaluated: false,
  },
};

const setupPanel = document.getElementById("setup-panel");
const examPanel = document.getElementById("exam-panel");
const phoneRoot = document.querySelector(".phone");
const subjectGrid = document.getElementById("subject-grid");
const yearGrid = document.getElementById("year-grid");
const startButton = document.getElementById("start-button");
const setupMessage = document.getElementById("setup-message");
const examLabel = document.getElementById("exam-label");
const statusGrid = document.getElementById("status-grid");
const questionNo = document.getElementById("question-no");
const questionPanel = document.querySelector(".question-panel");
const questionStem = document.getElementById("question-stem");
const optionPanel = document.querySelector(".option-panel");
const optionList = document.getElementById("option-list");
const explainButton = document.getElementById("explain-button");
const examDday = document.getElementById("exam-dday");
const calcToggle = document.getElementById("calc-toggle");
const calcPanel = document.getElementById("calc-panel");
const calcDisplay = document.getElementById("calc-display");
const calcClose = document.getElementById("calc-close");

const explainPopup = document.getElementById("explain-popup");
const explainPopupBody = document.getElementById("explain-popup-body");
const explainClose = document.getElementById("explain-close");
const trafficButtons = [...document.querySelectorAll(".traffic-btn")];
const noteOpenButton = document.getElementById("note-open-button");
const notePopup = document.getElementById("note-popup");
const noteTextarea = document.getElementById("note-textarea");
const noteCloseButton = document.getElementById("note-close-button");
const noteSaveButton = document.getElementById("note-save-button");
const noteClearButton = document.getElementById("note-clear-button");

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

function normalizeImportance(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  return IMPORTANCE_LEVELS.has(normalized) ? normalized : DEFAULT_IMPORTANCE;
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

function isYearEnabled(year) {
  return OPEN_YEARS.has(Number(year));
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

function refreshStartButton() {
  startButton.disabled = !(state.selectedSubject && isYearEnabled(state.selectedYear));
}

function selectSubject(subject) {
  state.selectedSubject = subject;
  setActiveButton(subjectGrid, (label) => label === subject);
  setupMessage.textContent = "";
  refreshStartButton();
}

function selectYear(year) {
  if (!isYearEnabled(year)) {
    return;
  }
  state.selectedYear = year;
  setActiveButton(yearGrid, (label) => Number(label) === year);
  setupMessage.textContent = "";
  refreshStartButton();
}

function createYearButtons() {
  yearGrid.innerHTML = "";
  YEARS.forEach((year) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "choice-button";
    button.textContent = String(year);
    const enabled = isYearEnabled(year);
    if (!enabled) {
      button.disabled = true;
      button.classList.add("disabled");
      button.setAttribute("aria-disabled", "true");
    } else {
      button.addEventListener("click", () => selectYear(Number(year)));
    }
    yearGrid.appendChild(button);
  });
}

function normalizeQuestions(rows) {
  const sorted = [...rows].sort((a, b) => a.original_no - b.original_no);
  return sorted.map((row, index) => ({
    index: index + 1,
    originalNo: row.original_no,
    stem: row.stem || "",
    stemHtml: row.stem_html || "",
    options: Array.isArray(row.options) ? row.options : ["", "", "", "", ""],
    optionsHtml: Array.isArray(row.options_html) ? row.options_html : ["", "", "", "", ""],
    answer: row.answer || "",
    distributedAnswer: row.distributed_answer || "",
    explanation: row.explanation || "",
  }));
}

function parseBootParams() {
  const params = new URLSearchParams(window.location.search);
  const year = Number(params.get("year") || "");
  const subject = params.get("subject") || "";
  const questionNo = Number(params.get("questionNo") || "");
  const userId = params.get("userId") || "";
  return {
    year: Number.isFinite(year) ? year : NaN,
    subject,
    questionNo: Number.isFinite(questionNo) ? questionNo : NaN,
    userId,
  };
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

async function loadQuestionsFromDb() {
  if (!state.apiReady || !state.apiBase) {
    throw new Error("api not ready");
  }
  const query = new URLSearchParams({
    year: String(state.selectedYear),
    subject: state.selectedSubject,
    user_id: state.userId,
  });
  const response = await fetch(`${state.apiBase}/api/questions?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`question api failed: ${response.status}`);
  }
  const payload = await response.json();
  return normalizeQuestions(payload.questions ?? []);
}

async function loadWrongNotesFromDb() {
  if (!state.apiReady || !state.apiBase) {
    state.wrongNotes = {};
    return;
  }
  const query = new URLSearchParams({
    year: String(state.selectedYear),
    subject: state.selectedSubject,
  });
  const response = await fetch(`${state.apiBase}/api/wrong-notes/map?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`wrong-note map api failed: ${response.status}`);
  }
  const payload = await response.json();
  state.wrongNotes = payload.items && typeof payload.items === "object" ? payload.items : {};
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

function parseChoiceSet(rawAnswer) {
  if (!rawAnswer) {
    return new Set();
  }
  const digits = rawAnswer.match(/[1-5]/g);
  return new Set(digits || []);
}

function getQuestionByIndex(index) {
  return state.questions[index] || null;
}

function getCurrentQuestion() {
  return getQuestionByIndex(state.currentIndex);
}

function getSelectedChoice(question) {
  return state.answers[question.index];
}

function getCorrectChoiceSet(question) {
  const primary = parseChoiceSet(question.answer);
  if (primary.size > 0) {
    return primary;
  }
  return parseChoiceSet(question.distributedAnswer);
}

function isQuestionAnswered(question) {
  return getSelectedChoice(question) !== undefined;
}

function isQuestionCorrect(question) {
  const selected = getSelectedChoice(question);
  if (selected === undefined) {
    return false;
  }
  const correctSet = getCorrectChoiceSet(question);
  if (correctSet.size === 0) {
    return false;
  }
  return correctSet.has(String(selected));
}

function isGradingComplete() {
  if (state.questions.length === 0) {
    return false;
  }
  return state.questions.every((question) => isQuestionAnswered(question));
}

function getScoreSummary() {
  const total = state.questions.length;
  let correct = 0;
  state.questions.forEach((question) => {
    if (isQuestionCorrect(question)) {
      correct += 1;
    }
  });
  const score = total > 0 ? Math.round((correct / total) * 100) : 0;
  return { total, correct, score };
}

function renderStatusGrid() {
  statusGrid.innerHTML = "";
  const count = Math.max(40, state.questions.length);
  const gradingComplete = isGradingComplete();

  for (let idx = 1; idx <= count; idx += 1) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "status-cell";
    button.textContent = String(idx);

    if (idx <= state.questions.length) {
      const question = state.questions[idx - 1];
      if (isQuestionAnswered(question)) {
        button.classList.add("solved");
      }
      if (gradingComplete && isQuestionAnswered(question)) {
        button.classList.add(isQuestionCorrect(question) ? "correct" : "wrong");
      }
      if (idx - 1 === state.currentIndex) {
        button.classList.add("current");
      }
      button.addEventListener("click", () => {
        state.currentIndex = idx - 1;
        closeNotePopup();
        renderExam();
      });
    } else {
      button.disabled = true;
      button.style.opacity = "0.35";
      button.style.cursor = "default";
    }
    statusGrid.appendChild(button);
  }
}

function renderOptions(question) {
  optionList.innerHTML = "";
  const selected = getSelectedChoice(question);
  const correctSet = getCorrectChoiceSet(question);
  const gradingComplete = isGradingComplete();

  question.options.forEach((optionText, optionIndex) => {
    const value = optionIndex + 1;
    const valueKey = String(value);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button";

    if (!gradingComplete && selected === value) {
      button.classList.add("active");
    }

    if (gradingComplete && selected !== undefined) {
      const selectedIsCorrect = correctSet.has(String(selected));
      if (selectedIsCorrect) {
        if (correctSet.has(valueKey)) {
          button.classList.add("correct-choice");
        }
      } else {
        if (selected === value) {
          button.classList.add("wrong-choice");
        }
        if (correctSet.has(valueKey)) {
          button.classList.add("correct-choice");
        }
      }
    }

    const left = document.createElement("span");
    left.className = "option-index";
    left.textContent = `${value}.`;
    const right = document.createElement("span");
    right.className = "option-text";
    const optionHtml = question.optionsHtml?.[optionIndex] || "";
    if (optionHtml) {
      right.innerHTML = optionHtml;
    } else {
      right.textContent = optionText;
    }
    button.append(left, right);

    button.addEventListener("click", () => handleOptionSelect(value));
    optionList.appendChild(button);
  });
}

function getWrongNoteKey(question) {
  return String(question.originalNo);
}

function getWrongNote(question) {
  const key = getWrongNoteKey(question);
  const note = state.wrongNotes[key];
  if (!note) {
    return { importance: DEFAULT_IMPORTANCE, comment: "" };
  }
  const importance = normalizeImportance(note.importance);
  return { ...note, importance };
}

async function persistWrongNote(question, note) {
  if (!state.apiReady || !state.apiBase) {
    return;
  }
  await fetch(`${state.apiBase}/api/wrong-notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: state.userId,
      year: state.selectedYear,
      subject: state.selectedSubject,
      question_no: question.originalNo,
      importance: note.importance || "",
      comment: note.comment || "",
    }),
  });
}

function setWrongNote(question, patch) {
  const key = getWrongNoteKey(question);
  const prev = getWrongNote(question);
  const next = { ...prev, ...patch };
  const hasComment = Boolean((next.comment || "").trim());
  const normalizedImportance = normalizeImportance(next.importance);
  const isDefaultOnly = normalizedImportance === DEFAULT_IMPORTANCE && !hasComment;

  if (isDefaultOnly) {
    delete state.wrongNotes[key];
    persistWrongNote(question, { importance: "", comment: "" }).catch(() => {});
  } else {
    const stored = { ...next, importance: normalizedImportance };
    state.wrongNotes[key] = stored;
    persistWrongNote(question, stored).catch(() => {});
  }
}

function renderTrafficButtons(question) {
  const note = getWrongNote(question);
  trafficButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.traffic === note.importance);
  });
}

function syncExplanationPopupBounds() {
  if (!optionPanel) {
    return;
  }
  const panelRect = optionPanel.getBoundingClientRect();
  const examRect = examPanel.getBoundingClientRect();

  const left = panelRect.left - examRect.left;
  const top = panelRect.top - examRect.top;
  explainPopup.style.left = `${left}px`;
  explainPopup.style.top = `${top}px`;
  explainPopup.style.width = `${panelRect.width}px`;
  explainPopup.style.height = `${panelRect.height}px`;
  explainPopup.style.right = "auto";
}

function syncCalculatorPopupBounds() {
  if (!optionPanel || !phoneRoot) {
    return;
  }
  const panelRect = optionPanel.getBoundingClientRect();
  const phoneRect = phoneRoot.getBoundingClientRect();

  const left = panelRect.left - phoneRect.left;
  const top = panelRect.top - phoneRect.top;
  calcPanel.style.left = `${left}px`;
  calcPanel.style.top = `${top}px`;
  calcPanel.style.width = `${panelRect.width}px`;
  calcPanel.style.height = `${panelRect.height}px`;
  calcPanel.style.bottom = "auto";
  calcPanel.style.transform = "none";
}

function syncCalculatorIfOpen() {
  if (calcPanel.classList.contains("hidden")) {
    return;
  }
  syncCalculatorPopupBounds();
  requestAnimationFrame(() => {
    if (!calcPanel.classList.contains("hidden")) {
      syncCalculatorPopupBounds();
    }
  });
}

function openExplanationPopup() {
  state.explanationOpen = true;
  explainButton.textContent = TEXT.explainClose;
  syncExplanationPopupBounds();
  explainPopup.classList.remove("hidden");
}

function closeExplanationPopup() {
  state.explanationOpen = false;
  explainButton.textContent = TEXT.explainOpen;
  explainPopup.classList.add("hidden");
  closeNotePopup();
}

function openNotePopup() {
  const question = getCurrentQuestion();
  if (!question) {
    return;
  }
  const note = getWrongNote(question);
  syncNotePopupBounds();
  noteTextarea.value = note.comment || "";
  notePopup.classList.remove("hidden");
  state.notePopupOpen = true;
  noteTextarea.focus();
}

function closeNotePopup() {
  state.notePopupOpen = false;
  notePopup.classList.add("hidden");
}

function syncNotePopupBounds() {
  if (!questionPanel) {
    return;
  }
  const questionRect = questionPanel.getBoundingClientRect();
  const examRect = examPanel.getBoundingClientRect();
  notePopup.style.left = `${questionRect.left - examRect.left}px`;
  notePopup.style.top = `${questionRect.top - examRect.top}px`;
  notePopup.style.width = `${questionRect.width}px`;
  notePopup.style.right = "auto";
}

function renderExplanationPopup(question) {
  if (!state.explanationOpen) {
    closeExplanationPopup();
    return;
  }

  const answerText = question.answer
    ? `${TEXT.answerLabel}: ${question.answer}`
    : TEXT.answerMissing;
  const distributedText = question.distributedAnswer
    ? `${TEXT.distAnswerLabel}: ${question.distributedAnswer}`
    : TEXT.distMissing;
  const explanation = question.explanation || TEXT.explanationMissing;

  explainPopupBody.textContent = `${answerText}\n${distributedText}\n\n${explanation}`;
  openExplanationPopup();
}

function renderExam() {
  const question = getCurrentQuestion();
  if (!question) {
    return;
  }

  let label = `${state.selectedSubject} | ${state.selectedYear}${TEXT.yearSuffix}`;
  if (isGradingComplete()) {
    const summary = getScoreSummary();
    label = `${label} ${summary.correct}/${summary.total}개 (${summary.score}점)`;
  }
  examLabel.textContent = label;
  questionNo.textContent = `${TEXT.question} ${question.index} / ${state.questions.length}`;
  if (question.stemHtml) {
    questionStem.innerHTML = question.stemHtml;
  } else {
    questionStem.textContent = question.stem;
  }

  renderStatusGrid();
  renderOptions(question);
  renderTrafficButtons(question);
  renderExplanationPopup(question);
  const mathTargets = [questionStem, optionList];
  if (state.explanationOpen) {
    mathTargets.push(explainPopupBody);
  }
  typesetMath(mathTargets);
  syncCalculatorIfOpen();
}

function showExamPanel() {
  setupPanel.classList.add("hidden");
  examPanel.classList.remove("hidden");
}

function showSetupPanel() {
  setupPanel.classList.remove("hidden");
  examPanel.classList.add("hidden");
  calcPanel.classList.add("hidden");
  closeExplanationPopup();
}

function handleOptionSelect(value) {
  const question = getCurrentQuestion();
  if (!question) {
    return;
  }
  state.answers[question.index] = value;
  closeExplanationPopup();

  if (state.currentIndex < state.questions.length - 1) {
    state.currentIndex += 1;
  }
  renderExam();
}

function safeEval(expression) {
  if (!/^[0-9+\-*/(). ]+$/.test(expression)) {
    return null;
  }
  try {
    const result = Function(`"use strict"; return (${expression});`)();
    if (typeof result !== "number" || !Number.isFinite(result)) {
      return null;
    }
    return result;
  } catch (_) {
    return null;
  }
}

function updateCalcDisplay(value) {
  state.calc.display = value;
  calcDisplay.value = value;
}

function appendCalcValue(value) {
  const current = state.calc.display;
  if (state.calc.justEvaluated && /^[0-9.]+$/.test(value)) {
    updateCalcDisplay(value);
    state.calc.justEvaluated = false;
    return;
  }
  state.calc.justEvaluated = false;
  if (current === "0" && /^[0-9]+$/.test(value)) {
    updateCalcDisplay(value);
    return;
  }
  updateCalcDisplay(current + value);
}

function evaluateCalc() {
  const value = safeEval(state.calc.display);
  if (value === null) {
    updateCalcDisplay("Error");
    state.calc.justEvaluated = true;
    return null;
  }
  const text = String(Number(value.toFixed(10)));
  updateCalcDisplay(text);
  state.calc.grandTotal += value;
  state.calc.justEvaluated = true;
  return value;
}

function numberFromDisplay() {
  const parsed = Number(state.calc.display);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function handleCalcAction(action) {
  if (action === "clear") {
    updateCalcDisplay("0");
    state.calc.justEvaluated = false;
    return;
  }
  if (action === "back") {
    if (state.calc.display.length <= 1 || state.calc.display === "Error") {
      updateCalcDisplay("0");
      return;
    }
    updateCalcDisplay(state.calc.display.slice(0, -1));
    return;
  }
  if (action === "equals") {
    evaluateCalc();
    return;
  }
  if (action === "mc") {
    state.calc.memory = 0;
    return;
  }
  if (action === "mr") {
    updateCalcDisplay(String(state.calc.memory));
    state.calc.justEvaluated = true;
    return;
  }
  if (action === "mplus") {
    state.calc.memory += numberFromDisplay();
    return;
  }
  if (action === "mminus") {
    state.calc.memory -= numberFromDisplay();
    return;
  }
  if (action === "gt") {
    updateCalcDisplay(String(Number(state.calc.grandTotal.toFixed(10))));
    state.calc.justEvaluated = true;
  }
}

function initCalculator() {
  updateCalcDisplay("0");
  calcPanel.querySelectorAll(".calc-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const { action, value } = button.dataset;
      if (action) {
        handleCalcAction(action);
      } else if (value) {
        appendCalcValue(value);
      }
    });
  });

  calcToggle.addEventListener("click", () => {
    const shouldOpen = calcPanel.classList.contains("hidden");
    if (shouldOpen) {
      syncCalculatorPopupBounds();
      calcPanel.classList.remove("hidden");
      return;
    }
    calcPanel.classList.add("hidden");
  });
  calcClose.addEventListener("pointerdown", (event) => {
    event.stopPropagation();
  });
  calcClose.addEventListener("click", () => {
    calcPanel.classList.add("hidden");
  });
  if (window.ResizeObserver && optionPanel) {
    const observer = new ResizeObserver(() => {
      syncCalculatorIfOpen();
    });
    observer.observe(optionPanel);
  }
}

function initExplanationEvents() {
  explainButton.addEventListener("click", () => {
    state.explanationOpen = !state.explanationOpen;
    if (!state.explanationOpen) {
      closeExplanationPopup();
      return;
    }
    renderExam();
  });

  explainClose.addEventListener("click", () => {
    closeExplanationPopup();
  });

  trafficButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const question = getCurrentQuestion();
      if (!question) {
        return;
      }
      const value = button.dataset.traffic || "";
      const current = getWrongNote(question).importance || DEFAULT_IMPORTANCE;
      setWrongNote(question, { importance: current === value ? "" : value });
      renderTrafficButtons(question);
    });
  });

  noteOpenButton.addEventListener("click", () => {
    openNotePopup();
  });
  noteCloseButton.addEventListener("click", closeNotePopup);

  noteSaveButton.addEventListener("click", () => {
    const question = getCurrentQuestion();
    if (!question) {
      return;
    }
    setWrongNote(question, { comment: noteTextarea.value });
    closeNotePopup();
    renderTrafficButtons(question);
  });

  noteClearButton.addEventListener("click", () => {
    const question = getCurrentQuestion();
    if (!question) {
      return;
    }
    setWrongNote(question, { comment: "" });
    noteTextarea.value = "";
    renderTrafficButtons(question);
  });
}

async function startExam() {
  if (!isYearEnabled(state.selectedYear)) {
    setupMessage.textContent = TEXT.yearLocked;
    refreshStartButton();
    return;
  }
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
    state.questions = rows;
    await loadWrongNotesFromDb();
    state.currentIndex = 0;
    if (state.initialTargetNo !== null) {
      const targetIndex = state.questions.findIndex(
        (question) => Number(question.originalNo) === Number(state.initialTargetNo),
      );
      if (targetIndex >= 0) {
        state.currentIndex = targetIndex;
      }
    }
    state.answers = {};
    state.explanationOpen = false;
    state.notePopupOpen = false;
    calcPanel.classList.add("hidden");
    showExamPanel();
    renderExam();
  } catch (_) {
    setupMessage.textContent = TEXT.loadFailed;
  } finally {
    refreshStartButton();
  }
}

async function init() {
  initUserId();
  createChoiceButtons(SUBJECTS, subjectGrid, selectSubject);
  createYearButtons();
  const boot = parseBootParams();
  if (boot.userId) {
    applyUserId(boot.userId);
  }
  if (SUBJECTS.includes(boot.subject)) {
    selectSubject(boot.subject);
  }
  if (YEARS.includes(boot.year) && isYearEnabled(boot.year)) {
    selectYear(boot.year);
  }
  if (Number.isFinite(boot.questionNo) && boot.questionNo > 0) {
    state.initialTargetNo = boot.questionNo;
  }
  await verifyApiReady();
  initCalculator();
  initExplanationEvents();
  renderExamDday();
  showSetupPanel();
  refreshStartButton();

  startButton.addEventListener("click", startExam);
  window.addEventListener("resize", () => {
    if (state.explanationOpen) {
      syncExplanationPopupBounds();
    }
    if (state.notePopupOpen) {
      syncNotePopupBounds();
    }
    syncCalculatorIfOpen();
  });

  if (state.selectedSubject && isYearEnabled(state.selectedYear)) {
    startExam();
  }
}

init();

